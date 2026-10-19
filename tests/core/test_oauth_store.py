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
