from canvas_mcp.core.access.tokens import mint_token, verify_token, TokenClaims

SECRET = "test-secret-key"


def test_roundtrip_valid_token():
    t = mint_token(oid="oid-1", jti="j1", exp=1000, secret=SECRET)
    claims = verify_token(t, secret=SECRET, now=999)
    assert claims == TokenClaims(oid="oid-1", jti="j1", exp=1000)


def test_expired_token_rejected():
    t = mint_token(oid="oid-1", jti="j1", exp=1000, secret=SECRET)
    assert verify_token(t, secret=SECRET, now=1000) is None  # exp must be > now
    assert verify_token(t, secret=SECRET, now=1001) is None


def test_tampered_signature_rejected():
    t = mint_token(oid="oid-1", jti="j1", exp=1000, secret=SECRET)
    assert verify_token(t, secret="wrong-secret", now=1) is None
    assert verify_token(t[:-2] + ("AA" if not t.endswith("AA") else "BB"),
                        secret=SECRET, now=1) is None


def test_garbage_input_returns_none_not_raise():
    for junk in ("", "no-dot", "a.b.c", "@@@.@@@"):
        assert verify_token(junk, secret=SECRET, now=1) is None
