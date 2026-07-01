from types import SimpleNamespace
from canvas_mcp.core.access import factory


def _cfg(**kw):
    base = dict(access_request_enabled=True, access_token_secret="s",
                access_table_account="acct", access_table_name="t",
                acs_endpoint="https://acs", acs_sender="x@d", access_admin_emails=["a@x"])
    base.update(kw)
    return SimpleNamespace(**base)


def test_feature_ready_true_when_configured():
    assert factory.feature_ready(_cfg()) is True


def test_feature_ready_false_when_disabled_or_unconfigured():
    assert factory.feature_ready(_cfg(access_request_enabled=False)) is False
    assert factory.feature_ready(_cfg(access_token_secret="")) is False
    assert factory.feature_ready(_cfg(access_table_account="")) is False


def test_build_store_returns_none_when_not_ready():
    assert factory.build_store(_cfg(access_request_enabled=False)) is None


def test_entity_to_row_surfaces_etag_from_metadata():
    """Azure exposes the ETag on entity.metadata, not as an item; the row must
    carry it so the store's single-use ETag guard works on the real backend.

    Regression guard for the cross-backend seam bug where dict(entity) dropped
    the ETag (InMemoryBackend kept it as a key, so tests hid the KeyError that
    consume_pending would raise against the live Azure backend)."""
    class _FakeEntity(dict):
        def __init__(self, data, etag):
            super().__init__(data)
            self.metadata = {"etag": etag}

    ent = _FakeEntity(
        {"PartitionKey": "pending", "RowKey": "oid-1", "status": "pending"},
        etag='W/"abc123"',
    )
    row = factory._entity_to_row(ent)
    assert row["etag"] == 'W/"abc123"'                 # surfaced from .metadata
    assert row["RowKey"] == "oid-1" and row["status"] == "pending"
    assert "etag" not in dict(ent)                     # bare dict() drops it — the bug


def test_entity_to_row_no_metadata_is_safe():
    """A row without metadata/etag (e.g. plain dict) must not raise."""
    assert factory._entity_to_row({"RowKey": "x"}) == {"RowKey": "x"}
