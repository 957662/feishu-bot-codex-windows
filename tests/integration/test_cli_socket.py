"""Integration test for CLI socket client against a real daemon."""

import asyncio
import tempfile
import uuid
from pathlib import Path

import pytest

from feishu_bot_codex.cli import run_op
from feishu_bot_codex.daemon import serve
from feishu_bot_codex.proto import DoneEvent, ResultEvent


@pytest.fixture
async def running_daemon(tmp_path):
    # Use short /tmp path to stay under macOS AF_UNIX 104-char limit
    socket_path = Path(tempfile.gettempdir()) / f"fbc-{uuid.uuid4().hex[:8]}.sock"
    bindings_path = tmp_path / "bindings.toml"
    server = await serve(socket_path=socket_path, bindings_path=bindings_path)
    yield socket_path
    server.close()
    await server.wait_closed()
    socket_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_run_op_ping_returns_pong(running_daemon):
    """CLI client connects to daemon, sends ping, receives pong."""
    events = []
    async for ev in run_op(socket_path=running_daemon, op="ping", args={}):
        events.append(ev)
    assert len(events) == 2
    assert isinstance(events[0], ResultEvent)
    assert events[0].ok is True
    assert events[0].data == {"pong": True}
    assert isinstance(events[1], DoneEvent)


@pytest.mark.asyncio
async def test_run_op_status_returns_version(running_daemon):
    events = []
    async for ev in run_op(socket_path=running_daemon, op="status", args={}):
        events.append(ev)
    assert events[0].ok is True
    assert "version" in events[0].data
