import os
import base64
import json
from typing import Dict, Any


def load_safe_env(env_var_name: str) -> str:
    """Load an environment variable and ensure it is not None or empty."""
    value = os.getenv(env_var_name)
    if value is None or value.strip() == "":
        raise ValueError(
            f"Environment variable '{env_var_name}' is not set or is empty."
        )
    return value


def _parse_request_body(event: Dict[str, Any]) -> Dict[str, Any]:
    body = event.get("body")
    if body is None:
        return {}
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    if isinstance(body, str):
        return json.loads(body) if body else {}
    return body
