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


class _AzureTableBackend:
    def __init__(self, table_client) -> None:
        self._t = table_client

    def get(self, pk, rk):
        from azure.core.exceptions import ResourceNotFoundError
        try:
            return dict(self._t.get_entity(pk, rk))
        except ResourceNotFoundError:
            return None

    def upsert(self, entity):
        self._t.upsert_entity(entity)

    def replace_if_unmodified(self, entity, etag):
        from azure.core import MatchConditions
        from azure.core.exceptions import HttpResponseError
        try:
            self._t.update_entity(entity, mode="replace", etag=etag,
                                  match_condition=MatchConditions.IfNotModified)
        except HttpResponseError as exc:
            raise ConcurrencyConflict(str(exc)) from exc

    def query(self, pk):
        flt = "PartitionKey eq '%s'" % pk.replace("'", "''")
        return [dict(e) for e in self._t.query_entities(flt)]

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

    async def send(recipients, subject, html, plain):
        from azure.communication.email import EmailClient
        from azure.identity import DefaultAzureCredential
        client = EmailClient(config.acs_endpoint, DefaultAzureCredential())
        message = {
            "senderAddress": config.acs_sender,
            "content": {"subject": subject, "html": html, "plainText": plain},
            "recipients": {"to": [{"address": a} for a in recipients]},
        }
        poller = client.begin_send(message)
        poller.result()

    return send
