"""Executable counterexamples and refinement checks for verify/lean and verify/tla.

No Canvas writes: the guard is real; the messaging transport is a controlled
rejection. Tests deliberately control clock samples and coroutine scheduling.
"""

import asyncio
from unittest.mock import patch

import pytest

from canvas_mcp.core.write_confirmation import ConfirmationGuard, redeem_confirmation


def test_expiry_crossing_during_reserve_cannot_redeem_twice():
    guard = ConfirmationGuard(ttl_seconds=1)
    with patch("canvas_mcp.core.write_confirmation.time.time", return_value=100):
        token = guard.issue("A")
        assert guard.reserve(token)
    # Original: authenticate at 101, purge at 102, reserve again => True.
    with patch("canvas_mcp.core.write_confirmation.time.time", side_effect=[101, 102]):
        assert guard.reserve(token) is False


def test_clock_rollback_cannot_resurrect_purged_token():
    guard = ConfirmationGuard(ttl_seconds=1)
    with patch("canvas_mcp.core.write_confirmation.time.time", return_value=100):
        token = guard.issue("A")
        assert redeem_confirmation(guard, token, "A") is None
    with patch("canvas_mcp.core.write_confirmation.time.time", return_value=102):
        guard._purge()
    with patch("canvas_mcp.core.write_confirmation.time.time", return_value=100):
        assert redeem_confirmation(guard, token, "A") is not None


def test_clock_rollback_does_not_freeze_token_lifetime():
    with (
        patch("canvas_mcp.core.write_confirmation.time.time") as wall,
        patch("canvas_mcp.core.write_confirmation.time.monotonic") as monotonic,
    ):
        wall.return_value, monotonic.return_value = 1000, 0
        guard = ConfirmationGuard(ttl_seconds=1)
        guard.issue("old")
        wall.return_value, monotonic.return_value = 100, 1
        token = guard.issue("new")
        wall.return_value, monotonic.return_value = 102, 3
        assert redeem_confirmation(guard, token, "new") is not None


@pytest.mark.asyncio
async def test_mismatch_during_inflight_send_survives_rejection_release():
    from fastmcp import FastMCP

    from canvas_mcp.tools import messaging

    entered, finish = asyncio.Event(), asyncio.Event()
    writes = []

    async def rejected_transport(*args, **kwargs):
        writes.append((args, kwargs))
        entered.set()
        await finish.wait()
        return {"error": "HTTP error: 400, Details: rejected"}

    with (
        patch.object(messaging, "_SEND_CONVERSATION_GUARD", ConfirmationGuard()),
        patch.object(messaging, "_post_conversation", rejected_transport),
    ):
        mcp = FastMCP("confirmation-replay")
        messaging.register_educator_messaging_tools(mcp)
        registered = await mcp.get_tool("send_conversation")
        assert registered is not None
        tool = registered.fn
        args = ("123", ["101", "102"], "Hi", "Body")
        preview = await tool(*args)
        token = preview["confirmation_token"]
        first = asyncio.create_task(tool(*args, confirmation_token=token))
        await asyncio.wait_for(entered.wait(), timeout=5)
        try:
            mismatch = await tool("123", ["101", "102"], "CHANGED", "Body",
                                  confirmation_token=token)
            assert "does not match" in mismatch["error"]
            assert len(writes) == 1  # mismatching caller never reaches transport
        finally:
            finish.set()
            first_result = await first
        assert "HTTP error: 400" in first_result["error"]
        replay = await tool(*args, confirmation_token=token)
        assert "already used" in replay["error"]
        assert len(writes) == 1


def test_release_after_proven_no_write_is_intentionally_retryable():
    guard = ConfirmationGuard()
    token = guard.issue("A")
    assert redeem_confirmation(guard, token, "A") is None
    guard.release(token)
    assert redeem_confirmation(guard, token, "A") is None


@pytest.mark.asyncio
async def test_concurrent_confirm_has_one_winner():
    guard = ConfirmationGuard()
    token = guard.issue("A")
    start = asyncio.Event()

    async def confirm():
        await start.wait()
        return redeem_confirmation(guard, token, "A")

    tasks = [asyncio.create_task(confirm()) for _ in range(100)]
    start.set()
    results = await asyncio.gather(*tasks)
    assert results.count(None) == 1


def test_mismatch_does_not_authorize_and_blocks_revert():
    guard = ConfirmationGuard()
    token = guard.issue("A")
    assert redeem_confirmation(guard, token, "B") is not None
    assert redeem_confirmation(guard, token, "A") is not None


def test_expired_token_never_authorizes():
    guard = ConfirmationGuard(ttl_seconds=1)
    with patch("canvas_mcp.core.write_confirmation.time.time", return_value=100):
        token = guard.issue("A")
    with patch("canvas_mcp.core.write_confirmation.time.time", return_value=102):
        assert redeem_confirmation(guard, token, "A") is not None
