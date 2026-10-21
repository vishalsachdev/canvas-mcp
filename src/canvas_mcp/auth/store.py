"""Secure local token store with OS credential manager (Keyring), file locking, atomic replace, and permission checks."""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout
from pydantic import ValidationError

from canvas_mcp.auth.mobile import normalize_domain
from canvas_mcp.auth.models import (
    StoredTokens,
    TokenStoreConflict,
    TokenStoreError,
)

logger = logging.getLogger(__name__)
DEFAULT_STORE_DIR = Path.home() / ".canvas-mcp"
DEFAULT_STORE_PATH = DEFAULT_STORE_DIR / "tokens.json"
KEYRING_SERVICE_NAME = "canvas-mcp"
ALLOW_FILE_STORE_ENV = "CANVAS_ALLOW_FILE_TOKEN_STORE"


def _check_no_symlink(p: Path, name: str) -> None:
    """Reject path if it or any component is a symbolic link."""
    curr: Path | None = p
    while curr is not None and curr != curr.parent:
        if os.path.islink(str(curr)):
            raise TokenStoreError(f"Rejecting symlink for {name}: {curr}")
        curr = curr.parent


def _verify_and_tighten_windows_permissions(p: Path, *, is_dir: bool) -> None:
    """Enforce private ACLs (remove inheritance, grant full control only to current user) on Windows."""
    if os.name != "nt":
        return
    if not p.exists():
        return
    username = os.environ.get("USERNAME")
    if not username:
        try:
            import getpass

            username = getpass.getuser()
        except Exception:
            return
    grant_perm = "(OI)(CI)F" if is_dir else "F"
    cmd = ["icacls", str(p), "/inheritance:r", "/grant:r", f"{username}:{grant_perm}"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode != 0:
            raise TokenStoreError(
                f"Failed to tighten Windows ACLs on {p}: {res.stderr.strip()}"
            )
    except FileNotFoundError:
        pass
    except OSError as e:
        raise TokenStoreError(f"Failed to execute icacls on {p}: {e}") from None


def _verify_and_tighten_posix_permissions(p: Path, *, is_dir: bool) -> None:
    """Enforce private ownership and permissions (0700 dir, 0600 file) on POSIX."""
    if os.name == "nt":
        return

    if not p.exists():
        return

    try:
        st = p.stat()
    except OSError as e:
        raise TokenStoreError(f"Failed to stat {p}: {e}") from e

    # Verify ownership
    current_uid = os.getuid()
    if st.st_uid != current_uid:
        raise TokenStoreError(
            f"Path {p} is owned by UID {st.st_uid}, but current process is UID {current_uid}"
        )

    # Tighten permissions if group or other have any bits
    target_mode = 0o700 if is_dir else 0o600
    if (st.st_mode & 0o077) != 0:
        try:
            os.chmod(p, target_mode)
            st_new = p.stat()
            if (st_new.st_mode & 0o077) != 0:
                raise TokenStoreError(
                    f"Failed to remove group/world permissions from {p}"
                )
        except OSError as e:
            raise TokenStoreError(f"Failed to tighten permissions on {p}: {e}") from e


def _verify_and_tighten_permissions(p: Path, *, is_dir: bool) -> None:
    """Enforce private ownership and permissions/ACLs across POSIX and Windows."""
    if os.name == "nt":
        _verify_and_tighten_windows_permissions(p, is_dir=is_dir)
    else:
        _verify_and_tighten_posix_permissions(p, is_dir=is_dir)


def _is_os_keyring_viable() -> bool:
    """Check if a secure OS credential store backend is available and active."""
    try:
        import keyring

        kr = keyring.get_keyring()
        if getattr(kr, "priority", 0) <= 0:
            return False
        name = kr.__class__.__name__.lower()
        if "fail" in name or "null" in name:
            return False
        return True
    except Exception:
        return False


class TokenStore:
    """Domain-keyed token storage using OS credential manager (Keyring) or private local file."""

    def __init__(self, path: Path | None = None) -> None:
        self._custom_path = path is not None
        self.path = path.absolute() if path is not None else DEFAULT_STORE_PATH

    @property
    def lock_path(self) -> Path:
        return Path(f"{self.path}.lock")

    def _use_keyring(self) -> bool:
        if self._custom_path:
            return False
        if os.environ.get(ALLOW_FILE_STORE_ENV) == "force":
            return False
        return _is_os_keyring_viable()

    def _is_file_store_allowed(self) -> bool:
        if self._custom_path:
            return True
        val = os.environ.get(ALLOW_FILE_STORE_ENV, "").lower()
        return val in ("1", "true", "yes", "force")

    def _read_map_unlocked(self) -> dict[str, StoredTokens]:
        """Read and validate all entries from disk. Returns empty dict if file absent."""
        _check_no_symlink(self.path.parent, "store directory")
        _check_no_symlink(self.path, "store file")

        if self.path.parent.exists():
            _verify_and_tighten_permissions(self.path.parent, is_dir=True)

        if not self.path.exists():
            return {}

        _verify_and_tighten_permissions(self.path, is_dir=False)

        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError as e:
            raise TokenStoreError(
                f"Failed to read token store at {self.path}: {e}"
            ) from e

        try:
            data = json.loads(raw)
        except Exception as e:
            raise TokenStoreError(
                f"Corrupt JSON in token store at {self.path}: {type(e).__name__}"
            ) from None
        if not isinstance(data, dict):
            raise TokenStoreError(
                f"Token store at {self.path} must contain a JSON object, got {type(data).__name__}"
            )

        result: dict[str, StoredTokens] = {}
        for key, entry_dict in data.items():
            if not isinstance(entry_dict, dict):
                raise TokenStoreError(
                    f"Invalid entry for '{key}' in {self.path}: expected object"
                )
            try:
                tokens = StoredTokens.from_store_dict(entry_dict)
            except ValidationError as e:
                field_errors = []
                for err in e.errors():
                    loc = ".".join(str(p) for p in err.get("loc", []))
                    msg = err.get("msg", "invalid")
                    field_errors.append(f"{loc}: {msg}" if loc else msg)
                err_summary = "; ".join(field_errors)
                raise TokenStoreError(
                    f"Invalid token entry schema for '{key}' in {self.path}: {err_summary}"
                ) from None
            except Exception as e:
                raise TokenStoreError(
                    f"Invalid token entry schema for '{key}' in {self.path}: {type(e).__name__}"
                ) from None

            if tokens.canvas_domain != key:
                raise TokenStoreError(
                    f"Domain mismatch in token store: key '{key}' != entry domain '{tokens.canvas_domain}'"
                )
            result[key] = tokens

        return result

    def load(self, domain: str) -> StoredTokens | None:
        """Load stored tokens for the given Canvas domain, or None if absent."""
        norm_domain = normalize_domain(domain)
        if self._use_keyring():
            try:
                import keyring

                raw = keyring.get_password(KEYRING_SERVICE_NAME, norm_domain)
                if raw is not None:
                    data = json.loads(raw)
                    return StoredTokens.from_store_dict(data)
            except Exception as e:
                logger.debug(
                    "Failed to load tokens from keyring for %s: %s", norm_domain, e
                )
            # Check if file has legacy token if absent in keyring
            if self.path.exists():
                return self._read_map_unlocked().get(norm_domain)
            return None

        entries = self._read_map_unlocked()
        return entries.get(norm_domain)

    def save(
        self, entry: StoredTokens, *, expected: StoredTokens | None = None
    ) -> None:
        """Save token entry with atomic write, file lock, and optional compare-and-swap."""
        norm_domain = normalize_domain(entry.canvas_domain)
        if entry.canvas_domain != norm_domain:
            raise TokenStoreError(
                f"Entry domain '{entry.canvas_domain}' does not match normalized domain '{norm_domain}'"
            )

        if self._use_keyring():
            try:
                import keyring

                if expected is not None:
                    raw_existing = keyring.get_password(
                        KEYRING_SERVICE_NAME, norm_domain
                    )
                    if raw_existing is None:
                        raise TokenStoreConflict(
                            f"Token store conflict: expected existing entry for '{norm_domain}', but found none in keyring"
                        )
                    existing_entry = StoredTokens.from_store_dict(
                        json.loads(raw_existing)
                    )
                    if (
                        existing_entry.access_token.get_secret_value()
                        != expected.access_token.get_secret_value()
                        or existing_entry.refresh_token.get_secret_value()
                        != expected.refresh_token.get_secret_value()
                        or existing_entry.client_secret.get_secret_value()
                        != expected.client_secret.get_secret_value()
                        or existing_entry.last_refreshed_at != expected.last_refreshed_at
                    ):
                        raise TokenStoreConflict(
                            f"Token store conflict: tokens for '{norm_domain}' were updated by another process"
                        )

                payload = json.dumps(entry.to_store_dict())
                keyring.set_password(KEYRING_SERVICE_NAME, norm_domain, payload)
                return
            except TokenStoreConflict:
                raise
            except Exception as e:
                raise TokenStoreError(f"Failed to save tokens to keyring: {e}") from None

        if not self._is_file_store_allowed():
            raise TokenStoreError(
                "No secure OS credential store available (Windows Credential Manager, "
                "macOS Keychain, or Freedesktop Secret Service). Refusing to persist unencrypted credentials. "
                "Set CANVAS_ALLOW_FILE_TOKEN_STORE=1 to permit secure file storage with private permissions."
            )

        store_dir = self.path.parent
        _check_no_symlink(store_dir, "store directory")
        _check_no_symlink(self.path, "store file")
        _check_no_symlink(self.lock_path, "lock file")

        # Ensure directory exists with 0700
        if not store_dir.exists():
            try:
                store_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
                if os.name != "nt":
                    os.chmod(store_dir, 0o700)
                else:
                    _verify_and_tighten_windows_permissions(store_dir, is_dir=True)
            except OSError as e:
                raise TokenStoreError(
                    f"Failed to create token store directory {store_dir}: {e}"
                ) from e
        else:
            _verify_and_tighten_permissions(store_dir, is_dir=True)

        try:
            lock = FileLock(str(self.lock_path), timeout=5, mode=0o600)
            with lock:
                _check_no_symlink(store_dir, "store directory")
                _check_no_symlink(self.path, "store file")
                _check_no_symlink(self.lock_path, "lock file")
                _verify_and_tighten_permissions(self.lock_path, is_dir=False)
                current_map = self._read_map_unlocked()

                if expected is not None:
                    existing = current_map.get(norm_domain)
                    if existing is None:
                        raise TokenStoreConflict(
                            f"Token store conflict: expected existing entry for '{norm_domain}', but found none"
                        )
                    if (
                        existing.access_token.get_secret_value()
                        != expected.access_token.get_secret_value()
                        or existing.refresh_token.get_secret_value()
                        != expected.refresh_token.get_secret_value()
                        or existing.client_secret.get_secret_value()
                        != expected.client_secret.get_secret_value()
                        or existing.last_refreshed_at != expected.last_refreshed_at
                    ):
                        raise TokenStoreConflict(
                            f"Token store conflict: tokens for '{norm_domain}' were updated by another process"
                        )

                current_map[norm_domain] = entry

                # Serialize map
                serialized: dict[str, Any] = {
                    k: v.to_store_dict() for k, v in current_map.items()
                }
                payload_bytes = json.dumps(serialized, indent=2).encode("utf-8")

                # Write atomically via tempfile in store_dir
                fd, tmp_str = tempfile.mkstemp(
                    dir=store_dir,
                    prefix="tokens-",
                    suffix=".tmp",
                )
                tmp_path = Path(tmp_str)
                try:
                    if os.name != "nt":
                        os.chmod(tmp_path, 0o600)
                    else:
                        _verify_and_tighten_windows_permissions(tmp_path, is_dir=False)
                    with os.fdopen(fd, "wb") as f:
                        f.write(payload_bytes)
                        f.flush()
                        os.fsync(f.fileno())

                    os.replace(tmp_path, self.path)
                    if os.name != "nt":
                        os.chmod(self.path, 0o600)
                    else:
                        _verify_and_tighten_windows_permissions(self.path, is_dir=False)
                except Exception as e:
                    if tmp_path.exists():
                        try:
                            tmp_path.unlink()
                        except OSError as unlink_err:
                            logger.debug(
                                "Failed to remove temporary store file %s: %s",
                                tmp_path,
                                unlink_err,
                            )
                    raise TokenStoreError(
                        f"Failed to write token file {self.path}: {e}"
                    ) from None

        except Timeout as e:
            raise TokenStoreError(
                f"Timeout waiting for token store lock at {self.lock_path}"
            ) from e
        except TokenStoreError:
            raise
        except Exception as e:
            raise TokenStoreError(f"Unexpected error saving token store: {e}") from None

    def delete(self, domain: str) -> bool:
        """Delete stored tokens for domain. Returns True if deleted, False if absent."""
        norm_domain = normalize_domain(domain)
        deleted = False
        if self._use_keyring():
            try:
                import keyring
                from keyring.errors import PasswordDeleteError

                try:
                    keyring.delete_password(KEYRING_SERVICE_NAME, norm_domain)
                    deleted = True
                except PasswordDeleteError:
                    pass
            except Exception as e:
                logger.debug(
                    "Failed to delete tokens from keyring for %s: %s", norm_domain, e
                )

        if self.path.exists():
            store_dir = self.path.parent
            lock = FileLock(str(self.lock_path), timeout=5, mode=0o600)
            with lock:
                current_map = self._read_map_unlocked()
                if norm_domain in current_map:
                    del current_map[norm_domain]
                    deleted = True
                    serialized = {
                        k: v.to_store_dict() for k, v in current_map.items()
                    }
                    payload_bytes = json.dumps(serialized, indent=2).encode("utf-8")
                    fd, tmp_str = tempfile.mkstemp(
                        dir=store_dir,
                        prefix="tokens-",
                        suffix=".tmp",
                    )
                    tmp_path = Path(tmp_str)
                    try:
                        if os.name != "nt":
                            os.chmod(tmp_path, 0o600)
                        else:
                            _verify_and_tighten_windows_permissions(tmp_path, is_dir=False)
                        with os.fdopen(fd, "wb") as f:
                            f.write(payload_bytes)
                            f.flush()
                            os.fsync(f.fileno())
                        os.replace(tmp_path, self.path)
                        if os.name != "nt":
                            os.chmod(self.path, 0o600)
                        else:
                            _verify_and_tighten_windows_permissions(self.path, is_dir=False)
                    except Exception as e:
                        if tmp_path.exists():
                            try:
                                tmp_path.unlink()
                            except OSError:
                                pass
                        raise TokenStoreError(f"Failed to delete token file {self.path}: {e}") from None

        return deleted
