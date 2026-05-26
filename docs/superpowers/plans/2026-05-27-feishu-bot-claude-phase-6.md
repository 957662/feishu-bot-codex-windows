# feishu-bot-claude — Phase 6: Orchestrator + Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the pipelines into per-binding coroutine groups managed by an `Orchestrator`. After Phase 6, the daemon can actually start/stop a binding: `feishu-bot-claude start --cwd /x` spawns the inbound + outbound coroutines, watches jsonl changes live via `watchfiles`, and replays backlog on start. Still using `FakeLarkCli` end-to-end (real OAuth is Phase 7).

**Architecture:** `Orchestrator` owns a `Binding` instance per active binding. Each `Binding` holds: `BindingConfig` (immutable), `BindingRuntimeState` (mutable), `OutboundPipeline`, `InboundPipeline`, `Tmux`, `LarkCli`, and the asyncio Task handles for the running coroutines. On daemon startup, `Orchestrator.restore_from_disk()` reads bindings.toml and state.json and reconstructs running bindings. On clean shutdown, all coroutines are cancelled gracefully.

**Prerequisite:** Phase 5 complete.

**Scope (Phase 6 deliverables):**
- `feishu_bot_claude/daemon/orchestrator.py` — `Orchestrator`, `RunningBinding`
- `feishu_bot_claude/daemon/jsonl_watcher.py` — `JsonlWatcher` (watchfiles wrapper)
- Replace stub `bind`/`unbind`/`start`/`stop` handlers with real implementations that use the orchestrator (still mock OAuth for `bind`)
- `tests/unit/test_orchestrator.py`
- `tests/unit/test_jsonl_watcher.py`
- `tests/integration/test_lifecycle.py`

**Out of scope:**
- Real Feishu OAuth (Phase 7)
- Menu push (Phase 7)
- `.claude/commands/` and setup.sh (Phase 8)

---

## File Structure (Phase 6)

| Path | Responsibility |
|---|---|
| `feishu_bot_claude/daemon/jsonl_watcher.py` | `JsonlWatcher` — async generator yielding "new bytes available" signals |
| `feishu_bot_claude/daemon/orchestrator.py` | `Orchestrator`, `RunningBinding` — owns per-binding coroutine groups, lifecycle |
| `feishu_bot_claude/daemon/handlers.py` | (modify) real `bind`/`unbind`/`start`/`stop`/`config`/`shell` handlers using orchestrator |
| `feishu_bot_claude/daemon/server.py` | (modify) inject `Orchestrator` into handlers |

---

## Phase 6 Tasks

### Task 6.1: jsonl_watcher.py — async file-change generator

