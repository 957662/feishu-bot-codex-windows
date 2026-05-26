"""Unit tests for the daemon server."""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

from feishu_bot_codex.daemon.server import serve
from feishu_bot_codex.proto import Request


@pytest.fixture
def socket_path(tmp_path):
    # AF_UNIX path limit on macOS is 104 chars; use a short tempdir path
    import uuid
    short = Path(tempfile.gettempdir()) / f"t{uuid.uuid4().hex[:8]}.sock"
    yield short
    if short.exists():
        short.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_server_responds_to_ping(socket_path, tmp_path):
    """A client connecting and sending a ping request gets a ResultEvent + DoneEvent."""
    bindings_path = tmp_path / "bindings.toml"
    server = await serve(socket_path=socket_path, bindings_path=bindings_path)

    try:
        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        req = Request(op="ping", args={}, request_id="t1")
        writer.write((req.to_json_line() + "\n").encode())
        await writer.drain()

        lines = []
        while True:
            line = await reader.readline()
            if not line:
                break
            lines.append(line.decode().rstrip("\n"))

        writer.close()
        await writer.wait_closed()

        events = [json.loads(line) for line in lines]
        assert events[0]["type"] == "result"
        assert events[0]["ok"] is True
        assert events[0]["data"]["pong"] is True
        assert events[-1]["type"] == "done"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_server_responds_to_unknown_op(socket_path, tmp_path):
    bindings_path = tmp_path / "bindings.toml"
    server = await serve(socket_path=socket_path, bindings_path=bindings_path)
    try:
        reader, writer = await asyncio.open_unix_connection(str(socket_path))
        req = Request(op="totally-unknown", args={}, request_id="t2")
        writer.write((req.to_json_line() + "\n").encode())
        await writer.drain()

        lines = []
        while True:
            line = await reader.readline()
            if not line:
                break
            lines.append(line.decode().rstrip("\n"))

        writer.close()
        await writer.wait_closed()

        events = [json.loads(line) for line in lines]
        assert events[0]["type"] == "result"
        assert events[0]["ok"] is False
        # Either "unknown op" (from validate()) or "no handler" (from dispatcher)
        assert "unknown" in events[0]["error"].lower() or "no handler" in events[0]["error"].lower()
        assert events[-1]["type"] == "done"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_server_socket_has_0600_perms(socket_path, tmp_path):
    """The socket file must be 0600 so other users can't connect."""
    bindings_path = tmp_path / "bindings.toml"
    server = await serve(socket_path=socket_path, bindings_path=bindings_path)
    try:
        mode = socket_path.stat().st_mode & 0o777
        assert mode == 0o600, f"expected 0600, got {oct(mode)}"
    finally:
        server.close()
        await server.wait_closed()
