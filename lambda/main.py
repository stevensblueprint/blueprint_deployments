import boto3
import json
import logging
from typing import Dict, Any
from utils import load_safe_env

logger = logging.getLogger()
logger.setLevel(logging.INFO)

secrets_client = boto3.client("secretsmanager")
codepipeline_client = boto3.client("codepipeline")
DEPLOYMENT_SECRET_ARN = load_safe_env("DEPLOYMENT_SECRET_ARN")
PIPELINE_NAME = load_safe_env("PIPELINE_NAME")


def handler(event, ctx) -> Dict[str, Any]:
    logger.info("Received event: %s", event)
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
    try:
        body = event.get("body")
        if body:
            json.loads(body)
    except Exception as e:
        logger.error("Invalid JSON body: %s", str(e))
        return {
            "statusCode": 400,
            "body": "Invalid JSON body.",
        }

    try:
        response = codepipeline_client.start_pipeline_execution(
            name=PIPELINE_NAME
        )
        execution_id = response.get("pipelineExecutionId", "")
        return {
            "statusCode": 200,
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