**Files:**
- Create: `feishu_bot_claude/daemon/jsonl_watcher.py`
- Create: `tests/unit/test_jsonl_watcher.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_jsonl_watcher.py`:
```python
"""Tests for JsonlWatcher — async file-change signal generator."""

import asyncio
import json
from pathlib import Path

import pytest

from feishu_bot_claude.daemon.jsonl_watcher import JsonlWatcher


@pytest.mark.asyncio
async def test_watcher_yields_on_file_grow(tmp_path):
    """Appending to a watched file should yield a change signal."""
    path = tmp_path / "session.jsonl"
    path.write_text("initial\n")

    watcher = JsonlWatcher(path)
    received: list[None] = []

    async def listen():
        async for _ in watcher.changes(stop_after=1):
            received.append(None)

    listen_task = asyncio.create_task(listen())
    await asyncio.sleep(0.1)  # let watcher initialize
    with path.open("a") as f:
        f.write("new line\n")
    await asyncio.wait_for(listen_task, timeout=3.0)
    assert len(received) >= 1


@pytest.mark.asyncio
async def test_watcher_handles_initial_missing_file(tmp_path):
    """If the file doesn't exist yet, watcher should wait for it to appear."""
    path = tmp_path / "later.jsonl"
    watcher = JsonlWatcher(path)
    received: list[None] = []

    async def listen():
        async for _ in watcher.changes(stop_after=1):
            received.append(None)

    listen_task = asyncio.create_task(listen())
    await asyncio.sleep(0.1)
    path.write_text("hello\n")
    await asyncio.wait_for(listen_task, timeout=3.0)
    assert len(received) >= 1


@pytest.mark.asyncio
async def test_watcher_cancellable(tmp_path):
    """Cancelling the listen task should not leak the watchfiles task."""
    path = tmp_path / "session.jsonl"
    path.write_text("")

    watcher = JsonlWatcher(path)
    received: list[None] = []

    async def listen():
        async for _ in watcher.changes(stop_after=0):
            received.append(None)

    task = asyncio.create_task(listen())
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_jsonl_watcher.py -xvs
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `JsonlWatcher`**

Create `feishu_bot_claude/daemon/jsonl_watcher.py`:
```python
"""Async wrapper around watchfiles that yields a signal when the target file grows."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import AsyncIterator

import watchfiles

logger = logging.getLogger(__name__)


class JsonlWatcher:
    """Yield a signal whenever the watched file grows or is created.

    Watches the *parent directory* of `path` so file creation is also detected.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    async def changes(self, stop_after: int = 0) -> AsyncIterator[None]:
        """Yield None each time the file changes. stop_after=N exits after N signals; 0 = unlimited."""
        emitted = 0
        # watchfiles watches the parent dir; we filter for our specific file
        async for changes in watchfiles.awatch(
            self._path.parent,
            recursive=False,
            stop_event=None,
        ):
            relevant = any(Path(p) == self._path for _, p in changes)
            if relevant:
                yield None
                emitted += 1
                if stop_after and emitted >= stop_after:
                    return
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_jsonl_watcher.py -xvs
```
Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/jsonl_watcher.py tests/unit/test_jsonl_watcher.py
git commit -m "feat(daemon): JsonlWatcher async file-change generator"
```

---

### Task 6.2: orchestrator.py — RunningBinding + Orchestrator

