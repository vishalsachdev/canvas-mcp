"""Secure local token store with OS credential manager (Keyring), file locking, atomic replace, and permission checks."""

import base64
import collections.abc
from contextlib import contextmanager
import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from filelock import FileLock, Timeout
from keyring.backend import KeyringBackend
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

_WIN_ACL_SCRIPT = """
$ErrorActionPreference = 'Stop'
$targetPath = $env:CANVAS_MCP_ACL_PATH
$isDir = ($env:CANVAS_MCP_ACL_IS_DIR -eq '1')

if (-not $targetPath -or -not (Test-Path -LiteralPath $targetPath)) {
    throw "Target path does not exist"
}

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$sid = $identity.User
if (-not $sid) {
    throw "Cannot determine current Windows SID"
}

$currentAcl = Get-Acl -LiteralPath $targetPath
$currentOwner = $currentAcl.GetOwner([System.Security.Principal.SecurityIdentifier])
if ($currentOwner -ne $sid) {
    throw "Target path is owned by another principal"
}

if ($isDir) {
    $acl = New-Object System.Security.AccessControl.DirectorySecurity
    $inherit = [System.Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
} else {
    $acl = New-Object System.Security.AccessControl.FileSecurity
    $inherit = [System.Security.AccessControl.InheritanceFlags]::None
}

$acl.SetOwner($sid)
$acl.SetAccessRuleProtection($true, $false)

$prop = [System.Security.AccessControl.PropagationFlags]::None
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    $sid,
    [System.Security.AccessControl.FileSystemRights]::FullControl,
    $inherit,
    $prop,
    [System.Security.AccessControl.AccessControlType]::Allow
)
$acl.AddAccessRule($rule)

Set-Acl -LiteralPath $targetPath -AclObject $acl

$readbackAcl = Get-Acl -LiteralPath $targetPath
$verifiedOwner = $readbackAcl.GetOwner([System.Security.Principal.SecurityIdentifier])
if ($verifiedOwner -ne $sid) {
    throw "Verified owner mismatch"
}
if (-not $readbackAcl.AreAccessRulesProtected) {
    throw "Access rules are not protected from inheritance"
}

$rules = $readbackAcl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])
if ($rules.Count -ne 1) {
    throw "Expected exactly 1 access rule"
}
$vRule = $rules[0]
if ($vRule.IdentityReference -ne $sid) {
    throw "Access rule identity mismatch"
}
if ($vRule.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow) {
    throw "Access rule is not Allow"
}
if ($vRule.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::FullControl -ne [System.Security.AccessControl.FileSystemRights]::FullControl) {
    throw "Access rule does not grant FullControl"
}
if ($vRule.IsInherited) {
    throw "Access rule is inherited"
}
if ($vRule.InheritanceFlags -ne $inherit) {
    throw "Inheritance flags mismatch"
}
if ($vRule.PropagationFlags -ne $prop) {
    throw "Propagation flags mismatch"
}

[Console]::Out.Write("CANVAS_MCP_PRIVATE_ACL_OK")
"""

_WIN_ACL_ENCODED = base64.b64encode(_WIN_ACL_SCRIPT.encode("utf-16le")).decode("ascii")


