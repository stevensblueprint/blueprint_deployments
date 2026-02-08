import boto3
import json
import logging
from dataclasses import replace, asdict
from typing import Dict, Any, Tuple, Optional, List
from utils import load_safe_env, get_oauth_token_from_secret_arn
from models import (
    InfraConfig,
    WebsiteConfig,
    Template,
    DeployCreateRequest,
    DeployDeleteRequest,
    DeploymentStatus,
    StageStatus,
)
from services import GithubService, CloudFormationService

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets_client = boto3.client("secretsmanager")
codepipeline_client = boto3.client("codepipeline")
cloudformation_client = boto3.client("cloudformation")

DEPLOYMENT_SECRET_ARN = load_safe_env("DEPLOYMENT_SECRET_ARN")
PIPELINE_NAME = load_safe_env("PIPELINE_NAME")
GITHUB_OAUTH_TOKEN_ARN = load_safe_env("GITHUB_OAUTH_TOKEN_ARN")
ORGANIZATION_NAME = "stevensblueprint"
STACK_NAME_TEMPLATE = "blueprint-{}-website-stack"


def _normalize_route(event: Dict[str, Any]) -> Tuple[str, str]:
    method = (event.get("httpMethod") or "").upper()
    path = (event.get("resource") or event.get("path") or "").lower()
    path = path.split("?", 1)[0]
    if path.endswith("/"):
        path = path[:-1]
    if path and not path.startswith("/"):
        path = f"/{path}"
    return method, path


def _get_execution_id(event: Dict[str, Any], path: str) -> str:
    path_params = event.get("pathParameters") or {}
    execution_id = path_params.get("executionId") or path_params.get("proxy")
    if execution_id:
        return execution_id
    if "/deployment/" in path:
        return path.rsplit("/", 1)[-1]
    return ""


def _load_infra_config() -> InfraConfig:
    try:
        secret_value_response = secrets_client.get_secret_value(
            SecretId=DEPLOYMENT_SECRET_ARN
        )
        logger.info(
            "Successfully retrieved secret value from Secrets Manager.%s",
            secret_value_response,
        )
        secret_string = secret_value_response.get("SecretString")
        if not secret_string and secret_value_response.get("SecretBinary"):
            secret_string = secret_value_response.get("SecretBinary", "").decode(
                "utf-8"
            )
        logger.info("Successfully retrieved secret.")
    except Exception as e:
        logger.error("Error retrieving secret: %s", str(e))
        raise

    try:
        normalized = (secret_string or "").strip()
        if not normalized:
            normalized = "{}"
        return InfraConfig.from_dict(json.loads(normalized))
    except Exception as e:
        logger.error("Error parsing secret JSON: %s", str(e))
        raise


def _start_pipeline() -> Dict[str, Any]:
    response = codepipeline_client.start_pipeline_execution(name=PIPELINE_NAME)
    execution_id = response.get("pipelineExecutionId", "")
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(
            {
                "message": "Pipeline execution started.",
                "pipelineExecutionId": execution_id,
            }
        ),
    }


def _handle_deploy(event: DeployCreateRequest, oauth_token: str) -> Dict[str, Any]:
    try:
        infra_config = _load_infra_config()
    except Exception as e:
        return {
            "statusCode": 500,
            "body": f"Error loading secret: {str(e)}",
        }

    logger.info("Creating github repository with config: %s", infra_config)
    github_service = GithubService(token=oauth_token)
    github_service.create_respository_from_template(
        repo_name=f"{ORGANIZATION_NAME}/{event.githubRepositoryName}",
        template=Template.VITE,
        private=False,
    )
    logger.info(
        "Successfully created GitHub repository: %s/%s",
        ORGANIZATION_NAME,
        event.githubRepositoryName,
    )

    infra_config = replace(
        infra_config,
        WEBSITES=[*infra_config.WEBSITES, WebsiteConfig.from_dict(event.__dict__)],
    )
    logger.info("Updated infrastructure config: %s", infra_config)
    secrets_client.put_secret_value(
        SecretId=DEPLOYMENT_SECRET_ARN, SecretString=json.dumps(infra_config.to_dict())
    )

    try:
        return _start_pipeline()
    except Exception as e:
        logger.error("Error starting pipeline: %s", str(e))
        return {
            "statusCode": 500,
            "body": f"Error starting pipeline: {str(e)}",
        }


