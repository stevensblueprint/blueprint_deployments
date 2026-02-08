from dataclasses import dataclass, asdict
from typing import Dict, Any, List
from enum import Enum
import json
import base64


class Template(Enum):
    VITE = "vite-react-template"


@dataclass(frozen=True)
class DeployCreateRequest:
    name: str
    subdomain: str
    githubRepositoryName: str
    githubBranchName: str
    requiresAuth: bool

    def is_empty(self) -> bool:
        return not any(
            getattr(self, field.name) for field in self.__dataclass_fields__.values()
        )

    @staticmethod
    def get_empty() -> "DeployCreateRequest":
        return DeployCreateRequest(
            name="",
            subdomain="",
            githubRepositoryName="",
            githubBranchName="",
            requiresAuth=False,
        )

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "DeployCreateRequest":
        return DeployCreateRequest(
            name=data["name"],
            subdomain=data["subdomain"],
            githubRepositoryName=data["githubRepositoryName"],
            githubBranchName=data["githubBranchName"],
            requiresAuth=data["requiresAuth"],
        )

    @staticmethod
    def from_event(event: Dict[str, Any]) -> "DeployCreateRequest":
        body = event.get("body")
        if body is None:
            return DeployCreateRequest.get_empty()
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode("utf-8")
        if isinstance(body, str):
            return DeployCreateRequest.from_dict(json.loads(body))
        return body


@dataclass(frozen=True)
class DeployDeleteRequest:
    name: str
    githubRepositoryName: str
    subdomain: str

    def is_empty(self) -> bool:
        return not any(
            getattr(self, field.name) for field in self.__dataclass_fields__.values()
        )

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "DeployDeleteRequest":
        return DeployDeleteRequest(
            name=data["name"],
            githubRepositoryName=data["githubRepositoryName"],
            subdomain=data["subdomain"],
        )

    @staticmethod
    def from_event(event: Dict[str, Any]) -> "DeployDeleteRequest":
        body = event.get("body")
        if body is None:
            return DeployDeleteRequest(name="", githubRepositoryName="", subdomain="")
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode("utf-8")
        if isinstance(body, str):
            return DeployDeleteRequest.from_dict(json.loads(body))
        return DeployDeleteRequest.from_dict(body)


@dataclass(frozen=True)
class WebsiteConfig:
    name: str
    subdomain: str
    githubRepositoryName: str
    githubBranchName: str
    requiresAuth: bool
    includeRootDomain: bool = False

    def is_empty(self) -> bool:
        return not any(
            getattr(self, field.name) for field in self.__dataclass_fields__.values()
        )

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "WebsiteConfig":
        return WebsiteConfig(
            name=data["name"],
            subdomain=data["subdomain"],
            githubRepositoryName=data["githubRepositoryName"],
            githubBranchName=data["githubBranchName"],
            requiresAuth=data["requiresAuth"],
            includeRootDomain=data.get("includeRootDomain", False),
        )

    @staticmethod
    def get_empty() -> "WebsiteConfig":
        return WebsiteConfig(
            name="",
            subdomain="",
            githubRepositoryName="",
            githubBranchName="",
            requiresAuth=False,
            includeRootDomain=False,
        )


@dataclass(frozen=True)
class InfraConfig:
    ACCOUNT_ID: str
    AWS_REGION: str
    DOMAIN_NAME: str
    SENDER_EMAIL: str
    RECIPIENT_EMAILS: List[str]
    CERTIFICATE_ARN: str
    GITHUB_OWNER: str
    WEBSITES: List[WebsiteConfig]
    NOTION_TOKEN: str

    def is_empty(self) -> bool:
        return all(
            not getattr(self, field.name)
            for field in self.__dataclass_fields__.values()
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary suitable for JSON serialization and reloading."""
        return {
            "ACCOUNT_ID": self.ACCOUNT_ID,
            "AWS_REGION": self.AWS_REGION,
            "DOMAIN_NAME": self.DOMAIN_NAME,
            "SENDER_EMAIL": self.SENDER_EMAIL,
            "RECIPIENT_EMAILS": ",".join(self.RECIPIENT_EMAILS),
            "CERTIFICATE_ARN": self.CERTIFICATE_ARN,
            "GITHUB_OWNER": self.GITHUB_OWNER,
            "WEBSITES": [asdict(w) for w in self.WEBSITES],
            "NOTION_TOKEN": self.NOTION_TOKEN,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "InfraConfig":
        recipient_emails = data["RECIPIENT_EMAILS"]
        # Handle both string (CSV) and list formats
        if isinstance(recipient_emails, str):
            recipient_emails = [
                email.strip() for email in recipient_emails.split(",") if email.strip()
            ]
        elif isinstance(recipient_emails, list):
            recipient_emails = [
                email.strip() for email in recipient_emails if email.strip()
            ]

        return InfraConfig(
            ACCOUNT_ID=data["ACCOUNT_ID"],
            AWS_REGION=data["AWS_REGION"],
            DOMAIN_NAME=data["DOMAIN_NAME"],
            SENDER_EMAIL=data["SENDER_EMAIL"],
            RECIPIENT_EMAILS=recipient_emails,
            CERTIFICATE_ARN=data["CERTIFICATE_ARN"],
            GITHUB_OWNER=data["GITHUB_OWNER"],
            WEBSITES=[WebsiteConfig.from_dict(w) for w in data.get("WEBSITES", [])],
            NOTION_TOKEN=data["NOTION_TOKEN"],
        )

    @staticmethod
    def get_empty() -> "InfraConfig":
        return InfraConfig(
            ACCOUNT_ID="",
            AWS_REGION="",
            DOMAIN_NAME="",
            SENDER_EMAIL="",
            RECIPIENT_EMAILS=[],
            CERTIFICATE_ARN="",
            GITHUB_OWNER="",
            WEBSITES=[],
            NOTION_TOKEN="",
        )
