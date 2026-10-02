"""OAuth/OIDC authentication for the public streamable HTTP MCP endpoint."""

from dataclasses import dataclass
from typing import Any

from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions

from .config import Config


@dataclass(frozen=True)
class MCPAuthentication:
    """The SDK settings, OAuth provider, and extra OIDC callback routes."""

    settings: AuthSettings
    provider: Any
    extra_route_paths: frozenset[str]


def create_mcp_auth_provider(config: Config) -> MCPAuthentication | None:
    """Create the optional FastMCP OIDC proxy authentication provider.

    FastMCP exposes the MCP OAuth metadata and Dynamic Client Registration
    routes itself.  It delegates the human login to the configured upstream
    OIDC provider, then issues and validates access tokens for MCP clients.
    """
    if config.mcp_auth_mode == "none":
        return None

    if config.mcp_auth_mode != "oidc":
        raise ValueError(f"Unsupported MCP_AUTH_MODE: {config.mcp_auth_mode}")

    from fastmcp.server.auth.oidc_proxy import OIDCProxy

    provider = OIDCProxy(
        config_url=config.mcp_oidc_config_url,
        client_id=config.mcp_oidc_client_id,
        client_secret=config.mcp_oidc_client_secret,
        audience=config.mcp_oidc_audience or None,
        required_scopes=config.mcp_oidc_required_scopes or None,
        base_url=config.mcp_public_url,
        issuer_url=config.mcp_public_url,
        redirect_path=config.mcp_oidc_redirect_path or None,
        allowed_client_redirect_uris=config.mcp_oidc_allowed_client_redirect_uris,
        jwt_signing_key=config.mcp_oidc_jwt_signing_key,
        token_endpoint_auth_method=(
            config.mcp_oidc_token_endpoint_auth_method or None
        ),
        require_authorization_consent=(
            config.mcp_oidc_require_authorization_consent
        ),
    )

    # The repository uses the MCP SDK's FastMCP implementation.  It supplies
    # the standard OAuth and protected-resource routes when given these
    # settings; OIDCProxy supplies the underlying login and token storage.
    settings = AuthSettings(
        issuer_url=config.mcp_public_url,
        resource_server_url=f"{config.mcp_public_url}/mcp",
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=config.mcp_oidc_required_scopes or None,
        ),
        required_scopes=config.mcp_oidc_required_scopes or None,
    )
    return MCPAuthentication(
        settings=settings,
        provider=provider,
        extra_route_paths=frozenset({config.mcp_oidc_redirect_path, "/consent"}),
    )


def register_mcp_auth_routes(mcp: Any, authentication: MCPAuthentication) -> None:
    """Register OIDCProxy's callback and consent routes on the MCP SDK app."""
    for route in authentication.provider.get_routes("/mcp"):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        endpoint = getattr(route, "endpoint", None)
        if (
            path in authentication.extra_route_paths
            and methods is not None
            and endpoint is not None
        ):
            mcp.custom_route(path, methods=list(methods))(endpoint)
