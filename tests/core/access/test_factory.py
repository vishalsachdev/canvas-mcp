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