**Files:**
- Create: `feishu_bot_claude/daemon/orchestrator.py`
- Create: `tests/unit/test_orchestrator.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_orchestrator.py`:
```python
"""Tests for Orchestrator — per-binding coroutine group lifecycle."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from feishu_bot_claude.config.binding import BindingConfig, BindingStore
from feishu_bot_claude.daemon.feishu import FakeLarkCli
from feishu_bot_claude.daemon.orchestrator import Orchestrator
from feishu_bot_claude.daemon.tmux import FakeTmux


def _config(name="foo-bot", project_dir="/abs/foo") -> BindingConfig:
    return BindingConfig(
        name=name,
        project_dir=project_dir,
        tmux_session=f"claude-{name}",
        feishu_app_id=f"cli_{name}",
        secret_ref=f"feishu-bot-claude.{name}.app_secret",
        created_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
    )


@pytest.fixture
def orchestrator(tmp_path):
    tmux = FakeTmux()
    lark = FakeLarkCli()
    store = BindingStore(tmp_path / "bindings.toml")
    return Orchestrator(
        store=store,
        tmux_factory=lambda binding_name: tmux,
        lark_factory=lambda binding: lark,
        data_dir=tmp_path,
        # Public refs so tests can inspect
    ), tmux, lark, store


@pytest.mark.asyncio
async def test_start_binding_requires_existing_binding(orchestrator):
    orch, *_ = orchestrator
    with pytest.raises(KeyError, match="no binding for cwd"):
        await orch.start_binding(cwd="/abs/unknown")


@pytest.mark.asyncio
async def test_start_binding_requires_tmux_session(orchestrator, tmp_path):
    orch, tmux, lark, store = orchestrator
    cfg = _config(project_dir=str(tmp_path / "foo"))
    (tmp_path / "foo").mkdir()
    store.add(cfg)
    # tmux session NOT registered → orchestrator must reject
    with pytest.raises(RuntimeError, match="tmux session.*not running"):
        await orch.start_binding(cwd=str(tmp_path / "foo"))


@pytest.mark.asyncio
async def test_start_binding_happy_path(orchestrator, tmp_path):
    orch, tmux, lark, store = orchestrator
    project_dir = tmp_path / "foo"
    project_dir.mkdir()
    cfg = _config(project_dir=str(project_dir), name="foo-bot")
    store.add(cfg)
    tmux.set_session("claude-foo-bot", exists=True)

    # Stub: jsonl path that doesn't exist yet — backlog process is a no-op
    await orch.start_binding(cwd=str(project_dir), jsonl_path=tmp_path / "session.jsonl")
    try:
        running = orch.get_running("foo-bot")
        assert running is not None
        assert running.config.name == "foo-bot"
    finally:
        await orch.stop_binding(cwd=str(project_dir))


@pytest.mark.asyncio
async def test_start_already_running_rejects(orchestrator, tmp_path):
    orch, tmux, lark, store = orchestrator
    project_dir = tmp_path / "foo"
    project_dir.mkdir()
    cfg = _config(project_dir=str(project_dir), name="foo-bot")
    store.add(cfg)
    tmux.set_session("claude-foo-bot", exists=True)

    await orch.start_binding(cwd=str(project_dir), jsonl_path=tmp_path / "session.jsonl")
    try:
        with pytest.raises(RuntimeError, match="already running"):
            await orch.start_binding(cwd=str(project_dir), jsonl_path=tmp_path / "session.jsonl")
    finally:
        await orch.stop_binding(cwd=str(project_dir))


@pytest.mark.asyncio
async def test_stop_cancels_coroutines(orchestrator, tmp_path):
    orch, tmux, lark, store = orchestrator
    project_dir = tmp_path / "foo"
    project_dir.mkdir()
    cfg = _config(project_dir=str(project_dir), name="foo-bot")
    store.add(cfg)
    tmux.set_session("claude-foo-bot", exists=True)

    await orch.start_binding(cwd=str(project_dir), jsonl_path=tmp_path / "session.jsonl")
    await orch.stop_binding(cwd=str(project_dir))
    assert orch.get_running("foo-bot") is None


@pytest.mark.asyncio
async def test_list_running_returns_names(orchestrator, tmp_path):
    orch, tmux, lark, store = orchestrator
    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    store.add(_config(project_dir=str(a), name="bot-a"))
    store.add(_config(project_dir=str(b), name="bot-b"))
    tmux.set_session("claude-bot-a", exists=True)
    tmux.set_session("claude-bot-b", exists=True)

    await orch.start_binding(cwd=str(a), jsonl_path=tmp_path / "a.jsonl")
    try:
        running = orch.list_running()
        assert running == ["bot-a"]
        await orch.start_binding(cwd=str(b), jsonl_path=tmp_path / "b.jsonl")
        assert set(orch.list_running()) == {"bot-a", "bot-b"}
    finally:
        await orch.stop_binding(cwd=str(a))
        await orch.stop_binding(cwd=str(b))
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_orchestrator.py -xvs
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `Orchestrator`**

Create `feishu_bot_claude/daemon/orchestrator.py`:
```python
"""Per-binding coroutine group lifecycle."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from feishu_bot_claude.config.binding import BindingConfig, BindingStore
from feishu_bot_claude.daemon.feishu import LarkCli
from feishu_bot_claude.daemon.inbound import InboundPipeline
from feishu_bot_claude.daemon.outbound import OutboundPipeline
from feishu_bot_claude.daemon.ratelimit import TokenBucket
from feishu_bot_claude.daemon.state import BindingRuntimeState
from feishu_bot_claude.daemon.tmux import Tmux

logger = logging.getLogger(__name__)


@dataclass
class RunningBinding:
    """Live state of one binding that's actively mirroring."""

    config: BindingConfig
    state: BindingRuntimeState
    outbound: OutboundPipeline
    inbound: InboundPipeline
    tasks: list[asyncio.Task] = field(default_factory=list)


