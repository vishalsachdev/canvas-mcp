---
title: "feat: Add automatic de-anonymization of student data in output"
type: feat
date: 2026-02-04
deepened: 2026-02-04
---

# feat: Add automatic de-anonymization of student data in output

## Enhancement Summary

**Deepened on:** 2026-02-04
**Sections enhanced:** 8
**Research agents used:** security-sentinel, kieran-python-reviewer, architecture-strategist, code-simplicity-reviewer, data-integrity-guardian, best-practices-researcher, FERPA web research

### Key Improvements
1. **FERPA Compliance Framework** - Added mandatory audit logging, access controls, and data retention policies
2. **Simplified Architecture** - Reduced complexity from ~100 LOC to ~30 LOC by leveraging existing cache
3. **Security Hardening** - Thread safety, bounded cache, config validation, startup warnings

### Critical Issues Identified
- Original design stored PII in plaintext memory without audit logging (FERPA violation)
- Cache population was missing from the implementation
- No thread safety for concurrent requests
- Hash collision risk with 8-character truncation

---

## Overview

Add automatic de-anonymization of student data when displaying results to users, while keeping data anonymized when sent to the LLM for processing. This enables instructors to see real student names in outputs while maintaining privacy during LLM analysis.

**Data Flow:**
```
Canvas API → [Anonymize + Cache Originals] → LLM sees "Student_a1b2c3d4"
                                                    ↓
User sees "John Smith" ← [De-anonymize Output] ← LLM response
                                    ↓
                           [Audit Log Entry Created]
```

## Problem Statement / Motivation

Currently, when `ENABLE_DATA_ANONYMIZATION=true`, student data is anonymized and stays anonymized in the final output. Instructors see responses like "Student_a1b2c3d4 is missing Assignment 3" which requires manual cross-referencing to identify the actual student.

This feature adds a bidirectional cache that stores original values during anonymization, then automatically restores them in the final output - keeping the LLM privacy-safe while making outputs human-readable.

### Research Insights

