"""Google OAuth credential management for Canvas MCP.

Handles OAuth2 flow for Google Docs and Slides APIs.
Token stored at ~/.canvas-mcp/google_token.json.
"""

import asyncio
import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from .logging import log_error, log_info

SCOPES = [
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/presentations.readonly",
]

TOKEN_DIR = Path.home() / ".canvas-mcp"
TOKEN_PATH = TOKEN_DIR / "google_token.json"


def _get_client_config() -> dict | None:
    """Build OAuth client config from env vars."""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }


def get_google_credentials() -> Credentials | None:
    """Load Google credentials from stored token, auto-refreshing if expired.

    Returns None if no token exists or refresh fails (user must re-authenticate).
    """
    if not TOKEN_PATH.exists():
        return None

    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    except Exception as exc:
        log_error("Failed to load Google token", exc=exc)
        return None

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_token(creds)
            log_info("Google token refreshed successfully")
            return creds
        except Exception as exc:
            log_error("Failed to refresh Google token", exc=exc)
            return None

    return None


async def authenticate_google() -> str:
    """Run the OAuth consent flow in a background thread.

    Opens a browser for the user to sign in and grant read-only access
    to Google Docs and Slides. Saves the refresh token for future use.

    Returns a status message.
    """
    client_config = _get_client_config()
    if not client_config:
        return (
            "Google OAuth not configured. Set GOOGLE_CLIENT_ID and "
            "GOOGLE_CLIENT_SECRET in the canvas-mcp-fork .env file."
        )

    def _run_flow() -> Credentials:
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        return flow.run_local_server(port=0, open_browser=True)

    try:
        creds = await asyncio.get_event_loop().run_in_executor(None, _run_flow)
        _save_token(creds)
        return "Google authentication successful! Token saved."
    except Exception as exc:
        log_error("Google OAuth flow failed", exc=exc)
        return f"Google authentication failed: {exc}"


def _save_token(creds: Credentials) -> None:
    """Persist credentials to disk."""
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else SCOPES,
    }
    TOKEN_PATH.write_text(json.dumps(token_data, indent=2))
    log_info(f"Google token saved to {TOKEN_PATH}")