def _handle_delete(event: DeployDeleteRequest, oauth_token: str) -> Dict[str, Any]:
    try:
        infra_config = _load_infra_config()
    except Exception as e:
        return {
            "statusCode": 500,
            "body": f"Error loading secret: {str(e)}",
        }

    updated_websites = [
        website
        for website in infra_config.WEBSITES
        if not (
            website.githubRepositoryName == event.githubRepositoryName
            and website.subdomain == event.subdomain
        )
    ]
    if len(updated_websites) == len(infra_config.WEBSITES):
        return {
            "statusCode": 404,
            "body": "Deployment not found.",
        }
    infra_config = replace(infra_config, WEBSITES=updated_websites)

    github_service = GithubService(token=oauth_token)
    try:
        deleted = github_service.delete_repository(
            repo_name=f"{ORGANIZATION_NAME}/{event.githubRepositoryName}"
        )
        if not deleted:
            logger.warning("GitHub repository not found for deletion.")
    except Exception as e:
        logger.error("Error deleting GitHub repository: %s", str(e))
        return {
            "statusCode": 500,
            "body": f"Error deleting GitHub repository: {str(e)}",
        }

    logger.info("Updated infrastructure config: %s", infra_config)
    secrets_client.put_secret_value(
        SecretId=DEPLOYMENT_SECRET_ARN, SecretString=json.dumps(infra_config.to_dict())
    )
    try:
        cf_service = CloudFormationService(cloudformation_client)
        cf_service.destroy_stack(stack_name=STACK_NAME_TEMPLATE.format(event.name))
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"message": "Deployment deletion started."}),
        }
    except Exception as e:
        logger.error("Error deleting deployment: %s", str(e))
        return {
            "statusCode": 500,
            "body": f"Error deleting deployment: {str(e)}",
        }


def _handle_poll(execution_id: str) -> Dict[str, Any]:
    try:
        execution_response = codepipeline_client.get_pipeline_execution(
            pipelineName=PIPELINE_NAME, pipelineExecutionId=execution_id
        )
    except codepipeline_client.exceptions.PipelineExecutionNotFoundException:
        return {
            "statusCode": 404,
            "body": "Deployment not found.",
        }
    except Exception as e:
        logger.error("Error fetching pipeline execution: %s", str(e))
        return {
            "statusCode": 500,
            "body": f"Error fetching pipeline execution: {str(e)}",
        }

    pipeline_execution = execution_response.get("pipelineExecution", {})
    status = pipeline_execution.get("status", "UNKNOWN")
    error: Optional[str] = None
    if status in ("Failed", "Stopped"):
        error = pipeline_execution.get("statusSummary") or None

    stages: List[StageStatus] = []
    try:
        state_response = codepipeline_client.get_pipeline_state(
            pipelineName=PIPELINE_NAME
        )
        for stage_state in state_response.get("stageStates", []):
            latest = stage_state.get("latestExecution")
            if not latest:
                continue
            if latest.get("pipelineExecutionId") != execution_id:
                continue
            last_update = latest.get("lastStatusChange")
            if last_update is not None:
                try:
                    last_update = last_update.isoformat()
                except Exception:
                    last_update = str(last_update)
            stages.append(
                StageStatus(
                    name=stage_state.get("stageName", ""),
                    status=latest.get("status", "UNKNOWN"),
                    lastUpdate=last_update,
                )
            )
    except Exception as e:
        logger.warning("Error fetching pipeline state: %s", str(e))

    deployment_status = DeploymentStatus(
        executionId=execution_id, status=status, stages=stages, error=error
    )
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(asdict(deployment_status)),
    }


def handler(event: Dict[str, Any], ctx) -> Dict[str, Any]:
    logger.info("Received event: %s", event)
    method, path = _normalize_route(event)
    oauth_token = get_oauth_token_from_secret_arn(
        secrets_client, GITHUB_OAUTH_TOKEN_ARN
    )
    if method == "POST" and path.endswith("/deploy"):
        request = DeployCreateRequest.from_event(event)
        if request.is_empty():
            return {
                "statusCode": 400,
                "body": "Invalid request body.",
            }
        return _handle_deploy(request, oauth_token)
    if method == "DELETE" and path.endswith("/deployment"):
        request = DeployDeleteRequest.from_event(event)
        if request.is_empty():
            return {
                "statusCode": 400,
                "body": "Invalid request body.",
            }
        return _handle_delete(request, oauth_token)
    if method == "GET" and "/deployment/" in path:
        execution_id = _get_execution_id(event, path)
        if not execution_id:
            return {
                "statusCode": 400,
                "body": "Missing executionId.",
            }
        return _handle_poll(execution_id)
    return {
        "statusCode": 404,
        "body": "Not found.",
    }