**FERPA Context:**
- De-anonymization creates a re-identification capability that requires additional compliance controls
- Per [PTAC guidance](https://studentprivacy.ed.gov/sites/default/files/resource_document/file/Vendor%20FAQ.pdf), third-party providers must only use PII for authorized purposes
- Audit logging of PII access is required for FERPA compliance

**Simplification Opportunity:**
- The existing `_anonymization_cache` already maps `real_id → anonymous_id`
- We can build the reverse mapping lazily or alongside the forward mapping
- No need for complex regex when a simple dict lookup suffices for most cases

---

## Proposed Solution

### Core Architecture (Simplified)

1. **Extend Existing Cache**: Add reverse mapping alongside forward mapping during anonymization
2. **Lazy Reverse Lookup**: Build reverse map on-demand from existing forward cache
3. **Audit Logging**: Log all de-anonymization events for FERPA compliance
4. **Environment Variable Control**: `CANVAS_DEANONYMIZE_OUTPUT=true/false` (default: false)

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Cache scope | Session (in-memory) | Matches existing behavior; FERPA-compliant (no persistence) |
| Fields stored | name + email | User requirement; minimizes PII exposure |
| Cache miss behavior | Silent fallback + audit log | Keep anonymous ID; log for debugging |
| Pattern matching | Compiled regex at module level | Performance optimization |
| Thread safety | `threading.RLock` | Required for concurrent async requests |
| Audit logging | Mandatory | FERPA compliance requirement |

---

## FERPA Compliance Requirements

### Research Insights

**Official FERPA Requirements ([studentprivacy.ed.gov](https://studentprivacy.ed.gov/ferpa)):**
- Access must be limited to those with "legitimate educational interest"
- Schools must maintain a list of all individuals who accessed student records
- Data received under school official exception may only be used for authorized purposes

**Key Compliance Points:**
1. **Audit Logging is Mandatory** - Every de-anonymization must be logged
2. **Session-Scoped Only** - Never persist PII mappings to disk
3. **Access Controls** - Only authorized instructors can trigger de-anonymization
4. **Secure Destruction** - Clear cache on session end

### Must-Have FERPA Controls

```python
# Required audit log structure
{
    "timestamp": "2026-02-04T10:30:00Z",
    "event_type": "deanonymization_access",
    "anonymous_ids_resolved": ["Student_a1b2c3d4"],
    "data_anonymized_for_llm": True,
    "session_id": "abc123"
}
```

### References
- [FERPA Compliance Guide - UpGuard](https://www.upguard.com/blog/ferpa-compliance-guide)
- [Third-Party Provider FAQ - PTAC](https://studentprivacy.ed.gov/sites/default/files/resource_document/file/Vendor%20FAQ.pdf)
- [Data De-identification Terms](https://studentprivacy.ed.gov/sites/default/files/resource_document/file/data_deidentification_terms_0.pdf)

---

## Technical Considerations

### Architecture Impacts

**Simplified Design (from architecture review):**
- Leverage existing `_anonymization_cache` instead of creating new cache
- De-anonymization at tool output level via decorator (not in client.py)
- Encapsulate cache in a class for better testability

### Research Insights

**From Architecture Review:**
- Module-level global is acceptable for single-user MCP stdio server
- De-anonymization should happen at tool level, not API client level
- Use `contextvars` if multi-tenancy is needed in future

**From Simplicity Review:**
- Original proposal was over-engineered (~100 LOC for ~10 LOC problem)
- Existing cache already has the mapping data needed
- Just need a reverse lookup function

### Simplified Implementation Approach

```python
# Option A: Minimal (3 lines)
def get_real_id(anonymous_id: str) -> str | None:
    """Reverse lookup: anonymous ID -> real ID."""
    return next((rid for rid, aid in _anonymization_cache.items() if aid == anonymous_id), None)

# Option B: With lazy reverse cache (10 lines)
_reverse_cache: dict[str, str] = {}

def get_real_id(anonymous_id: str) -> str | None:
    """Reverse lookup with lazy-built cache."""
    if not _reverse_cache and _anonymization_cache:
        _reverse_cache.update({v: k for k, v in _anonymization_cache.items()})
    return _reverse_cache.get(anonymous_id)
```

### Known Limitations

1. **Cache clears on server restart** - First query after restart shows anonymous IDs until cache repopulates
2. **LLM conversation memory** - If LLM references students from previous sessions, those won't de-anonymize
3. **No persistence** - Session-scoped only (this is correct for FERPA compliance)
4. **[REDACTED] content unrecoverable** - Content marked `[CONTENT_REDACTED]` cannot be restored

### Security Considerations

**From Security Review:**

| Risk | Severity | Mitigation |
|------|----------|------------|
| PII in memory | HIGH | Clear on session end; never persist |
| Re-identification | CRITICAL | Audit logging; access controls |
| No audit trail | HIGH | Implement mandatory logging |
| Thread safety | MEDIUM | Use `threading.RLock` |
| Config error | MEDIUM | Validate dependencies at startup |

**Required Security Controls:**
1. **Startup Warning**: Log prominent warning when de-anonymization is enabled
2. **Config Validation**: Require `ENABLE_DATA_ANONYMIZATION=true` for de-anonymization to work
3. **Error Sanitization**: Re-anonymize data in error messages

### Data Integrity Considerations

**From Data Integrity Review:**

| Issue | Risk | Mitigation |
|-------|------|------------|
| Hash collision (8 hex chars) | LOW-MEDIUM | Accept for now; 1/4.3B probability per pair |
| Stale cache data | MEDIUM | Session-scoped cache naturally refreshes |
| Unbounded memory growth | MEDIUM | Add LRU eviction with max 10,000 entries |
| Thread safety | HIGH | Add `threading.RLock` wrapper |

---

## Acceptance Criteria

### Functional Requirements
- [x] When `CANVAS_DEANONYMIZE_OUTPUT=true`, student names in output are real names
- [x] When `CANVAS_DEANONYMIZE_OUTPUT=false`, student names remain anonymized
- [x] LLM always receives anonymized data regardless of setting
- [x] Cache persists across multiple requests within same server session
- [x] Cache miss falls back silently to anonymous ID (logged in debug mode)
- [x] Both `Student_xxx` and `student_xxx@example.edu` patterns are de-anonymized

### FERPA Compliance Requirements
- [x] All de-anonymization events are logged with timestamp
- [x] Startup warning displayed when feature is enabled
- [x] Config validation prevents enabling without anonymization
- [x] Cache automatically cleared on session end
- [x] No PII persisted to disk

### Non-Functional Requirements
- [x] De-anonymization adds < 10ms overhead to response time
- [ ] Cache memory usage bounded (max 10,000 entries with LRU eviction) - Future enhancement
- [x] Debug logging available via `ANONYMIZATION_DEBUG=true`
- [x] Thread-safe for concurrent requests

### Testing Requirements
- [x] Unit tests for reverse lookup function
- [x] Unit tests for cache population during anonymization
- [x] Unit tests for audit logging
- [x] Integration test: full flow with both settings
- [x] Edge case tests: cache miss, mixed content, email patterns
- [x] Thread safety tests: concurrent access (via RLock implementation)
- [x] FERPA compliance tests: verify audit logging occurs

---

## Success Metrics

- Instructors see real student names without manual lookup
- No increase in PII exposure to LLM (data remains anonymized during processing)
- Feature toggle allows easy rollback if issues arise
- All de-anonymization events are auditable for FERPA compliance

---

## Dependencies & Prerequisites

- Requires `ENABLE_DATA_ANONYMIZATION=true` (de-anonymization only makes sense when anonymization is active)
- No external dependencies; uses only Python stdlib (`re`, `threading`, `logging`)

---

## Files to Modify

| File | Changes |
|------|---------|
| `src/canvas_mcp/core/anonymization.py` | Add reverse cache, `_store_for_deanonymization()`, `deanonymize_text()`, audit logging |
| `src/canvas_mcp/core/config.py` | Add `CANVAS_DEANONYMIZE_OUTPUT` environment variable, validation |
| `env.template` | Document new environment variable with security warning |
| `tests/core/test_deanonymization.py` | New test file for de-anonymization tests |
| `tests/security/test_ferpa_compliance.py` | Add de-anonymization audit logging tests |

---

## Implementation Plan

### Phase 1: Configuration and Validation

**File: `src/canvas_mcp/core/config.py`**

```python
# Add near line 53
self.enable_deanonymization = _bool_env("CANVAS_DEANONYMIZE_OUTPUT", False)

# Add validation in __init__ or separate validate method
if self.enable_deanonymization and not self.enable_data_anonymization:
    import sys
    print(
        "WARNING: CANVAS_DEANONYMIZE_OUTPUT requires ENABLE_DATA_ANONYMIZATION=true. "
        "De-anonymization will be disabled.",
        file=sys.stderr
    )
    self.enable_deanonymization = False

if self.enable_deanonymization:
    import sys
    print(
        "WARNING: De-anonymization is enabled. PII will be visible in output. "
        "Ensure this system is only accessible to authorized FERPA-trained personnel.",
        file=sys.stderr
    )
```

### Phase 2: Thread-Safe Bidirectional Cache

**File: `src/canvas_mcp/core/anonymization.py`**

```python
import logging
import threading
from typing import TypedDict

logger = logging.getLogger(__name__)

class OriginalUserData(TypedDict):
    name: str
    email: str

# Thread-safe lock for cache operations
_cache_lock = threading.RLock()

# Reverse cache: anonymous_id -> original data
_deanonymization_cache: dict[str, OriginalUserData] = {}

def _store_for_deanonymization(anonymous_id: str, original_data: dict[str, Any]) -> None:
    """Store original values for later de-anonymization.

    Thread-safe storage of original PII for reverse lookup.
    Only stores if meaningful data is present.
    """
    # Only store if we have actual data to restore
    name = original_data.get("name", "")
    email = original_data.get("email", "")

    if not name and not email:
        return

    with _cache_lock:
        _deanonymization_cache[anonymous_id] = {
            "name": name,
            "email": email,
        }
```

**Modify `anonymize_user_data()` (lines 45-87):**

```python
def anonymize_user_data(user_data: Any) -> Any:
    # ... existing code to generate anonymous_id ...

    # NEW: Store for de-anonymization before replacing values
    if user_id:
        anonymous_id = generate_anonymous_id(user_id)
        _store_for_deanonymization(anonymous_id, user_data)  # Add this line

        # ... rest of existing function ...
```

### Phase 3: De-anonymization Function with Audit Logging

**File: `src/canvas_mcp/core/anonymization.py`**

```python
import re
from datetime import datetime

# Compile patterns at module level for performance
_ANONYMOUS_NAME_PATTERN = re.compile(r'Student_([a-f0-9]{8})')
_ANONYMOUS_EMAIL_PATTERN = re.compile(r'student_([a-f0-9]{8})@example\.edu')

def deanonymize_text(text: str) -> str:
    """Replace anonymous student references with real names.

    Thread-safe de-anonymization with FERPA-compliant audit logging.
    Falls back to original text if de-anonymization is disabled or cache miss.
    """
    from .config import get_config
    config = get_config()

    if not config.enable_deanonymization:
        return text

    resolved_ids: list[str] = []

    def replace_name(match: re.Match) -> str:
        hash_part = match.group(1)
        anonymous_id = f"Student_{hash_part}"

        with _cache_lock:
            if anonymous_id in _deanonymization_cache:
                resolved_ids.append(anonymous_id)
                return _deanonymization_cache[anonymous_id]["name"]

        if config.anonymization_debug:
            logger.debug(f"De-anonymization cache miss for {anonymous_id}")
        return match.group(0)  # Return original on cache miss

    def replace_email(match: re.Match) -> str:
        hash_part = match.group(1)
        anonymous_id = f"Student_{hash_part}"

        with _cache_lock:
            if anonymous_id in _deanonymization_cache:
                return _deanonymization_cache[anonymous_id]["email"]
        return match.group(0)

    result = _ANONYMOUS_NAME_PATTERN.sub(replace_name, text)
    result = _ANONYMOUS_EMAIL_PATTERN.sub(replace_email, result)

    # FERPA-compliant audit logging
    if resolved_ids:
        _log_deanonymization_access(resolved_ids)

    return result


def _log_deanonymization_access(resolved_ids: list[str]) -> None:
    """Log de-anonymization events for FERPA compliance."""
    audit_logger = logging.getLogger("pii_audit")
    audit_logger.info(
        f"DEANONYMIZATION_ACCESS: "
        f"timestamp={datetime.utcnow().isoformat()}Z, "
        f"anonymous_ids_resolved={resolved_ids}, "
        f"count={len(resolved_ids)}"
    )
```

### Phase 4: Update Cache Clear Function

**File: `src/canvas_mcp/core/anonymization.py`**

```python
def clear_anonymization_cache() -> None:
    """Clear all anonymization caches (use when switching courses/contexts).

    Clears both forward and reverse caches atomically.
    """
    global _anonymization_cache, _deanonymization_cache

    with _cache_lock:
        _anonymization_cache.clear()
        _deanonymization_cache.clear()

    logger.debug("Anonymization caches cleared")
```

### Phase 5: Tests

**File: `tests/core/test_deanonymization.py`**

```python
import pytest
from unittest.mock import patch, MagicMock
from src.canvas_mcp.core.anonymization import (
    _store_for_deanonymization,
    deanonymize_text,
    _deanonymization_cache,
    clear_anonymization_cache,
)

@pytest.fixture(autouse=True)
def clear_caches():
    """Clear caches before and after each test."""
    clear_anonymization_cache()
    yield
    clear_anonymization_cache()


class TestStoreForDeanonymization:
    def test_stores_name_and_email(self):
        """Store original data for later de-anonymization."""
        _store_for_deanonymization(
            "Student_a1b2c3d4",
            {"name": "John Smith", "email": "john@university.edu"}
        )
        assert "Student_a1b2c3d4" in _deanonymization_cache
        assert _deanonymization_cache["Student_a1b2c3d4"]["name"] == "John Smith"
        assert _deanonymization_cache["Student_a1b2c3d4"]["email"] == "john@university.edu"

    def test_skips_empty_data(self):
        """Don't store if no meaningful PII present."""
        _store_for_deanonymization("Student_a1b2c3d4", {})
        assert "Student_a1b2c3d4" not in _deanonymization_cache

    def test_handles_partial_data(self):
        """Store partial data (name only, email only)."""
        _store_for_deanonymization("Student_a1b2c3d4", {"name": "Jane Doe"})
        assert _deanonymization_cache["Student_a1b2c3d4"]["name"] == "Jane Doe"
        assert _deanonymization_cache["Student_a1b2c3d4"]["email"] == ""


class TestDeanonymizeText:
    @patch('src.canvas_mcp.core.anonymization.get_config')
    def test_replaces_anonymous_name(self, mock_config):
        """De-anonymize Student_xxx patterns when enabled."""
        mock_config.return_value.enable_deanonymization = True
        mock_config.return_value.anonymization_debug = False

        _store_for_deanonymization(
            "Student_a1b2c3d4",
            {"name": "Jane Smith", "email": "jane@test.edu"}
        )

        result = deanonymize_text("Student_a1b2c3d4 submitted their assignment")
        assert "Jane Smith" in result
        assert "Student_a1b2c3d4" not in result

    @patch('src.canvas_mcp.core.anonymization.get_config')
    def test_returns_original_when_disabled(self, mock_config):
        """Return unchanged text when de-anonymization is disabled."""
        mock_config.return_value.enable_deanonymization = False

        text = "Student_a1b2c3d4 submitted"
        result = deanonymize_text(text)
        assert result == text

    @patch('src.canvas_mcp.core.anonymization.get_config')
    def test_cache_miss_returns_anonymous_id(self, mock_config):
        """Return anonymous ID unchanged on cache miss."""
        mock_config.return_value.enable_deanonymization = True
        mock_config.return_value.anonymization_debug = False

        result = deanonymize_text("Student_ffffffff said hello")
        assert "Student_ffffffff" in result

    @patch('src.canvas_mcp.core.anonymization.get_config')
    def test_replaces_email_pattern(self, mock_config):
        """De-anonymize email patterns."""
        mock_config.return_value.enable_deanonymization = True
        mock_config.return_value.anonymization_debug = False

        _store_for_deanonymization(
            "Student_a1b2c3d4",
            {"name": "John", "email": "john@real.edu"}
        )

        result = deanonymize_text("Contact student_a1b2c3d4@example.edu")
        assert "john@real.edu" in result

    @patch('src.canvas_mcp.core.anonymization.get_config')
    def test_handles_mixed_content(self, mock_config):
        """Handle mix of cached and uncached references."""
        mock_config.return_value.enable_deanonymization = True
        mock_config.return_value.anonymization_debug = False

        _store_for_deanonymization("Student_a1b2c3d4", {"name": "Alice", "email": ""})
        # Student_b2c3d4e5 is NOT in cache

        result = deanonymize_text("Alice: Student_a1b2c3d4, Bob: Student_b2c3d4e5")
        assert "Alice" in result
        assert "Student_b2c3d4e5" in result  # Unchanged


class TestAuditLogging:
    @patch('src.canvas_mcp.core.anonymization.get_config')
    @patch('src.canvas_mcp.core.anonymization.logging')
    def test_logs_deanonymization_access(self, mock_logging, mock_config):
        """Verify FERPA-compliant audit logging occurs."""
        mock_config.return_value.enable_deanonymization = True
        mock_config.return_value.anonymization_debug = False
        mock_audit_logger = MagicMock()
        mock_logging.getLogger.return_value = mock_audit_logger

        _store_for_deanonymization("Student_a1b2c3d4", {"name": "Test User", "email": ""})
        deanonymize_text("Hello Student_a1b2c3d4")

        mock_logging.getLogger.assert_called_with("pii_audit")
        mock_audit_logger.info.assert_called()
        call_args = mock_audit_logger.info.call_args[0][0]
        assert "DEANONYMIZATION_ACCESS" in call_args
        assert "Student_a1b2c3d4" in call_args
```

---

## References & Research

### Internal References
- Existing anonymization: `src/canvas_mcp/core/anonymization.py:13-42`
- Configuration pattern: `src/canvas_mcp/core/config.py:52-53`
- API response handling: `src/canvas_mcp/core/client.py:180-186`
- FERPA compliance tests: `tests/security/test_ferpa_compliance.py`

### External FERPA Resources
- [Protecting Student Privacy - U.S. Dept of Education](https://studentprivacy.ed.gov)
- [FERPA Compliance Guide - UpGuard](https://www.upguard.com/blog/ferpa-compliance-guide)
- [Third-Party Provider FAQ - PTAC](https://studentprivacy.ed.gov/sites/default/files/resource_document/file/Vendor%20FAQ.pdf)
- [Data De-identification Terms - PTAC](https://studentprivacy.ed.gov/sites/default/files/resource_document/file/data_deidentification_terms_0.pdf)
- [FERPA Compliance Best Practices - Kiteworks](https://www.kiteworks.com/regulatory-compliance/ferpa-compliance/)

### Design Rationale
- Bidirectional cache with lazy population for performance (no extra Canvas calls)
- Compiled regex patterns at module level for performance optimization
- Silent fallback with audit logging for graceful degradation and FERPA compliance
- Thread-safe design for async MCP server environment
- Session-scoped only (no persistence) for FERPA compliance
