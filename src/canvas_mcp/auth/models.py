"""Data models and exception hierarchy for Canvas mobile OAuth."""

from datetime import UTC
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)
from pydantic.types import AwareDatetime


class OAuthError(Exception):
    """Base exception for OAuth-related failures."""


class OAuthRefreshError(OAuthError):
    """Raised when refreshing an expired OAuth access token fails."""


class ReauthenticationRequired(OAuthRefreshError):
    """Raised when an OAuth refresh token is rejected and the user must re-authenticate."""


class TokenStoreError(OAuthError):
    """Raised when reading or writing local OAuth token storage fails."""


class TokenStoreConflict(TokenStoreError):
    """Raised when a concurrent write modified the stored tokens for a domain."""


class OAuthUser(BaseModel):
    """User identity returned by Canvas OAuth or user endpoints."""

    model_config = ConfigDict(extra="ignore")

    id: int = Field(..., strict=True)
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("user name cannot be empty")
        return v


class MobileCredentials(BaseModel):
    """Discovered mobile client credentials from Canvas SSO mobile verify."""

    model_config = ConfigDict(extra="ignore")

    client_id: str
    client_secret: SecretStr
    base_url: str

    @field_validator("client_id")
    @classmethod
    def validate_client_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("client_id cannot be empty")
        return v

    @field_validator("client_secret")
    @classmethod
    def validate_client_secret(cls, v: SecretStr) -> SecretStr:
        if not v.get_secret_value().strip():
            raise ValueError("client_secret cannot be empty")
        return v

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("base_url cannot be empty")
        return v


class StoredTokens(BaseModel):
    """Token set and metadata stored for a specific Canvas domain."""

    model_config = ConfigDict(extra="ignore")

    canvas_domain: str
    access_token: SecretStr
    refresh_token: SecretStr
    client_id: str
    client_secret: SecretStr
    obtained_at: AwareDatetime
    last_refreshed_at: AwareDatetime
    user: OAuthUser | None = None

    @field_validator("canvas_domain", "client_id")
    @classmethod
    def validate_nonempty_strings(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("field cannot be empty")
        return v

    @field_validator("access_token", "refresh_token", "client_secret")
    @classmethod
    def validate_nonempty_secrets(cls, v: SecretStr) -> SecretStr:
        if not v.get_secret_value().strip():
            raise ValueError("secret cannot be empty")
        return v

    def to_store_dict(self) -> dict[str, Any]:
        """Convert entry to JSON-serializable dictionary for private storage."""
        data: dict[str, Any] = {
            "canvas_domain": self.canvas_domain,
            "access_token": self.access_token.get_secret_value(),
            "refresh_token": self.refresh_token.get_secret_value(),
            "client_id": self.client_id,
            "client_secret": self.client_secret.get_secret_value(),
            "obtained_at": self.obtained_at.astimezone(UTC).isoformat(),
            "last_refreshed_at": self.last_refreshed_at.astimezone(UTC).isoformat(),
        }
        if self.user is not None:
            data["user"] = {
                "id": self.user.id,
                "name": self.user.name,
            }
        return data

    @classmethod
    def from_store_dict(cls, data: dict[str, Any]) -> "StoredTokens":
        """Instantiate StoredTokens from raw storage dictionary."""
        return cls.model_validate(data)
