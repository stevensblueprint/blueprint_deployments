import os
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def load_safe_env(env_var_name: str) -> str:
    """Load an environment variable and ensure it is not None or empty."""
    value = os.getenv(env_var_name)
    if value is None or value.strip() == "":
        raise ValueError(
            f"Environment variable '{env_var_name}' is not set or is empty."
        )
    return value


def get_oauth_token_from_secret_arn(secrets_client, secret_arn: str) -> str:
    try:
        secret_value_response = secrets_client.get_secret_value(SecretId=secret_arn)
        logger.info(f"Successfully retrieved secret for ARN: {secret_arn}")
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
        raise RuntimeError(f"Error retrieving OAuth token from secret: {str(e)}")
