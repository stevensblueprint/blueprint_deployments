import boto3
import json
import logging
from dataclasses import replace
from typing import Dict, Any, Tuple
from utils import load_safe_env, _parse_request_body
from models import InfraConfig, WebsiteConfig, Template
from services import GithubService, CloudFormationService

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets_client = boto3.client("secretsmanager")
codepipeline_client = boto3.client("codepipeline")
cloudformation_client = boto3.client("cloudformation")

DEPLOYMENT_SECRET_ARN = load_safe_env("DEPLOYMENT_SECRET_ARN")
PIPELINE_NAME = load_safe_env("PIPELINE_NAME")
GITHUB_OAUTH_TOKEN = load_safe_env("GITHUB_OAUTH_TOKEN")
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
        secret_string = secret_value_response.get("SecretString", "")
        logger.info("Successfully retrieved secret.")
    except Exception as e:
        logger.error("Error retrieving secret: %s", str(e))
        raise

    try:
        return InfraConfig.from_dict(json.loads(secret_string or "{}"))
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


def _handle_deploy(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        payload = _parse_request_body(event)
        if not payload:
            raise ValueError("Request body is required.")
        logger.info("Parsed request body: %s", payload)
        new_website_config = WebsiteConfig.from_dict(payload)
        logger.info("Parsed new website config: %s", new_website_config)
    except Exception as e:
        logger.error("Invalid request body: %s", str(e))
        return {
            "statusCode": 400,
            "body": "Invalid request body.",
        }

    try:
        infra_config = _load_infra_config()
    except Exception as e:
        return {
            "statusCode": 500,
            "body": f"Error loading secret: {str(e)}",
        }

    logger.info("Creating github repository with config: %s", infra_config)
    github_service = GithubService(token=GITHUB_OAUTH_TOKEN)
    github_service.create_respository_from_template(
        repo_name=f"{ORGANIZATION_NAME}/{new_website_config.githubRepositoryName}",
        template=Template.VITE,
        private=False,
    )
    logger.info(
        "Successfully created GitHub repository: %s/%s",
        ORGANIZATION_NAME,
        new_website_config.githubRepositoryName,
    )

    infra_config = replace(
        infra_config, WEBSITES=[*infra_config.WEBSITES, new_website_config]
    )
    logger.info("Updated infrastructure config: %s", infra_config)
    secrets_client.put_secret_value(
        SecretId=DEPLOYMENT_SECRET_ARN, SecretString=json.dumps(infra_config.__dict__)
    )

    try:
        return _start_pipeline()
    except Exception as e:
        logger.error("Error starting pipeline: %s", str(e))
        return {
            "statusCode": 500,
            "body": f"Error starting pipeline: {str(e)}",
        }


def _handle_delete(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        payload = _parse_request_body(event)
        if not payload:
            raise ValueError("Request body is required.")
        logger.info("Parsed request body: %s", payload)
        github_repository_name = payload["githubRepositoryName"]
        subdomain = payload["subdomain"]
    except Exception as e:
        logger.error("Invalid request body: %s", str(e))
        return {
            "statusCode": 400,
            "body": "Invalid request body.",
        }

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
            website.githubRepositoryName == github_repository_name
            and website.subdomain == subdomain
        )
    ]
    if len(updated_websites) == len(infra_config.WEBSITES):
        return {
            "statusCode": 404,
            "body": "Deployment not found.",
        }
    infra_config = replace(infra_config, WEBSITES=updated_websites)

    github_service = GithubService(token=GITHUB_OAUTH_TOKEN)
    try:
        deleted = github_service.delete_repository(
            repo_name=f"{ORGANIZATION_NAME}/{github_repository_name}"
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
        SecretId=DEPLOYMENT_SECRET_ARN, SecretString=json.dumps(infra_config.__dict__)
    )
    try:
        cf_service = CloudFormationService(cloudformation_client)
        cf_service.destroy_stack(
            stack_name=STACK_NAME_TEMPLATE.format(github_repository_name)
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


def handler(event, ctx) -> Dict[str, Any]:
    logger.info("Received event: %s", event)
    method, route = _normalize_route(event)
    if method == "POST" and route == "deploy":
        return _handle_deploy(event)
    if method == "DELETE" and route == "deployment":
        return _handle_delete(event)
    return {
        "statusCode": 404,
        "body": "Not found.",
    }
