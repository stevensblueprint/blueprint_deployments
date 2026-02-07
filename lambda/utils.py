import os


def load_safe_env(env_var_name: str) -> str:
    """Load an environment variable and ensure it is not None or empty."""
    value = os.getenv(env_var_name)
    if value is None or value.strip() == "":
        raise ValueError(
            f"Environment variable '{env_var_name}' is not set or is empty."
        )
    return value
