"""Lazy builders for the Azure-backed store + ACS sender.

Azure imports happen INSIDE the functions, so importing this module never
requires the optional ``[hosted]`` dependencies. Callers must guard with
``feature_ready(config)`` before building.
"""

from __future__ import annotations

from ..logging import log_error
from .store import AccessStore, ConcurrencyConflict


def feature_ready(config) -> bool:
    return bool(getattr(config, "access_request_enabled", False)
                and getattr(config, "access_token_secret", "")
                and getattr(config, "access_table_account", ""))


def _entity_to_row(entity) -> dict:
    """Convert an azure-data-tables entity to a plain row, surfacing the ETag.

    azure-data-tables exposes the ETag via ``entity.metadata['etag']`` rather
    than as an item, so a bare ``dict(entity)`` silently drops it. The store's
    ``consume_pending`` needs ``row['etag']`` for the optimistic-concurrency
    (single-use) guard, so copy it onto the row. Pure — no azure import — so it
    is unit-testable without the optional ``[hosted]`` deps installed.
    """
    row = dict(entity)
    meta = getattr(entity, "metadata", None) or {}
    etag = meta.get("etag")
    if etag:
        row["etag"] = etag
    return row


class _AzureTableBackend:
    def __init__(self, table_client) -> None:
        self._t = table_client

    def get(self, pk, rk):
        from azure.core.exceptions import ResourceNotFoundError
        try:
            return _entity_to_row(self._t.get_entity(pk, rk))
        except ResourceNotFoundError:
            return None

    def upsert(self, entity):
        self._t.upsert_entity(entity)

    def replace_if_unmodified(self, entity, etag):
        from azure.core import MatchConditions
        from azure.core.exceptions import HttpResponseError
        # The ETag rides the match_condition param, not the row body; drop the
        # synthetic "etag" item (added by _entity_to_row) so it is never
        # persisted as a data column.
        payload = {k: v for k, v in entity.items() if k != "etag"}
        try:
            self._t.update_entity(payload, mode="replace", etag=etag,
                                  match_condition=MatchConditions.IfNotModified)
        except HttpResponseError as exc:
            raise ConcurrencyConflict(str(exc)) from exc

    def query(self, pk):
        flt = "PartitionKey eq '%s'" % pk.replace("'", "''")
        return [_entity_to_row(e) for e in self._t.query_entities(flt)]

    def delete(self, pk, rk):
        self._t.delete_entity(pk, rk)


def build_store(config) -> AccessStore | None:
    if not feature_ready(config):
        return None
    try:
        from azure.data.tables import TableServiceClient
        from azure.identity import DefaultAzureCredential
        endpoint = f"https://{config.access_table_account}.table.core.windows.net"
        svc = TableServiceClient(endpoint=endpoint, credential=DefaultAzureCredential())
        svc.create_table_if_not_exists(config.access_table_name)
        table = svc.get_table_client(config.access_table_name)
        return AccessStore(_AzureTableBackend(table))
    except Exception as exc:
        log_error(f"access store unavailable: {exc}")
        return None


def build_email_sender(config):
    if not (config.acs_endpoint and config.acs_sender):
        return None
    # Build the credential + client ONCE here (not per send). Azure imports stay
    # inside this function body (never module top-level), so the base install
    # without the [hosted] extra is unaffected; degrade to None on any failure.
    try:
        import asyncio
        from azure.communication.email import EmailClient
        from azure.identity import DefaultAzureCredential
        client = EmailClient(config.acs_endpoint, DefaultAzureCredential())
    except Exception as exc:
        log_error(f"access email sender unavailable: {exc}")
        return None

    async def send(recipients, subject, html, plain):
        def _send():
            message = {
                "senderAddress": config.acs_sender,
                "content": {"subject": subject, "html": html, "plainText": plain},
                "recipients": {"to": [{"address": a} for a in recipients]},
            }
            client.begin_send(message).result()

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _send)

    return send
