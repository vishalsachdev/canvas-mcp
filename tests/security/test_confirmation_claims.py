"""Owning claims cannot release another attempt or an uncertain write."""
import asyncio
import json
from unittest.mock import patch

import httpx
import pytest
from fastmcp import FastMCP

from canvas_mcp.core import client as cm
from canvas_mcp.core.write_confirmation import ConfirmationGuard
from canvas_mcp.core.write_outcome import RequestFailure, WriteOutcome
from canvas_mcp.tools import messaging


def test_stale_foreign_and_legacy_handles_cannot_release_owner():
    guard = ConfirmationGuard()
    token = guard.issue('A')
    first = guard.claim(token, 'A')
    assert not isinstance(first, str)
    assert first.finish(WriteOutcome.REJECTED)
    second = guard.claim(token, 'A')
    assert not isinstance(second, str)
    assert not first.finish(WriteOutcome.NOT_DISPATCHED)
    guard.release(token)
    assert isinstance(guard.claim(token, 'A'), str)
    other = ConfirmationGuard()
    assert not other._finish_claim(second, WriteOutcome.REJECTED)
    assert second.finish(WriteOutcome.NOT_DISPATCHED)
    assert not isinstance(guard.claim(token, 'A'), str)


def test_uncertain_outcome_consumes_claim_and_burn_is_terminal():
    for outcome in (WriteOutcome.MAY_HAVE_WRITTEN, WriteOutcome.REJECTED):
        guard = ConfirmationGuard()
        token = guard.issue('A')
        claim = guard.claim(token, 'A')
        assert not isinstance(claim, str)
        if outcome == WriteOutcome.REJECTED:
            assert 'does not match' in guard.claim(token, 'B')
        assert not claim.finish(outcome)
        assert not claim.finish(WriteOutcome.NOT_DISPATCHED)
        guard.release(token)  # legacy release cannot erase an owning claim
        assert isinstance(guard.claim(token, 'A'), str)


@pytest.mark.asyncio
async def test_concurrent_claims_have_one_owner():
    guard = ConfirmationGuard()
    token = guard.issue('A')
    async def attempt():
        await asyncio.sleep(0)
        return guard.claim(token, 'A')
    claims = await asyncio.gather(*(attempt() for _ in range(100)))
    assert sum(not isinstance(claim, str) for claim in claims) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('status,retryable', [(400, True), (401, True), (403, True),
    (404, True), (422, True), (408, False), (409, False), (500, False)])
async def test_send_uses_transport_outcome_and_preserves_wire_error(status, retryable, monkeypatch):
    monkeypatch.setenv("CANVAS_API_URL", "https://canvas.example/api/v1")
    monkeypatch.setenv("CANVAS_API_TOKEN", "synthetic")
    calls = []
    def transport(request):
        calls.append(request)
        assert request.method == 'POST'
        assert request.url.path == '/api/v1/conversations'
        assert 'application/x-www-form-urlencoded' in request.headers['content-type']
        return httpx.Response(status, json={'error': 'rejected'})
    with patch.object(messaging, '_SEND_CONVERSATION_GUARD', ConfirmationGuard()):
        mcp = FastMCP('claims')
        messaging.register_educator_messaging_tools(mcp)
        tool = (await mcp.get_tool('send_conversation')).fn
        args = ('123', ['101', '102'], 'Hi', 'Body')
        preview = await tool(*args)
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
            with patch.object(cm, '_get_http_client', return_value=client):
                first = await tool(*args, confirmation_token=preview['confirmation_token'])
                assert json.loads(json.dumps(first)) == {'error': f"HTTP error: {status}, Details: {{'error': 'rejected'}}"}
                second = await tool(*args, confirmation_token=preview['confirmation_token'])
        assert len(calls) == (2 if retryable else 1)
        if not retryable:
            assert 'already used' in second['error']


@pytest.mark.asyncio
async def test_untyped_error_text_cannot_release_confirmation():
    with patch.object(messaging, '_SEND_CONVERSATION_GUARD', ConfirmationGuard()):
        mcp = FastMCP('claims')
        messaging.register_educator_messaging_tools(mcp)
        tool = (await mcp.get_tool('send_conversation')).fn
        args = ('123', ['101', '102'], 'Hi', 'Body')
        preview = await tool(*args)
        with patch.object(messaging, '_post_conversation', return_value={'error': 'HTTP error: 400'}) as post:
            await tool(*args, confirmation_token=preview['confirmation_token'])
            replay = await tool(*args, confirmation_token=preview['confirmation_token'])
        assert 'already used' in replay['error']
        assert post.call_count == 1


@pytest.mark.asyncio
async def test_local_endpoint_rejection_is_structured_without_dispatch():
    with patch.object(cm, '_get_http_client') as client:
        result = await cm.make_canvas_request('post', '/conversations?bad', data={})
    assert isinstance(result, RequestFailure)
    assert result.outcome == WriteOutcome.NOT_DISPATCHED
    client.assert_not_called()
