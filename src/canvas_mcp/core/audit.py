"""Structured audit logging for Canvas MCP Server.

Provides FERPA-compliant audit trail for data access and code execution events.
Events are emitted as JSON lines to both stderr and a rotating log file.

Controlled by:
- LOG_ACCESS_EVENTS: Enable data access audit events (default: false)
- LOG_EXECUTION_EVENTS: Enable code execution audit events (default: false)
- AUDIT_LOG_DIR: Directory for audit log files (default: ~/.canvas-mcp/)
"""

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

# Separate logger for audit events (not the main application logger)
_audit_logger = logging.getLogger("canvas_mcp.audit")
_audit_logger.setLevel(logging.INFO)
_audit_logger.propagate = False  # Don't propagate to root/parent loggers

# Module-level flags (set by init_audit_logging)
_access_events_enabled = False
_execution_events_enabled = False
_initialized = False

# Regex to replace numeric path segments
_NUMERIC_PATH_RE = re.compile(r"/\d+")

# Audit log file settings
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 5
_AUDIT_FILENAME = "audit.jsonl"


def _sanitize_endpoint(endpoint: str) -> str:
    """Replace numeric IDs in endpoint paths with '***'.

    Example: /courses/12345/users/678 → /courses/***/users/***
    """
    return _NUMERIC_PATH_RE.sub("/***", endpoint)


def init_audit_logging() -> None:
    """Initialize audit logging based on configuration.

    Sets up stderr and file handlers for the audit logger.
    Called once during server startup.
    """
    global _access_events_enabled, _execution_events_enabled, _initialized

    if _initialized:
        return

    from .config import get_config
    config = get_config()

    _access_events_enabled = config.log_access_events
    _execution_events_enabled = config.log_execution_events

    if not _access_events_enabled and not _execution_events_enabled:
        _initialized = True
        return

    # Stderr handler — JSON lines to stderr
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.INFO)
    stderr_handler.setFormatter(logging.Formatter("%(message)s"))
    _audit_logger.addHandler(stderr_handler)

    # File handler — rotating JSON lines file
    audit_dir_str = config.audit_log_dir
    if not audit_dir_str:
        audit_dir = Path.home() / ".canvas-mcp"
    else:
        audit_dir = Path(audit_dir_str)

    try:
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_file = audit_dir / _AUDIT_FILENAME
        file_handler = RotatingFileHandler(
            str(audit_file),
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter("%(message)s"))
        _audit_logger.addHandler(file_handler)
    except OSError:
        # If we can't write to the audit dir, log to stderr only
        print(
            f"Warning: Could not create audit log directory {audit_dir}. "
            "Audit events will be written to stderr only.",
            file=sys.stderr,
        )

    _initialized = True


def _emit(event: dict[str, Any]) -> None:
    """Emit a structured JSON audit event."""
    event["timestamp"] = datetime.now(timezone.utc).isoformat()
    _audit_logger.info(json.dumps(event, default=str))


def log_data_access(
    method: str,
    endpoint: str,
    status: str,
    error: str | None = None,
) -> None:
    """Log a data access audit event.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        endpoint: Canvas API endpoint (will be sanitized)
        status: "success" or "error"
        error: Optional error message
    """
    if not _access_events_enabled:
        return

    event: dict[str, Any] = {
        "event_type": "data_access",
        "method": method.upper(),
        "endpoint": _sanitize_endpoint(endpoint),
        "status": status,
    }
    if error:
        event["error"] = error

    _emit(event)


def log_code_execution(
    code_hash: str,
    sandbox_mode: str,
    status: str,
    duration_sec: float | None = None,
    error: str | None = None,
) -> None:
    """Log a code execution audit event.

    Args:
        code_hash: SHA-256 hash prefix of the executed code (not the raw code)
        sandbox_mode: Sandbox mode used (disabled, local, container)
        status: "success", "error", or "timeout"
        duration_sec: Execution duration in seconds
        error: Optional error message
    """
    if not _execution_events_enabled:
        return

    event: dict[str, Any] = {
        "event_type": "code_execution",
        "code_hash": code_hash,
        "sandbox_mode": sandbox_mode,
        "status": status,
    }
    if duration_sec is not None:
        event["duration_sec"] = round(duration_sec, 3)
    if error:
        event["error"] = error

    _emit(event)


def reset_audit_state() -> None:
    """Reset audit module state. For testing only."""
    global _access_events_enabled, _execution_events_enabled, _initialized
    _access_events_enabled = False
    _execution_events_enabled = False
    _initialized = False
    _audit_logger.handlers.clear()
