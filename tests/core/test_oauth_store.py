"""Tests for Canvas OAuth local token store: locking, schema, permissions, concurrency."""

import json
import multiprocessing
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import keyring
from keyring.backend import KeyringBackend
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


def test_windows_permissions_powershell_invocation(tmp_path: Path) -> None:
    """Assert that on Windows, powershell.exe is invoked with EncodedCommand to tighten DACLs."""
    from canvas_mcp.auth.store import _verify_and_tighten_windows_permissions, _WIN_ACL_ENCODED
    from unittest.mock import MagicMock

    target_file = tmp_path / "test_file.json"
    target_file.write_text("{}", encoding="utf-8")

    fake_root = tmp_path / "Windows"
    fake_ps = fake_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    fake_ps.parent.mkdir(parents=True)
    fake_ps.write_text("", encoding="utf-8")

    with (
        patch("os.name", "nt"),
        patch.dict("os.environ", {"SystemRoot": str(fake_root)}),
        patch("subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="CANVAS_MCP_PRIVATE_ACL_OK\n")
        _verify_and_tighten_windows_permissions(target_file, is_dir=False)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == [str(fake_ps), "-NoProfile", "-NonInteractive", "-EncodedCommand", _WIN_ACL_ENCODED]
        kwargs = mock_run.call_args[1]
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == 15.0
        assert kwargs["env"]["CANVAS_MCP_ACL_PATH"] == str(target_file.resolve())
        assert kwargs["env"]["CANVAS_MCP_ACL_IS_DIR"] == "0"


def test_windows_permissions_failure_raises(tmp_path: Path) -> None:
    """Any failure in Windows permission enforcement must raise sanitized TokenStoreError."""
    from canvas_mcp.auth.store import _verify_and_tighten_windows_permissions
    from unittest.mock import MagicMock
    import subprocess

    target_file = tmp_path / "test_file.json"
    target_file.write_text("{}", encoding="utf-8")

    fake_root = tmp_path / "Windows"
    fake_ps = fake_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    fake_ps.parent.mkdir(parents=True)
    fake_ps.write_text("", encoding="utf-8")

    # Subprocess non-zero returncode
    with (
        patch("os.name", "nt"),
        patch.dict("os.environ", {"SystemRoot": str(fake_root)}),
        patch("subprocess.run", return_value=MagicMock(returncode=1, stdout="Failed")),
    ):
        with pytest.raises(TokenStoreError, match="Cannot establish private Windows permissions"):
            _verify_and_tighten_windows_permissions(target_file, is_dir=False)

    # Subprocess returncode 0 but wrong stdout
    with (
        patch("os.name", "nt"),
        patch.dict("os.environ", {"SystemRoot": str(fake_root)}),
        patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="SOMETHING_ELSE")),
    ):
        with pytest.raises(TokenStoreError, match="Cannot establish private Windows permissions"):
            _verify_and_tighten_windows_permissions(target_file, is_dir=False)

    # Subprocess timeout
    with (
        patch("os.name", "nt"),
        patch.dict("os.environ", {"SystemRoot": str(fake_root)}),
        patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="powershell", timeout=15.0)),
    ):
        with pytest.raises(TokenStoreError, match="Cannot establish private Windows permissions"):
            _verify_and_tighten_windows_permissions(target_file, is_dir=False)

    # Missing SystemRoot
    with (
        patch("os.name", "nt"),
        patch.dict("os.environ", {}, clear=True),
    ):
        with pytest.raises(TokenStoreError, match="Cannot establish private Windows permissions"):
            _verify_and_tighten_windows_permissions(target_file, is_dir=False)

    # Missing powershell.exe
    fake_ps.unlink()
    with (
        patch("os.name", "nt"),
        patch.dict("os.environ", {"SystemRoot": str(fake_root)}),
    ):
        with pytest.raises(TokenStoreError, match="Cannot establish private Windows permissions"):
            _verify_and_tighten_windows_permissions(target_file, is_dir=False)

    # Non-existent target is a no-op
    non_existent = tmp_path / "absent.json"
    with patch("os.name", "nt"):
        _verify_and_tighten_windows_permissions(non_existent, is_dir=False)


