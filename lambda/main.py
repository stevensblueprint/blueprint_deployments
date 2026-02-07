import boto3
import json
import logging
from typing import Dict, Any
from utils import load_safe_env, _parse_request_body
from models import InfraConfig, WebsiteConfig, Template
from services import GithubService

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets_client = boto3.client("secretsmanager")
codepipeline_client = boto3.client("codepipeline")

DEPLOYMENT_SECRET_ARN = load_safe_env("DEPLOYMENT_SECRET_ARN")
PIPELINE_NAME = load_safe_env("PIPELINE_NAME")
GITHUB_OAUTH_TOKEN = load_safe_env("GITHUB_OAUTH_TOKEN")
ORGANIZATION_NAME = "stevensblueprint"


def handler(event, ctx) -> Dict[str, Any]:
    logger.info("Received event: %s", event)
    new_website_config = WebsiteConfig.get_empty()
    try:
        payload = _parse_request_body(event)
        if payload:
            logger.info("Parsed request body: %s", payload)
            new_website_config = WebsiteConfig.from_dict(payload)
            logger.info("Parsed new website config: %s", new_website_config)
    except Exception as e:
        logger.error("Invalid request body: %s", str(e))
        return {
            "statusCode": 400,
            "body": "Invalid request body.",
        }
    infra_config: InfraConfig = InfraConfig.get_empty()
    try:
        secret_value_response = secrets_client.get_secret_value(
            SecretId=DEPLOYMENT_SECRET_ARN
        )
        secret_string = secret_value_response.get("SecretString", "")
        logger.info("Successfully retrieved secret: %s", secret_string)
    except Exception as e:
        logger.error("Error retrieving secret: %s", str(e))
        return {
            "statusCode": 500,
            "body": f"Error retrieving secret: {str(e)}",
        }

    if infra_config.is_empty() or new_website_config.is_empty():
        logger.warning(
            "No configuration provided in the request body, using secret value."
        )
        try:
            infra_config = InfraConfig.from_dict(json.loads(secret_string))
        except Exception as e:
            logger.error("Error parsing secret JSON: %s", str(e))
            return {
                "statusCode": 500,
                "body": f"Error parsing secret JSON: {str(e)}",
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

    infra_config.WEBSITES.append(new_website_config)
    logger.info("Updated infrastructure config: %s", infra_config)
    secrets_client.put_secret_value(
        SecretId=DEPLOYMENT_SECRET_ARN, SecretString=json.dumps(infra_config.__dict__)
    )
    try:
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
    except Exception as e:
        logger.error("Error starting pipeline: %s", str(e))
        return {
            "statusCode": 500,
            "body": f"Error starting pipeline: {str(e)}",
        }
