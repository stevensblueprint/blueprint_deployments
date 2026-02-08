import base64
from typing import cast
from nacl import public, encoding
import requests


class GithubService:
    def __init__(self, token: str, api_base: str = "https://api.github.com"):
        if token is None or token.strip() == "":
            raise ValueError("GitHub token is required.")
        self.token = token.strip()
        self.api_base = api_base.rstrip("/")
        self.session = self._create_session()

    def _create_session(self):
        session = requests.Session()
        session.headers.update(
            {
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
            }
        )
        return session

    def _encrypt_secret(self, public_key: str, secret_value: str) -> str:
        """Encrypt a Unicode string using the public key."""
        encoder = cast(encoding.Encoder, encoding.Base64Encoder)
        public_key_obj = public.PublicKey(public_key.encode("utf-8"), encoder)
        sealed_box = public.SealedBox(public_key_obj)
        encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
        return base64.b64encode(encrypted).decode("utf-8")

    def create_or_update_secret(self, repo_name: str, secret_name: str, value: str):
        key_res = self.session.get(
            f"https://api.github.com/repos/{repo_name}/actions/secrets/public-key"
        )
        key_data = key_res.json()
        encrypted_value = self._encrypt_secret(key_data["key"], value)
        self.session.put(
            f"https://api.github.com/repos/{repo_name}/actions/secrets/{secret_name}",
            json={"encrypted_value": encrypted_value, "key_id": key_data["key_id"]},
        )

    def trigger_workflow(self, repo_name: str, workflow_file: str = "main.yml"):
        return self.session.post(
            f"https://api.github.com/repos/{repo_name}/actions/workflows/{workflow_file}/dispatches",
            json={"ref": "main"},
        )
