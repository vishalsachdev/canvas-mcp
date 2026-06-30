"""Compose + send the admin access-request email. No Azure import here."""

from __future__ import annotations

from html import escape

from ..logging import log_error, log_info
from .store import AccessStore, Requester
from .tokens import mint_token


def build_request_email(req: Requester, approve_url: str) -> dict:
    subject = f"Canvas MCP access request — {req.display_name or req.upn}"
    html = f"""\
<div style="font-family:sans-serif;max-width:560px">
  <p>Someone signed in to the hosted Canvas MCP but is <b>not on the allowlist yet</b>.
     They authenticated with NetID + Duo, so their identity is verified.</p>
  <p><b>{escape(req.display_name)}</b><br>
     {escape(req.upn)}<br>
     <code>{escape(req.oid)}</code></p>
  <p><a href="{escape(approve_url)}"
        style="background:#1d4ed8;color:#fff;padding:11px 20px;border-radius:8px;
               text-decoration:none">Approve access</a></p>
  <p style="color:#b45309;font-size:13px">This link is single-use and expires in 24 hours.
     Approving opens a confirmation page; the grant applies only after you click Confirm.</p>
</div>"""
    plain = (f"Canvas MCP access request\n\n{req.display_name} <{req.upn}>\n"
             f"OID: {req.oid}\n\nApprove: {approve_url}\n"
             f"(single-use, expires in 24h; confirm on the page to grant)")
    return {"subject": subject, "html": html, "plain": plain}


async def notify_access_request(
    *, store: AccessStore, requester: Requester, secret: str,
    approve_base_url: str, admin_emails: list[str], cooldown_hours: int,
    ttl_seconds: int, send_email, jti: str, now: int, now_iso: str,
) -> bool:
    """Dedup, mint a token, build the email, and send it. Never raises."""
    try:
        if not (secret and approve_base_url and admin_emails):
            log_error("access notify skipped: feature not fully configured")
            return False
        exp = now + ttl_seconds
        should = store.note_request(
            requester, jti=jti, exp=exp, now_iso=now_iso, cooldown_hours=cooldown_hours)
        if not should:
            return False
        token = mint_token(oid=requester.oid, jti=jti, exp=exp, secret=secret)
        approve_url = f"{approve_base_url}/admin/access/approve?token={token}"
        msg = build_request_email(requester, approve_url)
        await send_email(admin_emails, msg["subject"], msg["html"], msg["plain"])
        log_info("access request email sent", entra_oid=requester.oid)
        return True
    except Exception as exc:  # fire-and-forget: must never break the request path
        log_error(f"access notify failed: {exc}")
        return False
