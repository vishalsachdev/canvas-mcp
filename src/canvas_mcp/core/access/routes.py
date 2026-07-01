"""ASGI handlers + HTML for the approve (GET) and confirm (POST) endpoints."""

from __future__ import annotations

from html import escape
from urllib.parse import parse_qs

from ..audit import log_access_change
from ..logging import log_error
from .store import AccessStore, Requester
from .tokens import verify_token

_WRAP = ("<!doctype html><meta charset=utf-8>"
         "<body style='font-family:sans-serif;max-width:480px;margin:48px auto;text-align:center'>")


def render_confirm_page(req: Requester, token: str) -> str:
    return (_WRAP + "<h2>Grant Canvas MCP access?</h2>"
            f"<p><b>{escape(req.display_name)}</b><br>{escape(req.upn)}<br>"
            f"<code>{escape(req.oid)}</code></p>"
            "<form method='post' action='/admin/access/confirm'>"
            f"<input type='hidden' name='token' value='{escape(token)}'>"
            "<button style='background:#1d4ed8;color:#fff;padding:11px 20px;"
            "border:0;border-radius:8px;font-size:15px'>Confirm grant</button></form>"
            "<p style='color:#64748b;font-size:12px'>single-use · expires in 24h</p>")


def render_success_page(req: Requester) -> str:
    return (_WRAP + "<h2>Access granted</h2>"
            f"<p><b>{escape(req.display_name)}</b> ({escape(req.upn)}) can now use Canvas MCP.</p>"
            "<p style='color:#64748b'>Their client connects within ~30s — no restart needed.</p>")


def render_invalid_page() -> str:
    return (_WRAP + "<h2>This approval link is no longer valid</h2>"
            "<p>It may have expired or already been used. No changes were made.</p>"
            "<p>If this person still needs access, ask them to reconnect.</p>")


def render_retry_page() -> str:
    return (_WRAP + "<h2>Approval didn&#x27;t complete</h2>"
            "<p>A temporary error stopped the grant from being saved. Nothing was "
            "consumed — click Confirm again, or ask the person to reconnect for a "
            "fresh approval link.</p>")


async def _send_html(send, html: str, status: int = 200) -> None:
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"text/html; charset=utf-8")]})
    await send({"type": "http.response.body", "body": html.encode()})


def _requester_from_pending(row: dict | None, oid: str) -> Requester:
    row = row or {}
    return Requester(oid=oid, upn=row.get("upn", ""), display_name=row.get("displayName", ""))


async def handle_approve(query_string: bytes, send, *, store: AccessStore,
                         secret: str, now: int) -> None:
    token = (parse_qs(query_string.decode()).get("token") or [""])[0]
    claims = verify_token(token, secret=secret, now=now)
    if not claims:
        await _send_html(send, render_invalid_page())
        return
    pending = store.get_pending(claims.oid)
    if not pending or pending.get("status") != "pending" or pending.get("tokenJti") != claims.jti:
        await _send_html(send, render_invalid_page())
        return
    await _send_html(send, render_confirm_page(_requester_from_pending(pending, claims.oid), token))


async def handle_confirm(body: bytes, send, *, store: AccessStore,
                         secret: str, now: int) -> None:
    token = (parse_qs(body.decode()).get("token") or [""])[0]
    claims = verify_token(token, secret=secret, now=now)
    if not claims:
        await _send_html(send, render_invalid_page())
        return
    # Validate the token against the live pending request WITHOUT consuming it
    # yet, so a downstream write failure leaves the token retriable.
    pending = store.get_pending(claims.oid)
    if (not pending or pending.get("status") != "pending"
            or pending.get("tokenJti") != claims.jti):
        await _send_html(send, render_invalid_page())
        return
    req = _requester_from_pending(pending, claims.oid)

    # Grant FIRST — the actual authorization, an idempotent upsert. If this write
    # fails, nothing has been consumed, so the SAME link still works on retry,
    # instead of a token spent with no access granted.
    try:
        store.grant(req, jti=claims.jti)
    except Exception as exc:
        log_error(f"access grant write failed for {req.oid}: {exc}")
        await _send_html(send, render_retry_page())
        return

    # Mark the token single-use consumed. Best-effort: the user is already
    # granted, so a failure here at worst lets this token re-grant the SAME oid
    # (a harmless idempotent no-op).
    try:
        store.consume_pending(claims.oid, claims.jti)
    except Exception as exc:
        log_error(f"access token consume failed after grant for {req.oid}: {exc}")

    log_access_change("grant", req.oid, upn=req.upn or None)
    await _send_html(send, render_success_page(req))
