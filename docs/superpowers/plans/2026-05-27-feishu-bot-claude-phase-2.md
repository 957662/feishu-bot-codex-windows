# feishu-bot-claude — Phase 2: IPC Plumbing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the daemon process and CLI client communicating over a Unix socket. After Phase 2, `python -m feishu_bot_claude daemon` runs a server; `feishu-bot-claude ping/list` work end-to-end; `bind/start/stop` return clean "not yet implemented" responses ready for later phases to fill in.

**Architecture:** Asyncio Unix socket server (`daemon/server.py`) with one connection per request, request → handler dispatch (`daemon/dispatcher.py`), individual handler functions (`daemon/handlers.py`). CLI client (`cli.py`) opens the socket, writes one Request line, reads NDJSON response events, renders them to the terminal. Click for CLI argument parsing.

**Tech Stack:** Python 3.11+, asyncio, click ≥ 8.1, all foundation from Phase 1.

**Companion spec:** `docs/superpowers/specs/2026-05-26-feishu-bot-claude-design.md`

**Prerequisite:** Phase 1 complete (git tag `phase-1-complete`).

**Scope (Phase 2 deliverables):**
- `feishu_bot_claude/daemon/__init__.py`
- `feishu_bot_claude/daemon/server.py` — asyncio Unix socket server
- `feishu_bot_claude/daemon/dispatcher.py` — op → handler routing
- `feishu_bot_claude/daemon/handlers.py` — `ping`, `list`, stub `bind`/`start`/`stop`/`unbind`/`config`/`status`/`shell`
- `feishu_bot_claude/cli.py` — Click commands + socket client + event renderer
- `feishu_bot_claude/__main__.py` — module entry (`python -m feishu_bot_claude daemon`)
- Integration tests spawning a real daemon

**Out of scope (later phases):**
- Real `bind` OAuth (Phase 7)
- Real `start`/`stop` doing mirror work (Phase 5-6)
- Real tmux or lark-cli calls (Phase 3)

---

## File Structure (Phase 2)

| Path | Responsibility |
|---|---|
| `feishu_bot_claude/__main__.py` | `python -m feishu_bot_claude {daemon|<cli-op>}` entry |
| `feishu_bot_claude/daemon/__init__.py` | Re-export `serve()` |
| `feishu_bot_claude/daemon/server.py` | `asyncio.start_unix_server` lifecycle + connection handler |
| `feishu_bot_claude/daemon/dispatcher.py` | `Dispatcher` class — register/lookup handlers by op name |
| `feishu_bot_claude/daemon/handlers.py` | Async handler functions (one per op) |
| `feishu_bot_claude/cli.py` | Click group, op subcommands, socket client, event rendering |
| `tests/integration/test_daemon_cli.py` | End-to-end spawn-daemon tests |
| `tests/unit/test_dispatcher.py` | Dispatcher unit tests |
| `tests/unit/test_handlers.py` | Handler unit tests (with mock BindingStore) |
| `tests/unit/test_cli_renderer.py` | CLI event-renderer unit tests |

**Default socket path:** `~/.feishu-bot-claude/control.sock` — configurable via `FEISHU_BOT_CLAUDE_SOCKET` env var for tests.

---

## Phase 2 Tasks

### Task 2.1: Dispatcher — register and lookup handlers

**Files:**
- Create: `feishu_bot_claude/daemon/__init__.py` (empty re-export stub)
- Create: `feishu_bot_claude/daemon/dispatcher.py`
- Create: `tests/unit/test_dispatcher.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_dispatcher.py`:
```python
"""Tests for Dispatcher: register handlers, look them up by op name."""

import pytest

from feishu_bot_claude.daemon.dispatcher import Dispatcher


async def _example_handler(args):
    return {"got": args}


def test_register_then_lookup():
    d = Dispatcher()
    d.register("ping", _example_handler)
    assert d.lookup("ping") is _example_handler


def test_lookup_missing_raises():
    d = Dispatcher()
    with pytest.raises(KeyError, match="no handler for op 'unknown'"):
        d.lookup("unknown")


def test_register_duplicate_raises():
    d = Dispatcher()
    d.register("ping", _example_handler)
    with pytest.raises(ValueError, match="handler for 'ping' already registered"):
        d.register("ping", _example_handler)


def test_registered_ops_lists_all():
    d = Dispatcher()
    d.register("a", _example_handler)
    d.register("b", _example_handler)
    assert sorted(d.registered_ops()) == ["a", "b"]
```

- [ ] **Step 2: Run and verify it fails**

