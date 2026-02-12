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


def _get_cors_headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
    }


def _build_response(status_code: int, body: Any) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": _get_cors_headers(),
        "body": json.dumps(body) if not isinstance(body, str) else body,
    }


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
    return _build_response(
        200,
        {"message": "Pipeline execution started.", "pipelineExecutionId": execution_id},
    )


def _handle_deploy(
    raw_event, event: DeployCreateRequest, oauth_token: str
) -> Dict[str, Any]:
    try:
        infra_config = _load_infra_config()
    except Exception as e:
        return _build_response(500, f"Error loading secret: {str(e)}")

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
        return _build_response(500, f"Error starting pipeline: {str(e)}")


def _handle_delete(
    raw_event, event: DeployDeleteRequest, oauth_token: str
) -> Dict[str, Any]:
    try:
        infra_config = _load_infra_config()
    except Exception as e:
        return _build_response(500, f"Error loading secret: {str(e)}")

    updated_websites = [
        website
        for website in infra_config.WEBSITES
        if not (
            website.githubRepositoryName == event.githubRepositoryName
            and website.subdomain == event.subdomain
        )
    ]
    if len(updated_websites) == len(infra_config.WEBSITES):
        return _build_response(404, "Deployment not found.")
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
        return _build_response(500, f"Error deleting GitHub repository: {str(e)}")

    logger.info("Updated infrastructure config: %s", infra_config)
    secrets_client.put_secret_value(
        SecretId=DEPLOYMENT_SECRET_ARN, SecretString=json.dumps(infra_config.to_dict())
    )
    try:
        cf_service = CloudFormationService(cloudformation_client)
        cf_service.destroy_stack(stack_name=STACK_NAME_TEMPLATE.format(event.name))
        return _build_response(200, {"message": "Deployment deletion started."})
    except Exception as e:
        logger.error("Error deleting deployment: %s", str(e))
        return _build_response(500, f"Error deleting deployment: {str(e)}")


def _handle_poll(event, execution_id: str) -> Dict[str, Any]:
    try:
        execution_response = codepipeline_client.get_pipeline_execution(
            pipelineName=PIPELINE_NAME, pipelineExecutionId=execution_id
        )
    except codepipeline_client.exceptions.PipelineExecutionNotFoundException:
        return _build_response(404, "Deployment not found.")
    except Exception as e:
        logger.error("Error fetching pipeline execution: %s", str(e))
        return _build_response(500, f"Error fetching pipeline execution: {str(e)}")

    pipeline_execution = execution_response.get("pipelineExecution", {})
    status = pipeline_execution.get("status", "UNKNOWN")
    error: Optional[str] = None
    if status in ("Failed", "Stopped"):
        error = pipeline_execution.get("statusSummary") or None

    stages: List[StageStatus] = []
    try:
        action_executions = codepipeline_client.list_action_executions(
            pipelineName=PIPELINE_NAME, filter={"pipelineExecutionId": execution_id}
        )

        stage_map = {}
        for action in action_executions.get("actionExecutionDetails", []):
            stage_name = action.get("stageName")
            action_status = action.get("status", "UNKNOWN")
            last_update = action.get("lastUpdateTime")

            if stage_name not in stage_map:
                stage_map[stage_name] = {
                    "status": action_status,
                    "lastUpdate": last_update,
                    "actions": [],
                }

            stage_map[stage_name]["actions"].append(
                {"status": action_status, "lastUpdate": last_update}
            )
            current_stage_status = stage_map[stage_name]["status"]
            if action_status == "Failed" or current_stage_status == "Failed":
                stage_map[stage_name]["status"] = "Failed"
            elif action_status == "InProgress" and current_stage_status != "Failed":
                stage_map[stage_name]["status"] = "InProgress"
            elif action_status == "Succeeded" and current_stage_status not in (
                "Failed",
                "InProgress",
            ):
                stage_map[stage_name]["status"] = "Succeeded"
            if last_update and (
                not stage_map[stage_name]["lastUpdate"]
                or last_update > stage_map[stage_name]["lastUpdate"]
            ):
                stage_map[stage_name]["lastUpdate"] = last_update

        for stage_name, details in stage_map.items():
            last_update = details["lastUpdate"]
            if last_update is not None:
                try:
                    last_update = last_update.isoformat()
                except Exception:
                    last_update = str(last_update)

            stages.append(
                StageStatus(
                    name=stage_name,
                    status=details["status"],
                    lastUpdate=last_update,
                )
            )
        stages.sort(key=lambda s: s.name)

    except Exception as e:
        logger.warning("Error fetching action executions: %s", str(e))

    deployment_status = DeploymentStatus(
        executionId=execution_id, status=status, stages=stages, error=error
    )
    return _build_response(200, asdict(deployment_status))


def _handle_list_deployments(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        infra_config = _load_infra_config()
        websites = [asdict(w) for w in infra_config.WEBSITES]
        return _build_response(200, websites)
    except Exception as e:
        logger.error("Error listing deployments: %s", str(e))
        return _build_response(500, f"Error listing deployments: {str(e)}")


def handler(event: Dict[str, Any], ctx) -> Dict[str, Any]:
    try:
        logger.info("Received event: %s", event)
        method, path = _normalize_route(event)

        if method == "OPTIONS":
            return _build_response(200, "OK")

        oauth_token = get_oauth_token_from_secret_arn(
            secrets_client, GITHUB_OAUTH_TOKEN_ARN
        )
        if method == "POST" and path.endswith("/deploy"):
            request = DeployCreateRequest.from_event(event)
            if request.is_empty():
                return _build_response(400, "Invalid request body.")
            return _handle_deploy(event, request, oauth_token)

        if method == "DELETE" and path.endswith("/deployment"):
            request = DeployDeleteRequest.from_event(event)
            if request.is_empty():
                return _build_response(400, "Invalid request body.")
            return _handle_delete(event, request, oauth_token)

        if method == "GET" and "/deployment/" in path:
            execution_id = _get_execution_id(event, path)
            if not execution_id:
                return _build_response(400, "Missing executionId.")
            return _handle_poll(event, execution_id)

        if method == "GET" and path.endswith("/deployments"):
            return _handle_list_deployments(event)

        return _build_response(404, "Not found.")
    except Exception as e:
        logger.error("Unhandled exception in handler: %s", str(e), exc_info=True)
        return _build_response(500, f"Internal server error: {str(e)}")
