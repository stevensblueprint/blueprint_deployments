import boto3
import json
from services import GithubService
from utils import get_oauth_token_from_secret_arn, load_safe_env
from models import InfraConfig
import logging

logger = logging.getLogger()
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


def handler(event, context):
    stack_name = event["detail"]["stack-id"].split("/")[-2]
    if not stack_name.endswith("-website-stack"):
        logger.info(
            "Ignoring non-website stack event for stack '%s'.", stack_name
        )
        return {"status": "ignored", "stack": stack_name}
    response = cfn.describe_stacks(StackName=stack_name)
    stack = response["Stacks"][0]
    outputs = {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}
    secret_map = {
        "S3_BUCKET": outputs.get("S3BucketName"),
        "DISTRIBUTION_ID": outputs.get("CloudFrontDistributionId"),
        "AWS_REGION": load_safe_env("AWS_REGION"),
        "AWS_ACCOUNT_ID": context.invoked_function_arn.split(":")[4],
    }
    infra_config = _load_infra_config()
    # Logic: "blueprint-my-repo-website-stack" -> website name "my-repo"
    website_name = stack_name.replace("blueprint-", "").replace("-website-stack", "")
    matching_site = next(
        (site for site in infra_config.WEBSITES if site.name == website_name), None
    )
    if not matching_site:
        raise ValueError(
            f"Website config not found for name '{website_name}' from stack '{stack_name}'"
        )
    repo_suffix = matching_site.githubRepositoryName
    repo_full_name = f"{infra_config.GITHUB_OWNER}/{repo_suffix}"
    token = get_oauth_token_from_secret_arn(
        secrets_client, load_safe_env("GITHUB_OAUTH_TOKEN_ARN")
    )
    gh = GithubService(token=token)

    for key, val in secret_map.items():
        if val:
            gh.create_or_update_secret(repo_full_name, key, val)
    gh.trigger_workflow(repo_full_name, "deploy.yml")

    return {"status": "success", "repo": repo_full_name}
