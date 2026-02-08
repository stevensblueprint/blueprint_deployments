import os
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def load_safe_env(env_var_name: str) -> str:
    """Load an environment variable and ensure it is not None or empty."""
    value = os.getenv(env_var_name)
    if value is None or value.strip() == "":
        logger.error("Required environment variable '%s' is missing or empty.", env_var_name)
        raise ValueError(
            f"Environment variable '{env_var_name}' is not set or is empty."
        )
    logger.info("Loaded environment variable '%s'.", env_var_name)
    return value


def get_oauth_token_from_secret_arn(secrets_client, secret_arn: str) -> str:
    try:
        secret_value_response = secrets_client.get_secret_value(SecretId=secret_arn)
        logger.info("Successfully retrieved OAuth secret for ARN: %s", secret_arn)
        secret_string = secret_value_response.get("SecretString", "")
        if not secret_string:
            raise ValueError(f"Secret '{secret_arn}' has no string value.")
        try:
            secret_data = json.loads(secret_string)
        except json.JSONDecodeError:
            secret_data = None
        if isinstance(secret_data, dict):
            oauth_token = secret_data.get("GITHUB_OAUTH_TOKEN")
            if not oauth_token:
                raise ValueError(
                    f"Secret '{secret_arn}' does not contain 'GITHUB_OAUTH_TOKEN'."
                )
            return oauth_token
        return secret_string
    except Exception as e:
        logger.error("Error retrieving OAuth token from secret ARN '%s': %s", secret_arn, str(e))
        raise RuntimeError(f"Error retrieving OAuth token from secret: {str(e)}")
