import os
import json
import urllib.request
import urllib.error
from typing import Any, Dict, Tuple
from models import Template


class GithubService:
    def __init__(self, token: str, api_base: str = "https://api.github.com"):
        if token is None or token.strip() == "":
            raise ValueError("GitHub token is required.")
        self.token = token.strip()
        self.api_base = api_base.rstrip("/")

    def create_repository_from_template(
        self,
        repo_name: str,
        template: Template,
        private: bool = True,
        description: str = "Repo created from a template",
        include_all_branches: bool = False,
    ) -> Dict[str, Any]:
        template_owner, template_repo = self._resolve_template_owner_and_repo(template)
        owner, name = self._resolve_target_owner_and_name(repo_name)

        url = f"{self.api_base}/repos/{template_owner}/{template_repo}/generate"
        payload = {
            "owner": owner,
            "name": name,
            "description": description,
            "include_all_branches": include_all_branches,
            "private": private,
        }
        return self._post_json(url, payload)

    def create_respository_from_template(
        self, repo_name: str, template: Template, private: bool = True
    ) -> Dict[str, Any]:
        return self.create_repository_from_template(repo_name, template, private)

    def _resolve_target_owner_and_name(self, repo_name: str) -> Tuple[str, str]:
        if "/" in repo_name:
            owner_name, name = repo_name.split("/", 1)
            return owner_name, name

        owner_name = os.getenv("GITHUB_OWNER", "").strip()
        if not owner_name:
            raise ValueError(
                "GITHUB_OWNER is required when repo_name is not in 'owner/name' form."
            )
        return owner_name, repo_name

    def _resolve_template_owner_and_repo(self, template: Template) -> Tuple[str, str]:
        template_value = template.value
        if "/" in template_value:
            return tuple(template_value.split("/", 1))  # type: ignore[return-value]

        template_owner = os.getenv("GITHUB_TEMPLATE_OWNER", "").strip()
        if not template_owner:
            template_owner = os.getenv("GITHUB_OWNER", "").strip()
        if not template_owner:
            raise ValueError(
                "GITHUB_TEMPLATE_OWNER or GITHUB_OWNER is required to resolve template."
            )
        return template_owner, template_value

    def _post_json(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            raise RuntimeError(
                f"GitHub API error {e.code} for {url}: {body or e.reason}"
            ) from e