Run:
```bash
pytest tests/unit/test_dispatcher.py -xvs
```
Expected: `ModuleNotFoundError: No module named 'feishu_bot_claude.daemon'`

- [ ] **Step 3: Implement Dispatcher**

Create `feishu_bot_claude/daemon/__init__.py`:
```python
"""Daemon package — Unix socket server + handlers."""
```

Create `feishu_bot_claude/daemon/dispatcher.py`:
```python
"""Op-name → handler-function routing."""

from __future__ import annotations

from typing import Awaitable, Callable

HandlerFn = Callable[[dict], Awaitable[object]]


class Dispatcher:
    """Registry mapping op names to async handler callables."""

    def __init__(self) -> None:
        self._handlers: dict[str, HandlerFn] = {}

    def register(self, op: str, handler: HandlerFn) -> None:
        if op in self._handlers:
            raise ValueError(f"handler for {op!r} already registered")
        self._handlers[op] = handler

    def lookup(self, op: str) -> HandlerFn:
        try:
            return self._handlers[op]
        except KeyError:
            raise KeyError(f"no handler for op {op!r}") from None

    def registered_ops(self) -> list[str]:
        return list(self._handlers.keys())
```

- [ ] **Step 4: Verify tests pass**

Run:
```bash
pytest tests/unit/test_dispatcher.py -xvs
```
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/ tests/unit/test_dispatcher.py
git commit -m "feat(daemon): add Dispatcher for op-to-handler routing"
```

---

### Task 2.2: handlers.py — `ping` handler

**Files:**
- Create: `feishu_bot_claude/daemon/handlers.py`
- Create: `tests/unit/test_handlers.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_handlers.py`:
```python
"""Tests for daemon handlers (with mocked BindingStore)."""

import pytest

from feishu_bot_claude.daemon.handlers import handle_ping
from feishu_bot_claude.proto import DoneEvent, ResultEvent


@pytest.mark.asyncio
async def test_ping_emits_result_then_done():
    """ping yields a ResultEvent(ok=True, data={pong: True}) then DoneEvent."""
    events = []
    async for ev in handle_ping(args={}):
        events.append(ev)
    assert events == [
        ResultEvent(ok=True, data={"pong": True}, error=None),
        DoneEvent(),
    ]
```

- [ ] **Step 2: Run and verify failure**

```bash
pytest tests/unit/test_handlers.py -xvs
```
Expected: `ImportError: cannot import name 'handle_ping'`

- [ ] **Step 3: Implement `handle_ping`**

Create `feishu_bot_claude/daemon/handlers.py`:
```python
"""Daemon op handlers — async generators yielding ResponseEvents."""

from __future__ import annotations

from typing import AsyncIterator

from feishu_bot_claude.proto import DoneEvent, ResponseEvent, ResultEvent


async def handle_ping(args: dict) -> AsyncIterator[ResponseEvent]:
    """Liveness check. Yields a single ok result and done."""
    yield ResultEvent(ok=True, data={"pong": True}, error=None)
    yield DoneEvent()
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_handlers.py -xvs
```
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/handlers.py tests/unit/test_handlers.py
git commit -m "feat(daemon): add ping handler"
```

---

### Task 2.3: handlers.py — `list` handler (BindingStore-backed)

**Files:**
- Modify: `feishu_bot_claude/daemon/handlers.py`
- Modify: `tests/unit/test_handlers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_handlers.py`:
```python
from datetime import datetime, timezone
from pathlib import Path

from feishu_bot_claude.config.binding import BindingConfig, BindingStore
from feishu_bot_claude.daemon.handlers import handle_list


def _example_config(name="foo-bot", project_dir="/abs/foo") -> BindingConfig:
    return BindingConfig(
        name=name,
        project_dir=project_dir,
        tmux_session=f"claude-{name}",
        feishu_app_id=f"cli_{name}",
        secret_ref=f"feishu-bot-claude.{name}.app_secret",
        created_at=datetime(2026, 5, 26, 18, 50, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_list_returns_all_bindings(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(_example_config(name="foo-bot", project_dir="/abs/foo"))
    store.add(_example_config(name="bar-bot", project_dir="/abs/bar"))

    events = []
    async for ev in handle_list(args={}, store=store):
        events.append(ev)

    assert len(events) == 2  # ResultEvent + DoneEvent
    result = events[0]
    assert result.ok is True
    assert {b["name"] for b in result.data["bindings"]} == {"foo-bot", "bar-bot"}
    assert events[-1] == DoneEvent()


@pytest.mark.asyncio
async def test_list_empty_store(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    events = []
    async for ev in handle_list(args={}, store=store):
        events.append(ev)
    assert events[0].data == {"bindings": []}
```