@pytest.mark.skipif(os.name != "nt", reason="Requires native Windows")
def test_windows_permissions_native_tighten_and_verify(tmp_path: Path) -> None:
    """On native Windows, verify that DACLs are private to current user only."""
    from canvas_mcp.auth.store import _verify_and_tighten_windows_permissions
    import subprocess

    test_dir = tmp_path / "private_dir"
    test_dir.mkdir()
    test_file = test_dir / "tokens.json"
    test_file.write_text("{}", encoding="utf-8")

    _verify_and_tighten_windows_permissions(test_dir, is_dir=True)
    _verify_and_tighten_windows_permissions(test_file, is_dir=False)

    check_script = """
    $acl = Get-Acl -LiteralPath $env:TEST_FILE
    $rules = $acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])
    if ($rules.Count -ne 1) { exit 1 }
    if ($rules[0].IdentityReference.Value -ne [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value) { exit 2 }
    exit 0
    """
    res = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", check_script],
        env=dict(os.environ, TEST_FILE=str(test_file)),
        capture_output=True,
    )
    assert res.returncode == 0

class DictKeyring(KeyringBackend):
    priority = 5

    def __init__(self) -> None:
        self.storage: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.storage.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.storage[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.storage.pop((service, username), None)


def test_keyring_backend_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test saving, loading, CAS conflict, and deleting via Keyring backend."""
    fake = DictKeyring()
    monkeypatch.setattr("canvas_mcp.auth.store._select_secure_keyring", lambda: fake)

    store = TokenStore()
    assert store._use_keyring() is True
    assert store._get_pinned_keyring() is fake

    entry = _make_sample_entry("canvas.example.edu", access_token="keyring-acc-1")
    store.save(entry)
    assert ("canvas-mcp", "canvas.example.edu") in fake.storage

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
    assert ("canvas-mcp", "canvas.example.edu") not in fake.storage
    assert store.load("canvas.example.edu") is None

def test_keyring_unavailable_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """When OS credential store is unavailable, TokenStore fails closed unless file store is permitted."""
    monkeypatch.delenv("CANVAS_ALLOW_FILE_TOKEN_STORE", raising=False)

    class InactiveKeyring(KeyringBackend):
        priority = 0

        def get_password(self, service: str, username: str) -> str | None:
            return None

        def set_password(self, service: str, username: str, password: str) -> None:
            pass

        def delete_password(self, service: str, username: str) -> None:
            pass

    keyring.set_keyring(InactiveKeyring())
    store = TokenStore()
    assert store._use_keyring() is False

    entry = _make_sample_entry("canvas.example.edu")
    with pytest.raises(TokenStoreError, match="No secure OS credential store available"):
        store.save(entry)


def test_keyring_unavailable_with_file_store_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When OS credential store is unavailable and CANVAS_ALLOW_FILE_TOKEN_STORE=1, falls back to file store."""
    monkeypatch.setenv("CANVAS_ALLOW_FILE_TOKEN_STORE", "1")

    class InactiveKeyring(KeyringBackend):
        priority = 0

        def get_password(self, service: str, username: str) -> str | None:
            return None

        def set_password(self, service: str, username: str, password: str) -> None:
            pass

        def delete_password(self, service: str, username: str) -> None:
            pass

    keyring.set_keyring(InactiveKeyring())
    store_file = tmp_path / "tokens.json"
    with patch("canvas_mcp.auth.store.DEFAULT_STORE_PATH", store_file):
        store = TokenStore()
        assert store._use_keyring() is False
        assert store._is_file_store_allowed() is True

        entry = _make_sample_entry("canvas.example.edu", access_token="fallback-token")
        store.save(entry)

        loaded = store.load("canvas.example.edu")
        assert loaded is not None
        assert loaded.access_token.get_secret_value() == "fallback-token"


def _patch_priority(cls: type, val: float, request: pytest.FixtureRequest) -> None:
    from jaraco.classes.properties import classproperty
    desc = cls.__dict__.get("priority")
    type.__setattr__(cls, "priority", classproperty(classmethod(lambda c: val)))
    request.addfinalizer(lambda: type.__setattr__(cls, "priority", desc))


def test_secure_keyring_selector_allowlist(request: pytest.FixtureRequest) -> None:
    """Only exact approved native backend classes with priority > 0 are selected."""
    from canvas_mcp.auth.store import _select_secure_keyring
    import keyring.backends.macOS
    import keyring.backends.Windows
    import keyring.backends.SecretService
    import keyring.backends.fail

    # Unapproved custom class with high priority
    class UnsafeCustomKeyring(KeyringBackend):
        priority = 100
        def get_password(self, s: str, u: str) -> str | None: return None
        def set_password(self, s: str, u: str, p: str) -> None: pass
        def delete_password(self, s: str, u: str) -> None: pass

    keyring.set_keyring(UnsafeCustomKeyring())
    assert _select_secure_keyring() is None

    # Subclass of approved backend is rejected (must be exact class)
    class SubclassedMacOS(keyring.backends.macOS.Keyring):
        pass

    keyring.set_keyring(SubclassedMacOS())
    assert _select_secure_keyring() is None

    # Fail/Null backend is rejected
    keyring.set_keyring(keyring.backends.fail.Keyring())
    assert _select_secure_keyring() is None

    # Exact macOS Keyring with priority > 0 is approved
    mac_kr = keyring.backends.macOS.Keyring()
    _patch_priority(keyring.backends.macOS.Keyring, 5.0, request)
    keyring.set_keyring(mac_kr)
    assert _select_secure_keyring() is mac_kr

    # Exact WinVaultKeyring with priority > 0 is approved
    win_kr = keyring.backends.Windows.WinVaultKeyring()
    _patch_priority(keyring.backends.Windows.WinVaultKeyring, 5.0, request)
    keyring.set_keyring(win_kr)
    assert _select_secure_keyring() is win_kr

    # Exact SecretService Keyring with priority > 0 is approved
    ss_kr = keyring.backends.SecretService.Keyring()
    _patch_priority(keyring.backends.SecretService.Keyring, 5.0, request)
    keyring.set_keyring(ss_kr)
    assert _select_secure_keyring() is ss_kr

    # Priority <= 0 is rejected even for approved class
    _patch_priority(keyring.backends.macOS.Keyring, 0.0, request)
    keyring.set_keyring(mac_kr)
    assert _select_secure_keyring() is None


def test_secure_keyring_selector_chainer(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """ChainerBackend is resolved to its first approved leaf if all leaves are approved; otherwise rejected."""
    from canvas_mcp.auth.store import _select_secure_keyring
    import keyring.backends.macOS
    import keyring.backends.Windows
    from keyring.backends.chainer import ChainerBackend

    mac_kr = keyring.backends.macOS.Keyring()
    win_kr = keyring.backends.Windows.WinVaultKeyring()
    _patch_priority(keyring.backends.macOS.Keyring, 10.0, request)
    _patch_priority(keyring.backends.Windows.WinVaultKeyring, 5.0, request)

    class UnsafeBackend(KeyringBackend):
        priority = 1
        def get_password(self, s: str, u: str) -> str | None: return None
        def set_password(self, s: str, u: str, p: str) -> None: pass
        def delete_password(self, s: str, u: str) -> None: pass

    # Safe-only chain -> selects first approved leaf
    chainer_safe = ChainerBackend()
    monkeypatch.setattr(ChainerBackend, "backends", [mac_kr, win_kr])
    keyring.set_keyring(chainer_safe)
    assert _select_secure_keyring() is mac_kr

    # Mixed chain with unapproved leaf -> rejected
    monkeypatch.setattr(ChainerBackend, "backends", [mac_kr, UnsafeBackend()])
    keyring.set_keyring(chainer_safe)
    assert _select_secure_keyring() is None

    # Empty chain -> rejected
    monkeypatch.setattr(ChainerBackend, "backends", [])
    keyring.set_keyring(chainer_safe)
    assert _select_secure_keyring() is None


def test_token_store_pins_keyring_backend_instance(request: pytest.FixtureRequest) -> None:
    """TokenStore pins the selected keyring backend and does not follow later global changes."""
    import keyring.backends.macOS
    import keyring.backends.Windows

    mac_kr = keyring.backends.macOS.Keyring()
    win_kr = keyring.backends.Windows.WinVaultKeyring()
    _patch_priority(keyring.backends.macOS.Keyring, 5.0, request)
    _patch_priority(keyring.backends.Windows.WinVaultKeyring, 5.0, request)

    keyring.set_keyring(mac_kr)
    store = TokenStore()
    assert store._get_pinned_keyring() is mac_kr

    # Later global change does not affect the store's pinned backend
    keyring.set_keyring(win_kr)
    assert store._get_pinned_keyring() is mac_kr

def test_native_backend_errors_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keyring backend errors must raise sanitized TokenStoreError with op/domain/type only."""
    class FailingSecureBackend(keyring.backends.macOS.Keyring):
        priority = 5
        def get_password(self, s: str, u: str) -> str | None:
            raise RuntimeError("secret_token_12345 in db error")
        def set_password(self, s: str, u: str, p: str) -> None:
            raise RuntimeError("secret_token_12345 in db error")
        def delete_password(self, s: str, u: str) -> None:
            raise RuntimeError("secret_token_12345 in db error")

    fake_kr = FailingSecureBackend()
    store = TokenStore()
    monkeypatch.setattr(store, "_get_pinned_keyring", lambda: fake_kr)

    entry = _make_sample_entry("canvas.example.edu")
    with pytest.raises(TokenStoreError) as exc_info:
        store.save(entry)
    err_msg = str(exc_info.value)
    assert "secret_token_12345" not in err_msg
    assert "RuntimeError" in err_msg
    assert "canvas.example.edu" in err_msg

    with pytest.raises(TokenStoreError) as exc_info:
        store.load("canvas.example.edu")
    err_msg = str(exc_info.value)
    assert "secret_token_12345" not in err_msg
    assert "RuntimeError" in err_msg
    assert "canvas.example.edu" in err_msg

    with pytest.raises(TokenStoreError) as exc_info:
        store.delete("canvas.example.edu")
    err_msg = str(exc_info.value)
    assert "secret_token_12345" not in err_msg
    assert "RuntimeError" in err_msg
    assert "canvas.example.edu" in err_msg



class SqliteKeyringBackend(KeyringBackend):
    priority = 5

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS credentials (service TEXT, username TEXT, password TEXT, PRIMARY KEY (service, username))"
            )

    def get_password(self, service: str, username: str) -> str | None:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT password FROM credentials WHERE service = ? AND username = ?",
                (service, username),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def set_password(self, service: str, username: str, password: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO credentials (service, username, password) VALUES (?, ?, ?) "
                "ON CONFLICT(service, username) DO UPDATE SET password = excluded.password",
                (service, username, password),
            )

    def delete_password(self, service: str, username: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM credentials WHERE service = ? AND username = ?",
                (service, username),
            )


def _mp_worker_cas(
    db_path: str,
    store_path: str,
    entry_dict: dict[str, Any],
    expected_dict: dict[str, Any] | None,
    is_paused_writer: bool,
    event_inside_lock: Any,
    event_resume: Any,
    event_attempted: Any,
    out_q: Any,
) -> None:
    try:
        entry = StoredTokens.from_store_dict(entry_dict)
        expected = StoredTokens.from_store_dict(expected_dict) if expected_dict is not None else None
        backend = SqliteKeyringBackend(db_path)
        store = TokenStore(Path(store_path))
        store._pinned_keyring = backend
        store._pinned_keyring_resolved = True

        if is_paused_writer:
            orig_set = backend.set_password

            def _paused_set(s: str, u: str, p: str) -> None:
                event_inside_lock.set()
                if not event_resume.wait(timeout=10.0):
                    raise RuntimeError("Timed out waiting for resume event")
                orig_set(s, u, p)

            backend.set_password = _paused_set  # type: ignore

        if event_attempted is not None:
            event_attempted.set()

        store.save(entry, expected=expected)
        out_q.put(("SUCCESS", entry.access_token.get_secret_value()))
    except TokenStoreConflict as exc:
        out_q.put(("CONFLICT", str(exc)))
    except Exception as exc:
        out_q.put(("ERROR", f"{type(exc).__name__}: {exc}"))


def _mp_worker_delete(
    db_path: str,
    store_path: str,
    domain: str,
    out_q: Any,
) -> None:
    try:
        backend = SqliteKeyringBackend(db_path)
        store = TokenStore(Path(store_path))
        store._pinned_keyring = backend
        store._pinned_keyring_resolved = True
        res = store.delete(domain)
        out_q.put(("SUCCESS", res))
    except Exception as exc:
        out_q.put(("ERROR", f"{type(exc).__name__}: {exc}"))


def test_legacy_file_migration_to_keyring(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Loading a domain from legacy file migrates it to keyring and removes it from file."""
    fake = DictKeyring()
    monkeypatch.setattr("canvas_mcp.auth.store._select_secure_keyring", lambda: fake)

    store = TokenStore()
    store.path.parent.mkdir(parents=True, exist_ok=True)
    entry_1 = _make_sample_entry("canvas.example.edu", access_token="leg-1")
    entry_2 = _make_sample_entry("other.example.edu", access_token="leg-2")
    store.path.write_text(
        json.dumps({
            "canvas.example.edu": entry_1.to_store_dict(),
            "other.example.edu": entry_2.to_store_dict(),
        }, indent=2),
        encoding="utf-8",
    )
    loaded = store.load("canvas.example.edu")
    assert loaded is not None
    assert loaded.access_token.get_secret_value() == "leg-1"

    # Migrated to fake keyring
    raw_in_keyring = fake.get_password("canvas-mcp", "canvas.example.edu")
    assert raw_in_keyring is not None
    assert json.loads(raw_in_keyring)["access_token"] == "leg-1"

    # Removed from file, but other domain preserved
    file_content = json.loads(store.path.read_text(encoding="utf-8"))
    assert "canvas.example.edu" not in file_content
    assert "other.example.edu" in file_content


def test_legacy_file_migration_empty_file_preserves_empty_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When last domain is migrated from legacy file, file is preserved with empty dict."""
    fake = DictKeyring()
    monkeypatch.setattr("canvas_mcp.auth.store._select_secure_keyring", lambda: fake)

    store = TokenStore()
    store.path.parent.mkdir(parents=True, exist_ok=True)
    entry = _make_sample_entry("canvas.example.edu", access_token="leg-1")
    store.path.write_text(
        json.dumps({"canvas.example.edu": entry.to_store_dict()}),
        encoding="utf-8",
    )
    loaded = store.load("canvas.example.edu")
    assert loaded is not None

    assert store.path.exists()
    file_content = json.loads(store.path.read_text(encoding="utf-8"))
    assert file_content == {}


def test_migration_existing_native_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If keyring already has domain, native state is authoritative and stale legacy entry is purged."""
    fake = DictKeyring()
    monkeypatch.setattr("canvas_mcp.auth.store._select_secure_keyring", lambda: fake)

    entry_native = _make_sample_entry("canvas.example.edu", access_token="native-tok")
    entry_legacy = _make_sample_entry("canvas.example.edu", access_token="legacy-tok")
    fake.set_password("canvas-mcp", "canvas.example.edu", json.dumps(entry_native.to_store_dict()))

    store = TokenStore()
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps({"canvas.example.edu": entry_legacy.to_store_dict()}),
        encoding="utf-8",
    )
    loaded = store.load("canvas.example.edu")
    assert loaded is not None
    assert loaded.access_token.get_secret_value() == "native-tok"

    # Legacy residue cleaned up
    file_content = json.loads(store.path.read_text(encoding="utf-8"))
    assert "canvas.example.edu" not in file_content


def test_migration_failed_native_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Failed native write during migration raises error and preserves legacy file untouched."""
    class FailingWriteKeyring(DictKeyring):
        def set_password(self, s: str, u: str, p: str) -> None:
            raise RuntimeError("Keyring disk failure")

    fake = FailingWriteKeyring()
    monkeypatch.setattr("canvas_mcp.auth.store._select_secure_keyring", lambda: fake)

    store = TokenStore()
    store.path.parent.mkdir(parents=True, exist_ok=True)
    entry_legacy = _make_sample_entry("canvas.example.edu", access_token="legacy-tok")
    store.path.write_text(
        json.dumps({"canvas.example.edu": entry_legacy.to_store_dict()}),
        encoding="utf-8",
    )
    with pytest.raises(TokenStoreError, match="Failed to save tokens to keyring"):
        store.load("canvas.example.edu")

    # File preserved
    file_content = json.loads(store.path.read_text(encoding="utf-8"))
    assert "canvas.example.edu" in file_content


def test_migration_failed_readback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Failed readback during migration raises error and preserves legacy file untouched."""
    class BadReadbackKeyring(DictKeyring):
        def get_password(self, s: str, u: str) -> str | None:
            # Return None or different entry on readback
            return None

    fake = BadReadbackKeyring()
    monkeypatch.setattr("canvas_mcp.auth.store._select_secure_keyring", lambda: fake)

    store = TokenStore()
    store.path.parent.mkdir(parents=True, exist_ok=True)
    entry_legacy = _make_sample_entry("canvas.example.edu", access_token="legacy-tok")
    store.path.write_text(
        json.dumps({"canvas.example.edu": entry_legacy.to_store_dict()}),
        encoding="utf-8",
    )
    with pytest.raises(TokenStoreError, match="Failed to verify migrated tokens in keyring"):
        store.load("canvas.example.edu")

    # File preserved
    file_content = json.loads(store.path.read_text(encoding="utf-8"))
    assert "canvas.example.edu" in file_content


def test_migration_failed_legacy_replacement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Failed legacy rewrite retains native state and next load retries cleanup."""
    fake = DictKeyring()
    monkeypatch.setattr("canvas_mcp.auth.store._select_secure_keyring", lambda: fake)

    store = TokenStore()
    store.path.parent.mkdir(parents=True, exist_ok=True)
    entry_legacy = _make_sample_entry("canvas.example.edu", access_token="legacy-tok")
    store.path.write_text(
        json.dumps({"canvas.example.edu": entry_legacy.to_store_dict()}),
        encoding="utf-8",
    )

    orig_replace = os.replace

    def failing_replace(src: Any, dst: Any) -> None:
        raise OSError("Read-only filesystem")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(TokenStoreError, match="Failed to write token file"):
        store.load("canvas.example.edu")

    # Native state retained
    assert fake.get_password("canvas-mcp", "canvas.example.edu") is not None

    # Restore replace and next load cleans up stale legacy entry
    monkeypatch.setattr(os, "replace", orig_replace)
    loaded = store.load("canvas.example.edu")
    assert loaded is not None
    assert loaded.access_token.get_secret_value() == "legacy-tok"
    file_content = json.loads(store.path.read_text(encoding="utf-8"))
    assert "canvas.example.edu" not in file_content


def test_cross_process_keyring_cas_multiprocessing(tmp_path: Path) -> None:
    """Two spawned processes saving with same expected credential serialize with one winner and one conflict."""
    ctx = multiprocessing.get_context("spawn")
    db_path = str(tmp_path / "keyring.db")
    store_path = str(tmp_path / "tokens.json")

    # Seed initial entry in SQLite keyring
    initial_entry = _make_sample_entry("canvas.example.edu", access_token="initial-tok")
    init_backend = SqliteKeyringBackend(db_path)
    init_backend.set_password("canvas-mcp", "canvas.example.edu", json.dumps(initial_entry.to_store_dict()))

    entry_a = _make_sample_entry("canvas.example.edu", access_token="tok-worker-a")
    entry_b = _make_sample_entry("canvas.example.edu", access_token="tok-worker-b")

    event_inside_lock = ctx.Event()
    event_resume = ctx.Event()
    event_attempted_b = ctx.Event()
    out_q = ctx.Queue()

    proc_a = ctx.Process(
        target=_mp_worker_cas,
        args=(
            db_path,
            store_path,
            entry_a.to_store_dict(),
            initial_entry.to_store_dict(),
            True,
            event_inside_lock,
            event_resume,
            None,
            out_q,
        ),
    )
    proc_b = ctx.Process(
        target=_mp_worker_cas,
        args=(
            db_path,
            store_path,
            entry_b.to_store_dict(),
            initial_entry.to_store_dict(),
            False,
            None,
            None,
            event_attempted_b,
            out_q,
        ),
    )

    proc_a.start()
    assert event_inside_lock.wait(timeout=5.0), "Worker A did not enter lock"

    proc_b.start()
    assert event_attempted_b.wait(timeout=5.0), "Worker B did not start attempt"

    # Release Worker A to finish
    event_resume.set()

    proc_a.join(timeout=10.0)
    proc_b.join(timeout=10.0)
    assert not proc_a.is_alive(), "Worker A timed out"
    assert not proc_b.is_alive(), "Worker B timed out"

    res_1 = out_q.get(timeout=2.0)
    res_2 = out_q.get(timeout=2.0)

    statuses = [res_1[0], res_2[0]]
    assert "SUCCESS" in statuses
    assert "CONFLICT" in statuses

    # Winner equals stored entry in SQLite
    winner_token = res_1[1] if res_1[0] == "SUCCESS" else res_2[1]
    final_raw = init_backend.get_password("canvas-mcp", "canvas.example.edu")
    assert final_raw is not None
    assert json.loads(final_raw)["access_token"] == winner_token

    # Test unconditional login contender
    entry_login = _make_sample_entry("canvas.example.edu", access_token="tok-cli-login")
    proc_login = ctx.Process(
        target=_mp_worker_cas,
        args=(
            db_path,
            store_path,
            entry_login.to_store_dict(),
            None,  # expected=None
            False,
            None,
            None,
            None,
            out_q,
        ),
    )
    proc_login.start()
    proc_login.join(timeout=5.0)
    assert not proc_login.is_alive()
    login_res = out_q.get(timeout=2.0)
    assert login_res[0] == "SUCCESS"
    final_raw = init_backend.get_password("canvas-mcp", "canvas.example.edu")
    assert final_raw is not None
    assert json.loads(final_raw)["access_token"] == "tok-cli-login"

    # Test delete contender
    proc_del = ctx.Process(
        target=_mp_worker_delete,
        args=(
            db_path,
            store_path,
            "canvas.example.edu",
            out_q,
        ),
    )
    proc_del.start()
    proc_del.join(timeout=5.0)
    assert not proc_del.is_alive()
    del_res = out_q.get(timeout=2.0)
    assert del_res[0] == "SUCCESS"
    assert del_res[1] is True
    assert init_backend.get_password("canvas-mcp", "canvas.example.edu") is None
