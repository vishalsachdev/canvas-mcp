"""Resource bounds on the routes an unauthenticated caller can reach.

Two paths in the ASGI middleware do work before, or regardless of, a successful
authorization:

- ``/admin/access/confirm`` is intercepted ahead of every token gate, so its
  request body is read from an unauthenticated caller. It carries one short
  signed token and nothing else.
- The Entra denial branch returns 403 immediately and *then* schedules an admin
  notification. Because the 403 comes first, a denied identity can repeat the
  request as fast as it likes, and the email cooldown that would suppress the
  work lives inside the scheduled task, after an Azure client and an asyncio
  task have already been created.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from canvas_mcp import server


class TestBodyReader:
    """_read_body must abandon an oversized stream instead of buffering it."""

    def _receive(self, chunks):
        queue = list(chunks)

        async def receive():
            body = queue.pop(0)
            return {"type": "http.request", "body": body, "more_body": bool(queue)}

        return receive

    @pytest.mark.asyncio
    async def test_reads_a_small_body(self):
        body = await server._read_body(
            self._receive([b"token=abc"]), max_bytes=server._MAX_PUBLIC_BODY_BYTES
        )
        assert body == b"token=abc"

    @pytest.mark.asyncio
    async def test_refuses_an_oversized_body(self):
        body = await server._read_body(self._receive([b"x" * 10_000]), max_bytes=8192)
        assert body is None

    @pytest.mark.asyncio
    async def test_refuses_an_oversized_chunked_body(self):
        """A body split into many small chunks must not slip past the cap."""
        chunks = [b"x" * 1000] * 20
        body = await server._read_body(self._receive(chunks), max_bytes=8192)
        assert body is None

    @pytest.mark.asyncio
    async def test_stops_before_consuming_the_whole_stream(self):
        """The cap must trip mid-stream, not after assembling everything."""
        delivered = 0

        async def receive():
            nonlocal delivered
            delivered += 1
            return {"type": "http.request", "body": b"x" * 1000, "more_body": True}

        body = await server._read_body(receive, max_bytes=8192)
        assert body is None
        # Nine 1000-byte chunks exceed 8192; an unbounded reader would loop forever.
        assert delivered <= 10

    @pytest.mark.asyncio
    async def test_unbounded_read_is_still_available_for_internal_callers(self):
        body = await server._read_body(self._receive([b"a", b"b"]))
        assert body == b"ab"


class TestContentLengthGate:
    def test_parses_declared_length(self):
        assert server._declared_content_length([(b"content-length", b"123")]) == 123

    def test_case_insensitive(self):
        assert server._declared_content_length([(b"Content-Length", b"7")]) == 7

    def test_absent_or_unparseable(self):
        assert server._declared_content_length([]) is None
        assert server._declared_content_length([(b"content-length", b"abc")]) is None


class TestNotifyAdmission:
    """The denial path must not do per-request work for a repeating caller."""

    def setup_method(self):
        server.reset_notify_state()

    def teardown_method(self):
        server.reset_notify_state()

    def test_repeat_denials_are_admitted_once(self):
        now = 1_000_000.0
        admitted = [server._notify_admitted("oid-1", now + i) for i in range(50)]
        assert admitted[0] is True
        assert not any(admitted[1:]), "only the first denial should do work"

    def test_distinct_identities_are_independent(self):
        now = 1_000_000.0
        assert server._notify_admitted("oid-1", now) is True
        assert server._notify_admitted("oid-2", now) is True

    def test_admission_resumes_after_the_interval(self):
        now = 1_000_000.0
        assert server._notify_admitted("oid-1", now) is True
        later = now + server._NOTIFY_MIN_INTERVAL_SECONDS + 1
        assert server._notify_admitted("oid-1", later) is True

    def test_inflight_cap_blocks_further_work(self):
        server._notify_inflight.update(range(server._NOTIFY_MAX_INFLIGHT))
        assert server._notify_admitted("brand-new-oid", 1_000_000.0) is False

    def test_tracking_table_is_bounded(self):
        """The table is keyed by attacker-supplied identities, so it must not grow forever."""
        now = 1_000_000.0
        for i in range(server._NOTIFY_MAX_TRACKED_OIDS + 200):
            server._notify_admitted(f"oid-{i}", now + i)

        assert len(server._notify_last_scheduled) <= server._NOTIFY_MAX_TRACKED_OIDS

    def test_repeated_denials_do_not_build_a_client_each_time(self):
        """The property that matters: attacker-controlled repeats cost ~nothing.

        Building an Azure credential and client is the expensive part of the
        denial path. A flood of denied requests from one identity must not
        translate into a flood of client constructions.
        """
        config = MagicMock()
        requester = MagicMock(oid="oid-flood")

        with patch(
            "canvas_mcp.core.access.factory.build_email_sender", return_value=None
        ) as build:
            for _ in range(200):
                server._schedule_notify(config, MagicMock(), requester)

        assert build.call_count == 1, (
            f"200 denied requests caused {build.call_count} client builds"
        )

    def test_a_built_sender_is_reused_across_intervals(self):
        """A real sender is memoized, so later admitted denials reuse it."""
        config = MagicMock()

        with patch(
            "canvas_mcp.core.access.factory.build_email_sender",
            return_value=MagicMock(),
        ) as build, patch(
            "canvas_mcp.core.access.notify.notify_access_request",
            new_callable=MagicMock,  # not an AsyncMock: create_task is stubbed out
        ), patch("asyncio.create_task"):
            for i in range(5):
                server._schedule_notify(
                    config, MagicMock(), MagicMock(oid=f"oid-{i}")
                )

        assert build.call_count == 1

    @pytest.mark.asyncio
    async def test_scheduled_task_is_tracked_and_released(self):
        config = MagicMock()
        config.access_token_secret = "s"
        config.access_approve_base_url = "https://example.test"
        config.access_admin_emails = ["a@example.test"]
        config.access_notify_cooldown_hours = 1
        requester = MagicMock(oid="oid-track")

        async def fake_notify(**kwargs):
            await asyncio.sleep(0)

        with patch(
            "canvas_mcp.core.access.factory.build_email_sender",
            return_value=MagicMock(),
        ), patch("canvas_mcp.core.access.notify.notify_access_request", fake_notify):
            server._schedule_notify(config, MagicMock(), requester)
            assert len(server._notify_inflight) == 1
            await asyncio.sleep(0.01)

        assert len(server._notify_inflight) == 0, "completed task was not released"
