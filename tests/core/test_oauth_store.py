"""Tests for Canvas OAuth local token store: locking, schema, permissions, concurrency."""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from canvas_mcp.auth.models import (
    OAuthUser,
    StoredTokens,
    TokenStoreConflict,
    TokenStoreError,
)
from canvas_mcp.auth.store import TokenStore


def _make_sample_entry(
    domain: str = "canvas.example.edu",
    access_token: str = "access-123",
    refresh_token: str = "refresh-456",
    client_id: str = "client-789",
    client_secret: str = "secret-abc",
    user_id: int | None = 42,
    user_name: str = "Test Student",
    obtained_at: datetime | None = None,
    last_refreshed_at: datetime | None = None,
) -> StoredTokens:
    now = datetime.now(UTC)
    return StoredTokens(
        canvas_domain=domain,
        access_token=SecretStr(access_token),
        refresh_token=SecretStr(refresh_token),
        client_id=client_id,
        client_secret=SecretStr(client_secret),
        obtained_at=obtained_at or now,
        last_refreshed_at=last_refreshed_at or now,
        user=OAuthUser(id=user_id, name=user_name) if user_id is not None else None,
    )


def test_missing_store_file_and_missing_domain(tmp_path: Path) -> None:
    store_path = tmp_path / "sub" / "tokens.json"
    store = TokenStore(store_path)
    assert store.load("canvas.example.edu") is None

    # After saving one domain, querying another domain returns None
    entry = _make_sample_entry("canvas.example.edu")
    store.save(entry)
    assert store.load("other.example.edu") is None


def test_round_trip_across_store_reload(tmp_path: Path) -> None:
    store_path = tmp_path / "tokens.json"
    store1 = TokenStore(store_path)
    entry = _make_sample_entry(
        domain="canvas.example.edu",
        access_token="tok_acc",
        refresh_token="tok_ref",
        user_id=101,
        user_name="Jane Doe",
    )
    store1.save(entry)

    # Fresh store instance reading from disk
    store2 = TokenStore(store_path)
    loaded = store2.load("canvas.example.edu")
    assert loaded is not None
    assert loaded.canvas_domain == "canvas.example.edu"
    assert loaded.access_token.get_secret_value() == "tok_acc"
    assert loaded.refresh_token.get_secret_value() == "tok_ref"
    assert loaded.client_id == "client-789"
    assert loaded.client_secret.get_secret_value() == "secret-abc"
    assert loaded.user is not None
    assert loaded.user.id == 101
    assert loaded.user.name == "Jane Doe"
    assert loaded.obtained_at == entry.obtained_at
    assert loaded.last_refreshed_at == entry.last_refreshed_at


