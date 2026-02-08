import boto3
import json
import logging
from dataclasses import replace, asdict
from typing import Dict, Any, Tuple
from utils import load_safe_env, get_oauth_token_from_secret_arn
from models import (
    InfraConfig,
    WebsiteConfig,
    Template,
    DeployCreateRequest,
    DeployDeleteRequest,
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
    last_segment = path.rsplit("/", 1)[-1] if path else ""
    return method, last_segment


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
        cf_service.destroy_stack(
            stack_name=STACK_NAME_TEMPLATE.format(event.githubRepositoryName)
        )
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"message": "Deployment deleted successfully."}),
        }
    except Exception as e:
        logger.error("Error deleting deployment: %s", str(e))
        return {
            "statusCode": 500,
            "body": f"Error deleting deployment: {str(e)}",
        }


def handler(event: Dict[str, Any], ctx) -> Dict[str, Any]:
    logger.info("Received event: %s", event)
    method, route = _normalize_route(event)
    oauth_token = get_oauth_token_from_secret_arn(
        secrets_client, GITHUB_OAUTH_TOKEN_ARN
    )
    if method == "POST" and route == "deploy":
        request = DeployCreateRequest.from_event(event)
        if request.is_empty():
            return {
                "statusCode": 400,
                "body": "Invalid request body.",
            }
        return _handle_deploy(request, oauth_token)
    if method == "DELETE" and route == "deployment":
        request = DeployDeleteRequest.from_event(event)
        if request.is_empty():
            return {
                "statusCode": 400,
                "body": "Invalid request body.",
            }
        return _handle_delete(request, oauth_token)
    return {
        "statusCode": 404,
        "body": "Not found.",
    }