def _verify_and_tighten_windows_permissions(p: Path, *, is_dir: bool) -> None:
    """Enforce and verify private DACL (current SID only, full control, no inheritance) on Windows."""
    if os.name != "nt":
        return
    if not p.exists():
        return

    system_root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
    if not system_root:
        raise TokenStoreError("Cannot establish private Windows permissions for token storage")

    ps_exe = os.path.join(system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    if not os.path.exists(ps_exe):
        raise TokenStoreError("Cannot establish private Windows permissions for token storage")

    child_env = os.environ.copy()
    child_env["CANVAS_MCP_ACL_PATH"] = str(p.resolve())
    child_env["CANVAS_MCP_ACL_IS_DIR"] = "1" if is_dir else "0"

    try:
        res = subprocess.run(
            [ps_exe, "-NoProfile", "-NonInteractive", "-EncodedCommand", _WIN_ACL_ENCODED],
            env=child_env,
            capture_output=True,
            text=True,
            timeout=15.0,
            shell=False,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        raise TokenStoreError("Cannot establish private Windows permissions for token storage") from None

    if res.returncode != 0 or res.stdout.strip() != "CANVAS_MCP_PRIVATE_ACL_OK":
        raise TokenStoreError("Cannot establish private Windows permissions for token storage")

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


def _get_trusted_backend_classes() -> tuple[type, ...]:
    classes: list[type] = []
    try:
        import keyring.backends.macOS
        classes.append(keyring.backends.macOS.Keyring)
    except (ImportError, AttributeError) as exc:
        logger.debug("macOS keyring backend unavailable: %s", exc)
    try:
        import keyring.backends.Windows
        classes.append(keyring.backends.Windows.WinVaultKeyring)
    except (ImportError, AttributeError) as exc:
        logger.debug("Windows keyring backend unavailable: %s", exc)
    try:
        import keyring.backends.SecretService
        classes.append(keyring.backends.SecretService.Keyring)
    except (ImportError, AttributeError) as exc:
        logger.debug("SecretService keyring backend unavailable: %s", exc)
    return tuple(classes)


def _safe_priority(backend: KeyringBackend) -> float:
    try:
        return float(getattr(backend, "priority", 0))
    except (RuntimeError, AttributeError, ValueError, TypeError) as exc:
        logger.debug("Failed to read priority for %s: %s", backend, exc)
        return 0.0


def _secure_keyring_leaf(backend: KeyringBackend) -> KeyringBackend | None:
    trusted_classes = _get_trusted_backend_classes()
    if type(backend) in trusted_classes:
        if _safe_priority(backend) > 0:
            return backend
        return None

    try:
        from keyring.backends.chainer import ChainerBackend

        if type(backend) is ChainerBackend:
            backends = list(getattr(backend, "backends", []))
            if not backends:
                return None
            for leaf in backends:
                if (
                    type(leaf) not in trusted_classes
                    or _safe_priority(leaf) <= 0
                ):
                    return None
            return backends[0]
    except (ImportError, AttributeError) as exc:
        logger.debug("ChainerBackend unavailable or malformed: %s", exc)

    return None


def _select_secure_keyring() -> KeyringBackend | None:
    """Select and return an approved native OS keyring backend, or None if unavailable."""
    try:
        import keyring.core

        kr = keyring.core.get_keyring()
        if kr is None:
            return None
        return _secure_keyring_leaf(kr)
    except (ImportError, AttributeError, RuntimeError) as exc:
        logger.debug("Failed to discover secure OS keyring backend: %s", exc)
        return None

class TokenStore:
    """Domain-keyed token storage using OS credential manager (Keyring) or private local file."""

    def __init__(self, path: Path | None = None) -> None:
        self._custom_path = path is not None
        self.path = path.absolute() if path is not None else DEFAULT_STORE_PATH
        self._pinned_keyring_resolved: bool = False
        self._pinned_keyring: KeyringBackend | None = None

    @property
    def lock_path(self) -> Path:
        return Path(f"{self.path}.lock")

    def _get_pinned_keyring(self) -> KeyringBackend | None:
        if not self._pinned_keyring_resolved:
            if self._custom_path:
                self._pinned_keyring = None
            elif os.environ.get(ALLOW_FILE_STORE_ENV) == "force":
                self._pinned_keyring = None
            else:
                self._pinned_keyring = _select_secure_keyring()
            self._pinned_keyring_resolved = True
        return self._pinned_keyring

    def _use_keyring(self) -> bool:
        return self._get_pinned_keyring() is not None
    def _is_file_store_allowed(self) -> bool:
        if self._custom_path:
            return True
        val = os.environ.get(ALLOW_FILE_STORE_ENV, "").lower()
        return val in ("1", "true", "yes", "force")

    @contextmanager
    def _locked(self) -> collections.abc.Iterator[None]:
        store_dir = self.path.parent
        _check_no_symlink(store_dir, "store directory")
        _check_no_symlink(self.path, "store file")
        _check_no_symlink(self.lock_path, "lock file")

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

        lock = FileLock(str(self.lock_path), timeout=5, mode=0o600)
        try:
            with lock:
                _check_no_symlink(store_dir, "store directory")
                _check_no_symlink(self.path, "store file")
                _check_no_symlink(self.lock_path, "lock file")
                _verify_and_tighten_permissions(self.lock_path, is_dir=False)
                yield
        except Timeout:
            raise TokenStoreError(
                f"Timeout waiting for token store lock at {self.lock_path}"
            ) from None

    def _write_map_unlocked(self, entries: dict[str, StoredTokens]) -> None:
        store_dir = self.path.parent
        _check_no_symlink(store_dir, "store directory")
        _check_no_symlink(self.path, "store file")

        serialized: dict[str, Any] = {
            k: v.to_store_dict() for k, v in entries.items()
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
                except OSError as unlink_err:
                    logger.debug(
                        "Failed to remove temporary store file %s: %s",
                        tmp_path,
                        unlink_err,
                    )
            raise TokenStoreError(
                f"Failed to write token file {self.path}: {type(e).__name__}"
            ) from None

    def _read_keyring_unlocked(self, domain: str) -> StoredTokens | None:
        kr = self._get_pinned_keyring()
        if kr is None:
            return None
        try:
            raw = kr.get_password(KEYRING_SERVICE_NAME, domain)
        except Exception as e:
            raise TokenStoreError(
                f"Failed to read tokens from keyring for {domain}: {type(e).__name__}"
            ) from None

        if raw is None:
            return None

        try:
            data = json.loads(raw)
            entry = StoredTokens.from_store_dict(data)
        except Exception as e:
            raise TokenStoreError(
                f"Corrupt token entry in keyring for {domain}: {type(e).__name__}"
            ) from None

        if entry.canvas_domain != domain:
            raise TokenStoreError(
                f"Stored domain '{entry.canvas_domain}' does not match requested '{domain}'"
            )
        return entry

    def _assert_expected(
        self,
        existing: StoredTokens | None,
        expected: StoredTokens | None,
        domain: str,
    ) -> None:
        if expected is None:
            return
        if existing is None:
            raise TokenStoreConflict(
                f"Token store conflict: expected existing entry for '{domain}', but found none"
            )
        if existing != expected:
            raise TokenStoreConflict(
                f"Token store conflict: tokens for '{domain}' were updated by another process"
            )

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
        with self._locked():
            kr = self._get_pinned_keyring()
            if kr is not None:
                native_entry = self._read_keyring_unlocked(norm_domain)
                if native_entry is None:
                    # Check legacy file for migration
                    if self.path.exists():
                        legacy_map = self._read_map_unlocked()
                        if norm_domain in legacy_map:
                            entry = legacy_map[norm_domain]
                            # Write to native backend
                            payload = json.dumps(entry.to_store_dict())
                            try:
                                kr.set_password(KEYRING_SERVICE_NAME, norm_domain, payload)
                            except Exception as e:
                                raise TokenStoreError(
                                    f"Failed to save tokens to keyring for {norm_domain}: {type(e).__name__}"
                                ) from None
                            # Verify readback
                            readback = self._read_keyring_unlocked(norm_domain)
                            if readback != entry:
                                raise TokenStoreError(
                                    f"Failed to verify migrated tokens in keyring for {norm_domain}: readback mismatch"
                                )
                            # Cleanup legacy file entry
                            del legacy_map[norm_domain]
                            self._write_map_unlocked(legacy_map)
                            return entry
                    return None
                else:
                    # Native entry exists; cleanup stale legacy domain residue if present
                    if self.path.exists():
                        legacy_map = self._read_map_unlocked()
                        if norm_domain in legacy_map:
                            del legacy_map[norm_domain]
                            self._write_map_unlocked(legacy_map)
                    return native_entry

            if not self._is_file_store_allowed():
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

        with self._locked():
            kr = self._get_pinned_keyring()
            if kr is not None:
                # Reconcile native/legacy state before CAS
                native_entry = self._read_keyring_unlocked(norm_domain)
                if native_entry is None and self.path.exists():
                    legacy_map = self._read_map_unlocked()
                    existing = legacy_map.get(norm_domain)
                else:
                    existing = native_entry

                self._assert_expected(existing, expected, norm_domain)

                payload = json.dumps(entry.to_store_dict())
                try:
                    kr.set_password(KEYRING_SERVICE_NAME, norm_domain, payload)
                except Exception as e:
                    raise TokenStoreError(
                        f"Failed to save tokens to keyring for {norm_domain}: {type(e).__name__}"
                    ) from None

                readback = self._read_keyring_unlocked(norm_domain)
                if readback != entry:
                    raise TokenStoreError(
                        f"Failed to verify saved tokens in keyring for {norm_domain}: readback mismatch"
                    )

                # Remove same-domain legacy residue if present
                if self.path.exists():
                    legacy_map = self._read_map_unlocked()
                    if norm_domain in legacy_map:
                        del legacy_map[norm_domain]
                        self._write_map_unlocked(legacy_map)
                return

            if not self._is_file_store_allowed():
                raise TokenStoreError(
                    "No secure OS credential store available (Windows Credential Manager, "
                    "macOS Keychain, or Freedesktop Secret Service). Refusing to persist unencrypted credentials. "
                    "Set CANVAS_ALLOW_FILE_TOKEN_STORE=1 to permit secure file storage with private permissions."
                )

            current_map = self._read_map_unlocked()
            existing = current_map.get(norm_domain)
            self._assert_expected(existing, expected, norm_domain)
            current_map[norm_domain] = entry
            self._write_map_unlocked(current_map)

    def delete(self, domain: str) -> bool:
        """Delete stored tokens for domain. Returns True if deleted, False if absent."""
        norm_domain = normalize_domain(domain)
        with self._locked():
            kr = self._get_pinned_keyring()
            if kr is not None:
                had_legacy = False
                if self.path.exists():
                    legacy_map = self._read_map_unlocked()
                    if norm_domain in legacy_map:
                        del legacy_map[norm_domain]
                        self._write_map_unlocked(legacy_map)
                        had_legacy = True

                native_entry = self._read_keyring_unlocked(norm_domain)
                had_native = native_entry is not None
                if had_native:
                    try:
                        kr.delete_password(KEYRING_SERVICE_NAME, norm_domain)
                    except Exception as e:
                        raise TokenStoreError(
                            f"Failed to delete tokens from keyring for {norm_domain}: {type(e).__name__}"
                        ) from None

                return had_legacy or had_native

            if not self.path.exists():
                return False

            current_map = self._read_map_unlocked()
            if norm_domain not in current_map:
                return False
            del current_map[norm_domain]
            self._write_map_unlocked(current_map)
            return True