def test_preservation_of_multiple_domains(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    entry1 = _make_sample_entry("canvas1.example.edu", access_token="acc1")
    entry2 = _make_sample_entry("canvas2.example.edu", access_token="acc2")

    store.save(entry1)
    store.save(entry2)

    loaded1 = store.load("canvas1.example.edu")
    loaded2 = store.load("canvas2.example.edu")
    assert loaded1 is not None and loaded1.access_token.get_secret_value() == "acc1"
    assert loaded2 is not None and loaded2.access_token.get_secret_value() == "acc2"


def test_domain_key_mismatch_raises_token_store_error(tmp_path: Path) -> None:
    store_file = tmp_path / "tokens.json"
    entry = _make_sample_entry("canvas.example.edu")
    store = TokenStore(store_file)
    store.save(entry)

    # Maliciously or erroneously change map key so it doesn't match canvas_domain
    data = json.loads(store_file.read_text(encoding="utf-8"))
    data["mismatched.example.edu"] = data.pop("canvas.example.edu")
    store_file.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(TokenStoreError, match="Domain mismatch"):
        store.load("mismatched.example.edu")


def test_corrupt_file_non_overwrite(tmp_path: Path) -> None:
    store_file = tmp_path / "tokens.json"
    corrupt_content = "NOT_VALID_JSON{{"
    store_file.write_text(corrupt_content, encoding="utf-8")

    store = TokenStore(store_file)
    with pytest.raises(TokenStoreError, match="Corrupt JSON"):
        store.load("canvas.example.edu")

    entry = _make_sample_entry("canvas.example.edu")
    with pytest.raises(TokenStoreError, match="Corrupt JSON"):
        store.save(entry)

    # Corrupt content must NOT be overwritten
    assert store_file.read_text(encoding="utf-8") == corrupt_content


def test_compare_and_swap_conflict(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "tokens.json")
    entry = _make_sample_entry("canvas.example.edu", access_token="tok1")
    store.save(entry)

    # Update succeeds when expected matches current
    updated_entry = _make_sample_entry("canvas.example.edu", access_token="tok2")
    store.save(updated_entry, expected=entry)
    assert store.load("canvas.example.edu").access_token.get_secret_value() == "tok2"  # type: ignore[union-attr]

    # Stale expected entry raises TokenStoreConflict
    newer_entry = _make_sample_entry("canvas.example.edu", access_token="tok3")
    with pytest.raises(TokenStoreConflict, match="updated by another process"):
        store.save(newer_entry, expected=entry)

    # Expected entry when domain does not exist in store
    with pytest.raises(TokenStoreConflict, match="expected existing entry"):
        store.save(
            _make_sample_entry("absent.example.edu"),
            expected=_make_sample_entry("absent.example.edu"),
        )


def test_failed_replace_preserves_previous_bytes(tmp_path: Path) -> None:
    store_file = tmp_path / "tokens.json"
    store = TokenStore(store_file)
    entry1 = _make_sample_entry("canvas.example.edu", access_token="tok_initial")
    store.save(entry1)
    original_bytes = store_file.read_bytes()

    entry2 = _make_sample_entry("canvas.example.edu", access_token="tok_next")

    with patch("os.replace", side_effect=OSError("Disk failure")):
        with pytest.raises(TokenStoreError, match="Failed to write token file"):
            store.save(entry2)

    # Store file content remains untouched
    assert store_file.read_bytes() == original_bytes
    # No orphaned temporary files left in directory
    tmp_files = list(tmp_path.glob("tokens-*.tmp"))
    assert len(tmp_files) == 0


def test_concurrent_writers_preserve_both_domains(tmp_path: Path) -> None:
    import concurrent.futures

    store_file = tmp_path / "tokens.json"
    store = TokenStore(store_file)

    def writer(domain: str, iterations: int) -> None:
        local_store = TokenStore(store_file)
        for i in range(iterations):
            e = _make_sample_entry(domain, access_token=f"{domain}-tok-{i}")
            local_store.save(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        f1 = executor.submit(writer, "d1.example.edu", 15)
        f2 = executor.submit(writer, "d2.example.edu", 15)
        f1.result()
        f2.result()

    loaded1 = store.load("d1.example.edu")
    loaded2 = store.load("d2.example.edu")
    assert (
        loaded1 is not None
        and "d1.example.edu-tok-" in loaded1.access_token.get_secret_value()
    )
    assert (
        loaded2 is not None
        and "d2.example.edu-tok-" in loaded2.access_token.get_secret_value()
    )


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions & symlinks test")
def test_posix_symlink_rejection(tmp_path: Path) -> None:
    # Symlink to directory
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir(mode=0o700)
    link_dir = tmp_path / "link_dir"
    link_dir.symlink_to(real_dir)

    store = TokenStore(link_dir / "tokens.json")
    with pytest.raises(TokenStoreError, match="Rejecting symlink for store directory"):
        store.load("canvas.example.edu")

    # Symlink to token file
    real_file = real_dir / "tokens.json"
    real_file.write_text("{}", encoding="utf-8")
    link_file = real_dir / "link_tokens.json"
    link_file.symlink_to(real_file)

    store_link = TokenStore(link_file)
    with pytest.raises(TokenStoreError, match="Rejecting symlink for store file"):
        store_link.load("canvas.example.edu")

    # Symlink to lock file
    store_real = TokenStore(real_file)
    lock_file = store_real.lock_path
    lock_target = real_dir / "other.lock"
    lock_target.write_text("", encoding="utf-8")
    lock_file.symlink_to(lock_target)

    with pytest.raises(TokenStoreError, match="Rejecting symlink for lock file"):
        store_real.save(_make_sample_entry("canvas.example.edu"))


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions test")
def test_posix_permissions_tightened(tmp_path: Path) -> None:
    store_dir = tmp_path / "insecure_dir"
    store_dir.mkdir(mode=0o755)
    # Ensure it's wide open to group/others
    os.chmod(store_dir, 0o755)

    store_file = store_dir / "tokens.json"
    store = TokenStore(store_file)
    entry = _make_sample_entry("canvas.example.edu")
    store.save(entry)

    # Check directory permissions were tightened to 0700
    dir_mode = store_dir.stat().st_mode & 0o777
    assert dir_mode == 0o700

    # Check file permissions are 0600
    file_mode = store_file.stat().st_mode & 0o777
    assert file_mode == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX ownership test")
def test_posix_wrong_owner_rejected(tmp_path: Path) -> None:
    store_dir = tmp_path / "store_dir"
    store_dir.mkdir(mode=0o700)
    store_file = store_dir / "tokens.json"
    store = TokenStore(store_file)

    # Mock getuid to a different UID
    with patch("os.getuid", return_value=99999):
        with pytest.raises(TokenStoreError, match="owned by UID"):
            store.load("canvas.example.edu")
def test_validation_errors_redact_credentials(tmp_path: Path) -> None:
    """Regressions asserting access token, refresh token, and client secret never leak in validation errors."""
    secret_acc = "SECRET_ACCESS_TOKEN_ABC123"
    secret_ref = "SECRET_REFRESH_TOKEN_XYZ456"
    secret_cli = "SECRET_CLIENT_SECRET_789"

    # 1. Missing required field (obtained_at missing)
    bad_dict = {
        "canvas_domain": "canvas.example.edu",
        "access_token": secret_acc,
        "refresh_token": secret_ref,
        "client_id": "client_1",
        "client_secret": secret_cli,
    }
    store_file = tmp_path / "tokens.json"
    store_file.write_text(json.dumps({"canvas.example.edu": bad_dict}), encoding="utf-8")
    store = TokenStore(store_file)

    with pytest.raises(TokenStoreError) as exc_info:
        store.load("canvas.example.edu")

    err_str = str(exc_info.value)
    err_repr = repr(exc_info.value)
    for s in (secret_acc, secret_ref, secret_cli):
        assert s not in err_str, f"Secret leaked in error str: {s}"
        assert s not in err_repr, f"Secret leaked in error repr: {s}"
    assert exc_info.value.__cause__ is None
    assert exc_info.value.__suppress_context__ is True
    if exc_info.value.__context__ is not None:
        ctx_str = str(exc_info.value.__context__)
        for s in (secret_acc, secret_ref, secret_cli):
            assert s not in ctx_str

    # 2. Invalid field type
    bad_dict2 = {
        "canvas_domain": "canvas.example.edu",
        "access_token": secret_acc,
        "refresh_token": secret_ref,
        "client_id": "client_1",
        "client_secret": secret_cli,
        "obtained_at": "not-a-valid-date",
        "last_refreshed_at": 12345,
    }
    store_file.write_text(json.dumps({"canvas.example.edu": bad_dict2}), encoding="utf-8")
    with pytest.raises(TokenStoreError) as exc_info2:
        store.load("canvas.example.edu")

    err_str2 = str(exc_info2.value)
    for s in (secret_acc, secret_ref, secret_cli):
        assert s not in err_str2, f"Secret leaked in invalid-type error: {s}"
    assert exc_info2.value.__cause__ is None
    assert exc_info2.value.__suppress_context__ is True


def test_cli_error_does_not_leak_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Assert that CLI stderr does not output secrets when store validation fails."""
    secret_acc = "SECRET_ACCESS_VAL"
    secret_ref = "SECRET_REFRESH_VAL"
    secret_cli = "SECRET_CLIENT_VAL"

    bad_dict = {
        "canvas_domain": "canvas.example.edu",
        "access_token": secret_acc,
        "refresh_token": secret_ref,
        "client_id": "client_1",
        "client_secret": secret_cli,
    }
    store_file = tmp_path / "tokens.json"
    store_file.write_text(json.dumps({"canvas.example.edu": bad_dict}), encoding="utf-8")
    store = TokenStore(store_file)

    from canvas_mcp.auth import cli

    # Simulate running login which encounters corrupt/malformed store
    with patch.object(cli, "TokenStore", return_value=store):
        with patch("sys.stdin.isatty", return_value=False):
            with pytest.raises(SystemExit) as exc:
                cli.main(["login", "--domain", "canvas.example.edu", "--manual"])
            assert exc.value.code == 1

    captured = capsys.readouterr()
    for s in (secret_acc, secret_ref, secret_cli):
        assert s not in captured.err
        assert s not in captured.out


def test_windows_permissions_tightened(tmp_path: Path) -> None:
    """Assert that on Windows, icacls is invoked to remove inheritance and grant user full control."""
    from canvas_mcp.auth.store import _verify_and_tighten_windows_permissions

    target_file = tmp_path / "test_file.json"
    target_file.write_text("{}", encoding="utf-8")

    with patch("os.name", "nt"), patch("os.environ.get", return_value="TestUser"), patch("subprocess.run") as mock_run:
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(returncode=0)
        _verify_and_tighten_windows_permissions(target_file, is_dir=False)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["icacls", str(target_file), "/inheritance:r", "/grant:r", "TestUser:F"]


def test_windows_permissions_failure_raises(tmp_path: Path) -> None:
    from canvas_mcp.auth.store import _verify_and_tighten_windows_permissions

    target_file = tmp_path / "test_file.json"
    target_file.write_text("{}", encoding="utf-8")

    with patch("os.name", "nt"), patch("os.environ.get", return_value="TestUser"), patch("subprocess.run") as mock_run:
        from unittest.mock import MagicMock
        mock_run.return_value = MagicMock(returncode=1, stderr="Access is denied")
        with pytest.raises(TokenStoreError, match="Failed to tighten Windows ACLs"):
            _verify_and_tighten_windows_permissions(target_file, is_dir=False)


def test_keyring_backend_lifecycle() -> None:
    """Test saving, loading, CAS conflict, and deleting via Keyring backend."""
    storage: dict[tuple[str, str], str] = {}

    class MockKeyring:
        priority = 5

        def get_password(self, service: str, username: str) -> str | None:
            return storage.get((service, username))

        def set_password(self, service: str, username: str, password: str) -> None:
            storage[(service, username)] = password

        def delete_password(self, service: str, username: str) -> None:
            storage.pop((service, username), None)

    with patch("keyring.get_keyring", return_value=MockKeyring()):
        store = TokenStore()
        assert store._use_keyring() is True

        entry = _make_sample_entry("canvas.example.edu", access_token="keyring-acc-1")
        store.save(entry)

        loaded = store.load("canvas.example.edu")
        assert loaded is not None
        assert loaded.access_token.get_secret_value() == "keyring-acc-1"

        # CAS Conflict
        other_entry = _make_sample_entry("canvas.example.edu", access_token="keyring-acc-other")
        stale_expected = _make_sample_entry("canvas.example.edu", access_token="stale-acc")
        with pytest.raises(TokenStoreConflict):
            store.save(other_entry, expected=stale_expected)

        # Delete
        assert store.delete("canvas.example.edu") is True
        assert store.load("canvas.example.edu") is None


def test_keyring_unavailable_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """When OS credential store is unavailable, TokenStore fails closed unless file store is permitted."""
    monkeypatch.delenv("CANVAS_ALLOW_FILE_TOKEN_STORE", raising=False)

    class InactiveKeyring:
        priority = 0

    with patch("keyring.get_keyring", return_value=InactiveKeyring()):
        store = TokenStore()
        assert store._use_keyring() is False

        entry = _make_sample_entry("canvas.example.edu")
        with pytest.raises(TokenStoreError, match="No secure OS credential store available"):
            store.save(entry)


def test_keyring_unavailable_with_file_store_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When OS credential store is unavailable and CANVAS_ALLOW_FILE_TOKEN_STORE=1, falls back to file store."""
    monkeypatch.setenv("CANVAS_ALLOW_FILE_TOKEN_STORE", "1")

    class InactiveKeyring:
        priority = 0

    store_file = tmp_path / "tokens.json"
    with patch("keyring.get_keyring", return_value=InactiveKeyring()), patch("canvas_mcp.auth.store.DEFAULT_STORE_PATH", store_file):
        store = TokenStore()
        assert store._use_keyring() is False
        assert store._is_file_store_allowed() is True

        entry = _make_sample_entry("canvas.example.edu", access_token="fallback-token")
        store.save(entry)

        loaded = store.load("canvas.example.edu")
        assert loaded is not None
        assert loaded.access_token.get_secret_value() == "fallback-token"
