import boto3
import json
from services import GithubService
from utils import get_oauth_token_from_secret_arn, load_safe_env
from models import InfraConfig
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

DEPLOYMENT_SECRET_ARN = load_safe_env("DEPLOYMENT_SECRET_ARN")
cfn = boto3.client("cloudformation")
secrets_client = boto3.client("secretsmanager")


def _load_infra_config() -> InfraConfig:
    try:
        secret_value_response = secrets_client.get_secret_value(
            SecretId=DEPLOYMENT_SECRET_ARN
        )
        logger.info(
            "Retrieved deployment secret metadata (VersionId=%s, CreatedDate=%s).",
            secret_value_response.get("VersionId"),
            secret_value_response.get("CreatedDate"),
        )
        secret_string = secret_value_response.get("SecretString")
        if not secret_string and secret_value_response.get("SecretBinary"):
            secret_string = secret_value_response.get("SecretBinary", "").decode(
                "utf-8"
            )
        logger.info("Successfully loaded deployment secret payload.")
    except Exception as e:
        logger.error("Error retrieving deployment secret: %s", str(e))
        raise

    try:
        normalized = (secret_string or "").strip()
        if not normalized:
            normalized = "{}"
        return InfraConfig.from_dict(json.loads(normalized))
    except Exception as e:
        logger.error("Error parsing secret JSON: %s", str(e))
        raise


def handler(event, context):
    logger.info(
        "Lambda invoked (request_id=%s, function=%s).",
        getattr(context, "aws_request_id", "unknown"),
        getattr(context, "function_name", "unknown"),
    )
    logger.info("Received event detail keys: %s", list(event.get("detail", {}).keys()))
    stack_name = event["detail"]["stack-id"].split("/")[-2]
    if not stack_name.endswith("-website-stack"):
        logger.info("Ignoring non-website stack event for stack '%s'.", stack_name)
        return {"status": "ignored", "stack": stack_name}
    logger.info("Processing stack '%s'.", stack_name)
    response = cfn.describe_stacks(StackName=stack_name)
    stack = response["Stacks"][0]
    outputs = {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}
    logger.info("Stack outputs loaded: %s", list(outputs.keys()))
    secret_map = {
        "S3_BUCKET": outputs.get("S3BucketName"),
        "DISTRIBUTION_ID": outputs.get("CloudFrontDistributionId"),
        "AWS_REGION": load_safe_env("AWS_REGION"),
        "AWS_ACCOUNT_ID": context.invoked_function_arn.split(":")[4],
    }
    infra_config = _load_infra_config()
    website_name = stack_name.replace("blueprint-", "").replace("-website-stack", "")
    logger.info("Resolved website name '%s' from stack '%s'.", website_name, stack_name)
    matching_site = next(
        (site for site in infra_config.WEBSITES if site.name == website_name), None
    )
    if not matching_site:
        logger.error(
            "No website config found for '%s' (stack '%s').",
            website_name,
            stack_name,
        )
        raise ValueError(
            f"Website config not found for name '{website_name}' from stack '{stack_name}'"
        )
    repo_suffix = matching_site.githubRepositoryName
    repo_full_name = f"{infra_config.GITHUB_OWNER}/{repo_suffix}"
    logger.info("Target GitHub repo resolved: %s.", repo_full_name)
    token = get_oauth_token_from_secret_arn(
        secrets_client, load_safe_env("GITHUB_OAUTH_TOKEN_ARN")
    )
    gh = GithubService(token=token)

    for key, val in secret_map.items():
        if val:
            logger.info("Updating GitHub secret '%s' for repo '%s'.", key, repo_full_name)
            gh.create_or_update_secret(repo_full_name, key, val)
        else:
            logger.warning(
                "Skipping GitHub secret '%s' for repo '%s' due to empty value.",
                key,
                repo_full_name,
            )
    logger.info("Triggering deployment workflow for repo '%s'.", repo_full_name)
    gh.trigger_workflow(repo_full_name, "deploy.yml")

    logger.info("Deployment notification flow completed for repo '%s'.", repo_full_name)

    return {"status": "success", "repo": repo_full_name}