class Orchestrator:
    """Owns per-binding coroutine groups; lifecycle is start/stop per cwd."""

    def __init__(
        self,
        store: BindingStore,
        tmux_factory: Callable[[str], Tmux],
        lark_factory: Callable[[BindingConfig], LarkCli],
        data_dir: Path,
    ) -> None:
        self._store = store
        self._tmux_factory = tmux_factory
        self._lark_factory = lark_factory
        self._data_dir = Path(data_dir)
        self._running: dict[str, RunningBinding] = {}
        self._chat_id_for: dict[str, str] = {}  # name → chat_id (in real prod, comes from binding creation)

    def set_chat_id(self, binding_name: str, chat_id: str) -> None:
        """Test/wiring helper: tell the orchestrator which chat_id to send to."""
        self._chat_id_for[binding_name] = chat_id

    def get_running(self, name: str) -> RunningBinding | None:
        return self._running.get(name)

    def list_running(self) -> list[str]:
        return sorted(self._running.keys())

    async def start_binding(self, cwd: str, jsonl_path: Path | None = None) -> RunningBinding:
        cfg = self._store.find_by_cwd(cwd)
        if cfg is None:
            raise KeyError(f"no binding for cwd {cwd!r}")
        if cfg.name in self._running:
            raise RuntimeError(f"binding {cfg.name!r} is already running")

        tmux = self._tmux_factory(cfg.name)
        if not tmux.has_session(cfg.tmux_session):
            raise RuntimeError(
                f"tmux session {cfg.tmux_session!r} is not running — start Claude first"
            )

        lark = self._lark_factory(cfg)
        state_path = self._data_dir / f"state-{cfg.name}.json"
        state = BindingRuntimeState.load(cfg.name, state_path)

        bucket = TokenBucket(rate_per_sec=10, capacity=20)

        if jsonl_path is None:
            jsonl_path = self._guess_jsonl_path(cfg)

        chat_id = self._chat_id_for.get(cfg.name, "")
        outbound = OutboundPipeline(
            jsonl_path=jsonl_path,
            chat_id=chat_id,
            project_name=cfg.name,
            state=state,
            lark=lark,
            bucket=bucket,
            render_style=cfg.render_style,
        )
        inbound = InboundPipeline(
            tmux_session=cfg.tmux_session,
            tmux=tmux,
            lark=lark,
        )

        # Initial backlog process
        await outbound.process_backlog()

        running = RunningBinding(config=cfg, state=state, outbound=outbound, inbound=inbound)

        # Long-running tasks
        running.tasks.append(asyncio.create_task(
            self._outbound_loop(running, jsonl_path, state_path),
            name=f"outbound-{cfg.name}",
        ))
        running.tasks.append(asyncio.create_task(
            self._inbound_loop(running),
            name=f"inbound-{cfg.name}",
        ))
        self._running[cfg.name] = running
        return running

    async def stop_binding(self, cwd: str) -> None:
        cfg = self._store.find_by_cwd(cwd)
        if cfg is None:
            raise KeyError(f"no binding for cwd {cwd!r}")
        running = self._running.pop(cfg.name, None)
        if running is None:
            return
        for task in running.tasks:
            task.cancel()
        for task in running.tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def stop_all(self) -> None:
        for name in list(self._running.keys()):
            cfg = self._store.find_by_name(name)
            if cfg:
                await self.stop_binding(cwd=cfg.project_dir)

    def _guess_jsonl_path(self, cfg: BindingConfig) -> Path:
        """Find newest jsonl in ~/.claude/projects/<encoded-cwd>/ — mtime-based."""
        from pathlib import Path
        home = Path.home()
        encoded = cfg.project_dir.replace("/", "-").lstrip("-")
        projects_dir = home / ".claude" / "projects" / f"-{encoded}"
        if not projects_dir.exists():
            return projects_dir / "no-session.jsonl"  # nonexistent, pipeline tolerates it
        candidates = sorted(projects_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        return candidates[0] if candidates else projects_dir / "no-session.jsonl"

    async def _outbound_loop(self, running: RunningBinding, jsonl_path: Path, state_path: Path) -> None:
        """Watch jsonl, process new bytes on each change, persist state."""
        from feishu_bot_claude.daemon.jsonl_watcher import JsonlWatcher
        watcher = JsonlWatcher(jsonl_path)
        try:
            async for _ in watcher.changes():
                try:
                    await running.outbound.process_backlog()
                    running.state.save(state_path)
                except Exception:
                    logger.exception("outbound process failed for %s", running.config.name)
        except asyncio.CancelledError:
            running.state.save(state_path)
            raise

    async def _inbound_loop(self, running: RunningBinding) -> None:
        try:
            # Real: this never returns until the lark-cli subprocess ends.
            # Fake: it drains the queue and returns.
            await running.inbound.process_until_idle(max_events=0)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("inbound loop failed for %s", running.config.name)
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_orchestrator.py -xvs
```
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/orchestrator.py tests/unit/test_orchestrator.py
git commit -m "feat(daemon): Orchestrator per-binding lifecycle"
```

---

### Task 6.3: handlers.py — real start/stop/list using Orchestrator

**Files:**
- Modify: `feishu_bot_claude/daemon/handlers.py`
- Modify: `feishu_bot_claude/daemon/server.py`
- Modify: `tests/unit/test_handlers.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_handlers.py`:
```python
from feishu_bot_claude.daemon.handlers import handle_start_with_orchestrator, handle_stop_with_orchestrator
from feishu_bot_claude.daemon.orchestrator import Orchestrator
from feishu_bot_claude.daemon.tmux import FakeTmux
from feishu_bot_claude.daemon.feishu import FakeLarkCli


@pytest.fixture
def orch(tmp_path):
    tmux = FakeTmux()
    lark = FakeLarkCli()
    store = BindingStore(tmp_path / "bindings.toml")
    return Orchestrator(
        store=store,
        tmux_factory=lambda n: tmux,
        lark_factory=lambda c: lark,
        data_dir=tmp_path,
    ), tmux, lark, store, tmp_path


@pytest.mark.asyncio
async def test_handle_start_succeeds(orch, tmp_path):
    o, tmux, lark, store, td = orch
    project_dir = td / "p"; project_dir.mkdir()
    cfg = _example_config(name="bot-p", project_dir=str(project_dir))
    store.add(cfg)
    tmux.set_session("claude-bot-p", exists=True)

    events = []
    async for ev in handle_start_with_orchestrator(args={"cwd": str(project_dir)}, orchestrator=o):
        events.append(ev)
    assert events[0].ok is True
    assert "bot-p" in events[0].data.get("name", "")
    await o.stop_binding(cwd=str(project_dir))


@pytest.mark.asyncio
async def test_handle_start_unknown_cwd_fails(orch):
    o, *_ = orch
    events = []
    async for ev in handle_start_with_orchestrator(args={"cwd": "/abs/nowhere"}, orchestrator=o):
        events.append(ev)
    assert events[0].ok is False
    assert "no binding" in events[0].error.lower()
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_handlers.py -xvs
```
Expected: `ImportError`.

- [ ] **Step 3: Implement `handle_start_with_orchestrator` and `handle_stop_with_orchestrator`**

Append to `feishu_bot_claude/daemon/handlers.py`:
```python
from feishu_bot_claude.daemon.orchestrator import Orchestrator


async def handle_start_with_orchestrator(args: dict, orchestrator: Orchestrator) -> AsyncIterator[ResponseEvent]:
    cwd = args.get("cwd", "")
    try:
        running = await orchestrator.start_binding(cwd=cwd)
        yield ResultEvent(
            ok=True,
            data={"name": running.config.name, "tmux_session": running.config.tmux_session},
            error=None,
        )
    except KeyError as e:
        yield ResultEvent(ok=False, data=None, error=str(e))
    except RuntimeError as e:
        yield ResultEvent(ok=False, data=None, error=str(e))
    yield DoneEvent()


async def handle_stop_with_orchestrator(args: dict, orchestrator: Orchestrator) -> AsyncIterator[ResponseEvent]:
    cwd = args.get("cwd", "")
    try:
        await orchestrator.stop_binding(cwd=cwd)
        yield ResultEvent(ok=True, data={"stopped": True}, error=None)
    except KeyError as e:
        yield ResultEvent(ok=False, data=None, error=str(e))
    yield DoneEvent()
```

Update `feishu_bot_claude/daemon/server.py` — in `_build_dispatcher`, replace the stub `start`/`stop` registrations with closures that pass the orchestrator:

```python
def _build_dispatcher(store: BindingStore, orchestrator: "Orchestrator | None" = None) -> Dispatcher:
    d = Dispatcher()
    d.register("ping", handle_ping)
    d.register("status", handle_status)

    async def _list_with_store(args):
        async for ev in handle_list(args, store=store):
            yield ev
    d.register("list", _list_with_store)

    if orchestrator is not None:
        async def _start_with_orch(args):
            async for ev in handle_start_with_orchestrator(args, orchestrator=orchestrator):
                yield ev
        async def _stop_with_orch(args):
            async for ev in handle_stop_with_orchestrator(args, orchestrator=orchestrator):
                yield ev
        d.register("start", _start_with_orch)
        d.register("stop", _stop_with_orch)
    else:
        d.register("start", handle_start)
        d.register("stop", handle_stop)

    d.register("bind", handle_bind)
    d.register("unbind", handle_unbind)
    d.register("config", handle_config)
    d.register("shell", handle_shell)
    return d
```

Update `serve()` to optionally accept an orchestrator and pass it through.

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_handlers.py -xvs
pytest tests/unit/test_server.py -xvs   # existing should still pass
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/handlers.py feishu_bot_claude/daemon/server.py tests/unit/test_handlers.py
git commit -m "feat(daemon): real start/stop handlers wired to Orchestrator"
```

---

### Task 6.4: Daemon entry — instantiate Orchestrator at startup

**Files:**
- Modify: `feishu_bot_claude/__main__.py`
- Modify: `feishu_bot_claude/daemon/server.py`

- [ ] **Step 1: Update `_run_daemon` to build Orchestrator**

Edit `feishu_bot_claude/__main__.py`:
```python
async def _run_daemon() -> None:
    socket_path = Path(os.environ.get(
        "FEISHU_BOT_CLAUDE_SOCKET",
        _DEFAULT_DATA_DIR / "control.sock",
    ))
    bindings_path = Path(os.environ.get(
        "FEISHU_BOT_CLAUDE_BINDINGS",
        _DEFAULT_DATA_DIR / "bindings.toml",
    ))
    data_dir = Path(os.environ.get(
        "FEISHU_BOT_CLAUDE_DATA_DIR",
        _DEFAULT_DATA_DIR,
    ))

    from feishu_bot_claude.config.binding import BindingStore
    from feishu_bot_claude.daemon.orchestrator import Orchestrator
    from feishu_bot_claude.daemon.tmux import RealTmux
    from feishu_bot_claude.daemon.feishu import RealLarkCli

    store = BindingStore(bindings_path)
    orchestrator = Orchestrator(
        store=store,
        tmux_factory=lambda name: RealTmux(),
        lark_factory=lambda cfg: RealLarkCli(),  # Phase 7 will pass app_id/secret
        data_dir=data_dir,
    )

    server = await serve(
        socket_path=socket_path,
        bindings_path=bindings_path,
        orchestrator=orchestrator,
    )
    try:
        async with server:
            await server.serve_forever()
    except asyncio.CancelledError:
        pass
    finally:
        await orchestrator.stop_all()
```

And update `serve()` signature in `server.py`:
```python
async def serve(
    socket_path: Path,
    bindings_path: Path,
    orchestrator: "Orchestrator | None" = None,
) -> asyncio.AbstractServer:
    ...
    dispatcher = _build_dispatcher(store, orchestrator=orchestrator)
    ...
```

- [ ] **Step 2: Verify the existing integration tests still pass**

```bash
pytest tests/integration/ -xvs
```
Expected: all green (the integration tests don't depend on the orchestrator).

- [ ] **Step 3: Commit**

```bash
git add feishu_bot_claude/__main__.py feishu_bot_claude/daemon/server.py
git commit -m "feat(daemon): wire Orchestrator into daemon entry"
```

---

### Task 6.5: Phase 6 wrap-up + integration test

**Files:**
- Create: `tests/integration/test_lifecycle.py`
- Create: `docs/phase-6-summary.md`

- [ ] **Step 1: Add a full lifecycle integration test**

Create `tests/integration/test_lifecycle.py`:
```python
"""End-to-end lifecycle test with fake adapters."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from feishu_bot_claude.config.binding import BindingConfig, BindingStore
from feishu_bot_claude.daemon.feishu import FakeLarkCli
from feishu_bot_claude.daemon.orchestrator import Orchestrator
from feishu_bot_claude.daemon.tmux import FakeTmux


@pytest.mark.asyncio
async def test_full_lifecycle_with_fakes(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    jsonl = tmp_path / "session.jsonl"
    jsonl.write_text("")

    cfg = BindingConfig(
        name="myproject-bot",
        project_dir=str(project_dir),
        tmux_session="claude-myproject-bot",
        feishu_app_id="cli_x",
        secret_ref="x",
        created_at=datetime.now(timezone.utc),
    )
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(cfg)

    tmux = FakeTmux()
    tmux.set_session("claude-myproject-bot", exists=True)
    lark = FakeLarkCli()

    orchestrator = Orchestrator(
        store=store,
        tmux_factory=lambda n: tmux,
        lark_factory=lambda c: lark,
        data_dir=tmp_path,
    )

    # Start
    await orchestrator.start_binding(cwd=str(project_dir), jsonl_path=jsonl)
    assert "myproject-bot" in orchestrator.list_running()

    # Simulate Claude writing a turn to the jsonl
    events = [
        {"role": "user", "uuid": "u1", "content": [{"type": "text", "text": "hi"}]},
        {"role": "assistant", "uuid": "a1", "content": [{"type": "text", "text": "hello"}]},
    ]
    with jsonl.open("a") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # Give the outbound loop a moment to react to the file change
    await asyncio.sleep(0.5)

    # The mock LarkCli should have at least one send call
    assert any(c["kind"] == "card" for c in lark.send_calls)

    # Stop
    await orchestrator.stop_binding(cwd=str(project_dir))
    assert "myproject-bot" not in orchestrator.list_running()
```

- [ ] **Step 2: Run**

```bash
pytest tests/integration/test_lifecycle.py -xvs
```
Expected: `1 passed`.

- [ ] **Step 3: Write summary**

Create `docs/phase-6-summary.md`:
```markdown
# Phase 6 Summary

**Date completed:** <fill in>

## What's in place

- `daemon/jsonl_watcher.py` — async file-change generator via `watchfiles`
- `daemon/orchestrator.py` — `Orchestrator` + `RunningBinding` lifecycle:
  - `start_binding(cwd, jsonl_path=None)` spawns outbound + inbound coroutines
  - `stop_binding(cwd)` cancels + persists state
  - Auto-discovers jsonl path via `~/.claude/projects/<encoded-cwd>/` mtime
- Real `start`/`stop` handlers wired to orchestrator
- Daemon entry instantiates orchestrator at startup with `RealTmux` + `RealLarkCli`
- Full lifecycle integration test passes with fakes

## What's intentionally missing

- `bind` handler still stubbed (Phase 7 adds OAuth)
- No menu push (Phase 7)
- No backlog progress card (could be added later as polish)
- No daemon-side state recovery on restart (TODO: orchestrator.restore_from_disk)

## Next phase preview

Phase 7 — Real OAuth + Menu Push:
- Real `bind` handler: spawn `lark-cli auth bot-new`, stream QR ASCII, persist credentials to keychain
- Menu JSON push via lark-cli (or fallback file)
- Real chat_id resolution
```

- [ ] **Step 4: Commit + tag**

```bash
git add tests/integration/test_lifecycle.py docs/phase-6-summary.md
git commit -m "test+docs: phase 6 lifecycle integration + summary"
git tag -a phase-6-complete -m "Phase 6: orchestrator + lifecycle complete"
```

---

## Phase 6 Done. Next: Phase 7 — Real Feishu Auth + Menu Push