- [ ] **Step 2: Run, verify failure**

```bash
pytest tests/unit/test_handlers.py -xvs
```
Expected: `ImportError: cannot import name 'handle_list'`

- [ ] **Step 3: Implement `handle_list`**

Append to `feishu_bot_claude/daemon/handlers.py`:
```python
from feishu_bot_claude.config.binding import BindingStore


def _binding_summary(b) -> dict:
    return {
        "name": b.name,
        "project_dir": b.project_dir,
        "tmux_session": b.tmux_session,
        "feishu_app_id": b.feishu_app_id,
        "render_style": b.render_style,
    }


async def handle_list(args: dict, store: BindingStore) -> AsyncIterator[ResponseEvent]:
    """Return all bindings as a list of summary dicts."""
    bindings = [_binding_summary(b) for b in store.all()]
    yield ResultEvent(ok=True, data={"bindings": bindings}, error=None)
    yield DoneEvent()
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_handlers.py -xvs
```
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/handlers.py tests/unit/test_handlers.py
git commit -m "feat(daemon): add list handler returning binding summaries"
```

---

### Task 2.4: handlers.py — stub `bind`/`start`/`stop`/`unbind`/`config`/`status`/`shell`

**Files:**
- Modify: `feishu_bot_claude/daemon/handlers.py`
- Modify: `tests/unit/test_handlers.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_handlers.py`:
```python
from feishu_bot_claude.daemon.handlers import (
    handle_bind,
    handle_unbind,
    handle_start,
    handle_stop,
    handle_config,
    handle_status,
    handle_shell,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", [handle_bind, handle_unbind, handle_start, handle_stop, handle_config, handle_shell])
async def test_stub_handlers_return_not_implemented(handler):
    """Each stub handler returns ok=False with 'not yet implemented'."""
    events = []
    async for ev in handler(args={}):
        events.append(ev)
    assert events[0].ok is False
    assert "not yet implemented" in events[0].error.lower()
    assert events[-1] == DoneEvent()


@pytest.mark.asyncio
async def test_status_returns_daemon_info():
    """status returns ok=True with daemon version + uptime."""
    events = []
    async for ev in handle_status(args={}):
        events.append(ev)
    assert events[0].ok is True
    assert "version" in events[0].data
    assert events[-1] == DoneEvent()
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_handlers.py -xvs
```
Expected: `ImportError` on the new handler names.

- [ ] **Step 3: Implement the stub handlers**

Append to `feishu_bot_claude/daemon/handlers.py`:
```python
import time

import feishu_bot_claude

_DAEMON_START_TIME = time.time()


async def _not_implemented(op: str) -> AsyncIterator[ResponseEvent]:
    yield ResultEvent(ok=False, data=None, error=f"{op}: not yet implemented (later phase)")
    yield DoneEvent()


async def handle_bind(args: dict) -> AsyncIterator[ResponseEvent]:
    async for ev in _not_implemented("bind"):
        yield ev


async def handle_unbind(args: dict) -> AsyncIterator[ResponseEvent]:
    async for ev in _not_implemented("unbind"):
        yield ev


async def handle_start(args: dict) -> AsyncIterator[ResponseEvent]:
    async for ev in _not_implemented("start"):
        yield ev


async def handle_stop(args: dict) -> AsyncIterator[ResponseEvent]:
    async for ev in _not_implemented("stop"):
        yield ev


async def handle_config(args: dict) -> AsyncIterator[ResponseEvent]:
    async for ev in _not_implemented("config"):
        yield ev


async def handle_shell(args: dict) -> AsyncIterator[ResponseEvent]:
    async for ev in _not_implemented("shell"):
        yield ev


async def handle_status(args: dict) -> AsyncIterator[ResponseEvent]:
    yield ResultEvent(
        ok=True,
        data={
            "version": feishu_bot_claude.__version__,
            "uptime_seconds": int(time.time() - _DAEMON_START_TIME),
        },
        error=None,
    )
    yield DoneEvent()
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_handlers.py -xvs
```
Expected: `10 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/handlers.py tests/unit/test_handlers.py
git commit -m "feat(daemon): add stub handlers for bind/unbind/start/stop/config/shell + status"
```

---

### Task 2.5: server.py — accept connection + parse Request

**Files:**
- Create: `feishu_bot_claude/daemon/server.py`
- Modify: `feishu_bot_claude/daemon/__init__.py`
- Create: `tests/unit/test_server.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_server.py`:
```python
"""Unit tests for the daemon server."""

import asyncio
import json
import os
from pathlib import Path

import pytest

from feishu_bot_claude.daemon.server import serve
from feishu_bot_claude.proto import Request


@pytest.fixture
def socket_path(tmp_path):
    return tmp_path / "test.sock"


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
        # Should get result(ok=False, error mentions op) + done
        assert events[0]["type"] == "result"
        assert events[0]["ok"] is False
        assert "unknown op" in events[0]["error"]
        assert events[-1]["type"] == "done"
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_server_socket_has_0600_perms(socket_path, tmp_path):
    """The socket file must be 0600 so other users on the box can't connect."""
    bindings_path = tmp_path / "bindings.toml"
    server = await serve(socket_path=socket_path, bindings_path=bindings_path)
    try:
        mode = socket_path.stat().st_mode & 0o777
        assert mode == 0o600, f"expected 0600, got {oct(mode)}"
    finally:
        server.close()
        await server.wait_closed()
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_server.py -xvs
```
Expected: `ImportError: cannot import name 'serve'`

- [ ] **Step 3: Implement `serve()`**

Create `feishu_bot_claude/daemon/server.py`:
```python
"""Asyncio Unix-socket server. One Request → many ResponseEvents → DoneEvent → close."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from feishu_bot_claude.config.binding import BindingStore
from feishu_bot_claude.daemon.dispatcher import Dispatcher
from feishu_bot_claude.daemon.handlers import (
    handle_bind,
    handle_config,
    handle_list,
    handle_ping,
    handle_shell,
    handle_start,
    handle_status,
    handle_stop,
    handle_unbind,
)
from feishu_bot_claude.proto import DoneEvent, Request, ResultEvent

logger = logging.getLogger(__name__)


def _build_dispatcher(store: BindingStore) -> Dispatcher:
    d = Dispatcher()
    d.register("ping", handle_ping)
    d.register("status", handle_status)
    # list needs the store — bind it via closure
    async def _list_with_store(args):
        async for ev in handle_list(args, store=store):
            yield ev
    d.register("list", _list_with_store)
    d.register("bind", handle_bind)
    d.register("unbind", handle_unbind)
    d.register("start", handle_start)
    d.register("stop", handle_stop)
    d.register("config", handle_config)
    d.register("shell", handle_shell)
    return d


async def _handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    dispatcher: Dispatcher,
) -> None:
    try:
        line = await reader.readline()
        if not line:
            return
        try:
            req = Request.from_json_line(line.decode().rstrip("\n"))
            req.validate()
        except (json.JSONDecodeError, ValueError) as e:
            await _write_event(writer, ResultEvent(ok=False, data=None, error=f"bad request: {e}"))
            await _write_event(writer, DoneEvent())
            return

        try:
            handler = dispatcher.lookup(req.op)
        except KeyError as e:
            await _write_event(writer, ResultEvent(ok=False, data=None, error=str(e)))
            await _write_event(writer, DoneEvent())
            return

        async for event in handler(req.args):
            await _write_event(writer, event)
    except Exception as e:  # noqa: BLE001
        logger.exception("client handler crashed")
        try:
            await _write_event(writer, ResultEvent(ok=False, data=None, error=f"server crash: {e}"))
            await _write_event(writer, DoneEvent())
        except Exception:
            pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def _write_event(writer: asyncio.StreamWriter, event) -> None:
    writer.write((event.to_json_line() + "\n").encode())
    await writer.drain()


async def serve(socket_path: Path, bindings_path: Path) -> asyncio.AbstractServer:
    """Start the daemon server bound to a Unix socket. Returns the running server."""
    socket_path = Path(socket_path)
    if socket_path.exists():
        socket_path.unlink()
    socket_path.parent.mkdir(parents=True, exist_ok=True)

    store = BindingStore(bindings_path)
    dispatcher = _build_dispatcher(store)

    async def _on_client(reader, writer):
        await _handle_client(reader, writer, dispatcher)

    server = await asyncio.start_unix_server(_on_client, path=str(socket_path))
    os.chmod(socket_path, 0o600)
    logger.info("daemon listening on %s", socket_path)
    return server
```

Update `feishu_bot_claude/daemon/__init__.py`:
```python
"""Daemon package — Unix socket server + handlers."""

from feishu_bot_claude.daemon.server import serve

__all__ = ["serve"]
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_server.py -xvs
```
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/server.py feishu_bot_claude/daemon/__init__.py tests/unit/test_server.py
git commit -m "feat(daemon): add Unix socket server with request dispatch"
```

---

### Task 2.6: cli.py — event renderer (pure function)

**Files:**
- Create: `feishu_bot_claude/cli.py`
- Create: `tests/unit/test_cli_renderer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_cli_renderer.py`:
```python
"""Tests for CLI event renderer (pure, no I/O)."""

from feishu_bot_claude.cli import render_event
from feishu_bot_claude.proto import (
    DoneEvent,
    LogEvent,
    ProgressEvent,
    QRCodeEvent,
    ResultEvent,
)


def test_render_log_returns_plain_message():
    out = render_event(LogEvent(level="info", msg="hello"))
    assert out == "hello"


def test_render_log_error_includes_marker():
    out = render_event(LogEvent(level="error", msg="bad thing"))
    assert "error" in out.lower() or "ERROR" in out
    assert "bad thing" in out


def test_render_qrcode_includes_ascii_and_url():
    out = render_event(QRCodeEvent(ascii="█▀█\n▀ █", url="https://x/qr"))
    assert "█▀█" in out
    assert "https://x/qr" in out


def test_render_progress_percent():
    out = render_event(ProgressEvent(value=0.42, msg="working"))
    assert "42%" in out
    assert "working" in out


def test_render_result_ok_with_data():
    out = render_event(ResultEvent(ok=True, data={"x": 1}, error=None))
    assert "ok" in out.lower() or "success" in out.lower() or "✓" in out or "OK" in out


def test_render_result_failure_includes_error():
    out = render_event(ResultEvent(ok=False, data=None, error="boom"))
    assert "boom" in out


def test_render_done_returns_empty_string():
    out = render_event(DoneEvent())
    assert out == ""
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_cli_renderer.py -xvs
```
Expected: `ImportError: cannot import name 'render_event' from 'feishu_bot_claude.cli'`

- [ ] **Step 3: Implement `render_event`**

Create `feishu_bot_claude/cli.py`:
```python
"""CLI entry: socket client + Click commands + terminal rendering."""

from __future__ import annotations

import json
from feishu_bot_claude.proto import (
    DoneEvent,
    LogEvent,
    ProgressEvent,
    QRCodeEvent,
    ResponseEvent,
    ResultEvent,
)


def render_event(event: ResponseEvent) -> str:
    """Format one ResponseEvent into a single terminal-ready string.

    Returns "" for DoneEvent (caller does nothing with it).
    """
    if isinstance(event, LogEvent):
        if event.level == "error":
            return f"ERROR: {event.msg}"
        if event.level == "warn":
            return f"WARN: {event.msg}"
        return event.msg
    if isinstance(event, QRCodeEvent):
        return f"{event.ascii}\n\nURL: {event.url}"
    if isinstance(event, ProgressEvent):
        pct = int(event.value * 100)
        return f"[{pct}%] {event.msg}"
    if isinstance(event, ResultEvent):
        if event.ok:
            payload = json.dumps(event.data, ensure_ascii=False, indent=2) if event.data else ""
            return f"OK\n{payload}" if payload else "OK"
        return f"FAILED: {event.error}"
    if isinstance(event, DoneEvent):
        return ""
    return repr(event)
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_cli_renderer.py -xvs
```
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/cli.py tests/unit/test_cli_renderer.py
git commit -m "feat(cli): add render_event for terminal output formatting"
```

---

### Task 2.7: cli.py — socket client (`run_op`)

**Files:**
- Modify: `feishu_bot_claude/cli.py`
- Create: `tests/integration/test_cli_socket.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_cli_socket.py`:
```python
"""Integration test for CLI socket client against a real daemon."""

import asyncio
import os
from pathlib import Path

import pytest

from feishu_bot_claude.cli import run_op
from feishu_bot_claude.daemon import serve
from feishu_bot_claude.proto import DoneEvent, ResultEvent


@pytest.fixture
async def running_daemon(tmp_path):
    socket_path = tmp_path / "ipc.sock"
    bindings_path = tmp_path / "bindings.toml"
    server = await serve(socket_path=socket_path, bindings_path=bindings_path)
    yield socket_path
    server.close()
    await server.wait_closed()


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
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/integration/test_cli_socket.py -xvs
```
Expected: `ImportError: cannot import name 'run_op'`

- [ ] **Step 3: Implement `run_op`**

Append to `feishu_bot_claude/cli.py`:
```python
import asyncio
from pathlib import Path
from typing import AsyncIterator

from feishu_bot_claude.proto import Request, parse_response_line


async def run_op(
    socket_path: Path,
    op: str,
    args: dict,
    request_id: str = "",
) -> AsyncIterator[ResponseEvent]:
    """Open the daemon socket, send one Request, yield ResponseEvents until done.

    Yields events as they stream in (real-time UI feedback).
    Raises ConnectionRefusedError if the daemon is not running.
    """
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    try:
        req = Request(op=op, args=args, request_id=request_id)
        writer.write((req.to_json_line() + "\n").encode())
        await writer.drain()

        while True:
            line = await reader.readline()
            if not line:
                break
            event = parse_response_line(line.decode().rstrip("\n"))
            yield event
            if isinstance(event, DoneEvent):
                break
    finally:
        writer.close()
        await writer.wait_closed()
```

- [ ] **Step 4: Verify**

```bash
pytest tests/integration/test_cli_socket.py -xvs
```
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/cli.py tests/integration/test_cli_socket.py
git commit -m "feat(cli): add run_op socket client for streaming response events"
```

---

### Task 2.8: cli.py — Click subcommands

**Files:**
- Modify: `pyproject.toml` (add `click` dep + console-script entry)
- Modify: `feishu_bot_claude/cli.py`

- [ ] **Step 1: Add click to dependencies**

Edit `pyproject.toml` — under `[project] dependencies`, add `"click >= 8.1.0"`:
```toml
dependencies = [
    "tomli-w >= 1.0.0",
    "click >= 8.1.0",
]
```

Under `[project]`, add a console-scripts entry:
```toml
[project.scripts]
feishu-bot-claude = "feishu_bot_claude.cli:main"
```

Reinstall:
```bash
pip install -e ".[dev]"
```

- [ ] **Step 2: Write the failing test**

Append to `tests/unit/test_cli_renderer.py`:
```python
from click.testing import CliRunner


def test_main_help_lists_subcommands():
    from feishu_bot_claude.cli import main
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for cmd in ["ping", "list", "bind", "start", "stop", "status", "unbind", "config"]:
        assert cmd in result.output, f"missing subcommand: {cmd}"
```

- [ ] **Step 3: Verify failure**

```bash
pytest tests/unit/test_cli_renderer.py::test_main_help_lists_subcommands -xvs
```
Expected: `ImportError` or "no such option --help" — `main` doesn't exist yet.

- [ ] **Step 4: Implement Click skeleton**

Append to `feishu_bot_claude/cli.py`:
```python
import os
import sys

import click

DEFAULT_SOCKET = Path(os.environ.get(
    "FEISHU_BOT_CLAUDE_SOCKET",
    Path.home() / ".feishu-bot-claude" / "control.sock",
))


def _print_events_sync(socket_path: Path, op: str, args: dict) -> int:
    """Run an op, print rendered events, return exit code (0 on ok, 1 on failure)."""
    final_ok = True

    async def _drive():
        nonlocal final_ok
        try:
            async for event in run_op(socket_path=socket_path, op=op, args=args):
                rendered = render_event(event)
                if rendered:
                    click.echo(rendered)
                if isinstance(event, ResultEvent) and not event.ok:
                    final_ok = False
        except ConnectionRefusedError:
            click.echo(f"ERROR: daemon not running at {socket_path}", err=True)
            return 2
        return 0 if final_ok else 1

    return asyncio.run(_drive())


@click.group(help="feishu-bot-claude — Feishu bridge for Claude Code")
@click.option("--socket", "socket_path", type=click.Path(path_type=Path), default=DEFAULT_SOCKET, show_default=True)
@click.pass_context
def main(ctx, socket_path):
    ctx.ensure_object(dict)
    ctx.obj["socket"] = socket_path


@main.command(help="Liveness check against the daemon")
@click.pass_context
def ping(ctx):
    sys.exit(_print_events_sync(ctx.obj["socket"], "ping", {}))


@main.command(name="list", help="List all bindings")
@click.pass_context
def list_cmd(ctx):
    sys.exit(_print_events_sync(ctx.obj["socket"], "list", {}))


@main.command(help="Show daemon status")
@click.pass_context
def status(ctx):
    sys.exit(_print_events_sync(ctx.obj["socket"], "status", {}))


@main.command(help="Bind current project to a new Feishu bot (Phase 7)")
@click.argument("name")
@click.option("--cwd", required=True, type=click.Path(path_type=Path))
@click.pass_context
def bind(ctx, name, cwd):
    sys.exit(_print_events_sync(ctx.obj["socket"], "bind", {"name": name, "cwd": str(cwd)}))


@main.command(help="Remove a binding")
@click.argument("name")
@click.pass_context
def unbind(ctx, name):
    sys.exit(_print_events_sync(ctx.obj["socket"], "unbind", {"name": name}))


@main.command(help="Start mirror for current project (Phase 5)")
@click.option("--cwd", required=True, type=click.Path(path_type=Path))
@click.pass_context
def start(ctx, cwd):
    sys.exit(_print_events_sync(ctx.obj["socket"], "start", {"cwd": str(cwd)}))


@main.command(help="Stop mirror for current project")
@click.option("--cwd", required=True, type=click.Path(path_type=Path))
@click.pass_context
def stop(ctx, cwd):
    sys.exit(_print_events_sync(ctx.obj["socket"], "stop", {"cwd": str(cwd)}))


@main.command(help="Adjust binding parameters")
@click.option("--cwd", required=True, type=click.Path(path_type=Path))
@click.argument("kv", nargs=-1)
@click.pass_context
def config(ctx, cwd, kv):
    sys.exit(_print_events_sync(ctx.obj["socket"], "config", {"cwd": str(cwd), "kv": list(kv)}))


@main.command(help="Start tmux + claude shell for current project (Phase 6)")
@click.option("--cwd", default=None, type=click.Path(path_type=Path))
@click.pass_context
def shell(ctx, cwd):
    sys.exit(_print_events_sync(ctx.obj["socket"], "shell", {"cwd": str(cwd) if cwd else os.getcwd()}))
```

- [ ] **Step 5: Verify**

```bash
pytest tests/unit/test_cli_renderer.py::test_main_help_lists_subcommands -xvs
```
Expected: `1 passed`. Also run the full suite:
```bash
pytest -xvs
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml feishu_bot_claude/cli.py tests/unit/test_cli_renderer.py
git commit -m "feat(cli): add Click subcommands for all 8 ops"
```

---

### Task 2.9: __main__.py — daemon entry

**Files:**
- Create: `feishu_bot_claude/__main__.py`
- Create: `tests/integration/test_daemon_entry.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_daemon_entry.py`:
```python
"""End-to-end: spawn daemon subprocess, run CLI against it, verify ping succeeds."""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_daemon_subprocess_responds_to_cli(tmp_path):
    socket_path = tmp_path / "ipc.sock"
    bindings_path = tmp_path / "bindings.toml"

    env = os.environ.copy()
    env["FEISHU_BOT_CLAUDE_SOCKET"] = str(socket_path)
    env["FEISHU_BOT_CLAUDE_BINDINGS"] = str(bindings_path)

    daemon = subprocess.Popen(
        [sys.executable, "-m", "feishu_bot_claude", "daemon"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        # Wait up to 3s for the socket to appear
        deadline = time.time() + 3
        while time.time() < deadline:
            if socket_path.exists():
                break
            await asyncio.sleep(0.05)
        assert socket_path.exists(), "daemon failed to create socket within 3s"

        # Run the CLI ping
        result = subprocess.run(
            [sys.executable, "-m", "feishu_bot_claude", "--socket", str(socket_path), "ping"],
            capture_output=True,
            text=True,
            env=env,
            timeout=5,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
        assert "pong" in result.stdout.lower() or "OK" in result.stdout
    finally:
        daemon.terminate()
        try:
            daemon.wait(timeout=2)
        except subprocess.TimeoutExpired:
            daemon.kill()
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/integration/test_daemon_entry.py -xvs
```
Expected: failure — `python -m feishu_bot_claude daemon` doesn't work yet.

- [ ] **Step 3: Implement `__main__.py`**

Create `feishu_bot_claude/__main__.py`:
```python
"""Module entry: `python -m feishu_bot_claude {daemon|<cli-op>}`.

When invoked with `daemon` it starts the server. Otherwise it delegates to
the Click CLI (so `python -m feishu_bot_claude ping` works just like
`feishu-bot-claude ping`).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from feishu_bot_claude.daemon import serve

_DEFAULT_DATA_DIR = Path.home() / ".feishu-bot-claude"


async def _run_daemon() -> None:
    socket_path = Path(os.environ.get(
        "FEISHU_BOT_CLAUDE_SOCKET",
        _DEFAULT_DATA_DIR / "control.sock",
    ))
    bindings_path = Path(os.environ.get(
        "FEISHU_BOT_CLAUDE_BINDINGS",
        _DEFAULT_DATA_DIR / "bindings.toml",
    ))
    server = await serve(socket_path=socket_path, bindings_path=bindings_path)
    try:
        async with server:
            await server.serve_forever()
    except asyncio.CancelledError:
        pass


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "daemon":
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
        try:
            asyncio.run(_run_daemon())
        except KeyboardInterrupt:
            pass
        return 0
    # Delegate to Click CLI
    from feishu_bot_claude.cli import main as click_main
    click_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Verify**

```bash
pytest tests/integration/test_daemon_entry.py -xvs
```
Expected: `1 passed`. The daemon spawns, accepts a CLI ping, responds with pong.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/__main__.py tests/integration/test_daemon_entry.py
git commit -m "feat: add module entry for daemon and CLI"
```

---

### Task 2.10: End-to-end list test + Phase 2 wrap-up

**Files:**
- Modify: `tests/integration/test_daemon_entry.py`
- Create: `docs/phase-2-summary.md`

- [ ] **Step 1: Append the end-to-end list test**

Append to `tests/integration/test_daemon_entry.py`:
```python
@pytest.mark.asyncio
async def test_daemon_list_empty(tmp_path):
    """A fresh daemon with no bindings returns an empty list."""
    socket_path = tmp_path / "ipc.sock"
    bindings_path = tmp_path / "bindings.toml"

    env = os.environ.copy()
    env["FEISHU_BOT_CLAUDE_SOCKET"] = str(socket_path)
    env["FEISHU_BOT_CLAUDE_BINDINGS"] = str(bindings_path)

    daemon = subprocess.Popen(
        [sys.executable, "-m", "feishu_bot_claude", "daemon"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.time() + 3
        while time.time() < deadline and not socket_path.exists():
            await asyncio.sleep(0.05)
        assert socket_path.exists()

        result = subprocess.run(
            [sys.executable, "-m", "feishu_bot_claude", "--socket", str(socket_path), "list"],
            capture_output=True, text=True, env=env, timeout=5,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "bindings" in result.stdout
        # Should show an empty list
        assert "[]" in result.stdout or '"bindings": []' in result.stdout
    finally:
        daemon.terminate()
        try:
            daemon.wait(timeout=2)
        except subprocess.TimeoutExpired:
            daemon.kill()
```

- [ ] **Step 2: Run the full suite**

```bash
pytest --cov=feishu_bot_claude --cov-report=term-missing -v
```
Expected: all pass; coverage ≥90%.

- [ ] **Step 3: Write Phase 2 summary**

Create `docs/phase-2-summary.md`:
```markdown
# Phase 2 Summary

**Date completed:** <fill in>

## What's in place

- `daemon/dispatcher.py` — op-name → handler registry
- `daemon/handlers.py` — `ping`, `status`, `list` working; `bind`/`unbind`/`start`/`stop`/`config`/`shell` stubs return "not yet implemented"
- `daemon/server.py` — asyncio Unix socket server, 0600 perms, request validation, error handling
- `cli.py` — Click CLI with 8 subcommands, socket client `run_op`, terminal renderer `render_event`
- `__main__.py` — single entry point: `python -m feishu_bot_claude daemon` starts server, anything else routes through Click
- Integration tests spawning real daemon subprocess

## Verification commands

```bash
# Start daemon manually
python -m feishu_bot_claude daemon &

# In another shell
feishu-bot-claude ping       # → OK, {"pong": true}
feishu-bot-claude list       # → OK, {"bindings": []}
feishu-bot-claude status     # → OK, {version, uptime_seconds}
feishu-bot-claude bind foo --cwd ~/some-project   # → FAILED: not yet implemented
```

## What's intentionally missing

- Real `bind` OAuth (Phase 7)
- Real `start`/`stop` mirror logic (Phase 5)
- tmux + lark-cli integrations (Phase 3)
- Card rendering (Phase 4)
- `.claude/commands/*.md` (Phase 8)
- `setup.sh` and daemon auto-start (Phase 8)

## Next phase preview

Phase 3 — External Adapters: wrap tmux and lark-cli subprocesses behind clean
interfaces with both real implementations and fakes for tests.
```

- [ ] **Step 4: Commit + tag**

```bash
git add docs/phase-2-summary.md tests/integration/test_daemon_entry.py
git commit -m "docs: phase 2 summary"
git tag -a phase-2-complete -m "Phase 2: IPC plumbing complete"
```

---

## Phase 2 Done. Next: Phase 3 — External Adapters

After Phase 2 lands:
- `daemon/tmux.py` — wrap `tmux has-session/new-session/send-keys/kill-session`
- `daemon/feishu.py` — wrap `lark-cli` subprocesses (event consume + message send)
- Fake backends for both, enabling all later phases to be tested without external dependencies
