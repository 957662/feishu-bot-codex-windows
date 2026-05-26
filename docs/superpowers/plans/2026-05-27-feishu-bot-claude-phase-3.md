# feishu-bot-claude — Phase 3: External Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the two external dependencies (tmux + lark-cli) behind clean, testable interfaces. After Phase 3, the daemon can drive tmux sessions and exchange messages with Feishu via lark-cli — but no orchestration yet (that's Phase 5-6). Pure adapter layer.

**Architecture:** Each adapter is a Python class with one job. `Tmux` wraps the `tmux` binary; `LarkCli` wraps the `lark-cli` binary. Both have a real implementation and a fake backend. Real implementations spawn subprocesses; fakes record calls and replay canned responses for tests.

**Tech Stack:** Python asyncio subprocess, no new deps. `lark-cli` (already cloned to `vendor/lark-cli/`, installed globally via npm).

**Prerequisite:** Phase 2 complete (`phase-2-complete` git tag).

**Scope (Phase 3 deliverables):**
- `feishu_bot_claude/daemon/tmux.py` — `Tmux` interface + `RealTmux` + `FakeTmux`
- `feishu_bot_claude/daemon/feishu.py` — `LarkCli` interface + `RealLarkCli` + `FakeLarkCli`
- Unit tests for both adapters (using fakes for hot path, real backends for one smoke test each)

**Out of scope:**
- Orchestration (Phase 5-6)
- Card rendering (Phase 4)
- Real OAuth flow (Phase 7) — Phase 3 only covers `send` and `consume`, not `auth bot-new`

---

## File Structure (Phase 3)

| Path | Responsibility |
|---|---|
| `feishu_bot_claude/daemon/tmux.py` | `Tmux` abstract + 2 implementations |
| `feishu_bot_claude/daemon/feishu.py` | `LarkCli` abstract + 2 implementations |
| `tests/unit/test_tmux_fake.py` | `FakeTmux` behavior tests |
| `tests/unit/test_feishu_fake.py` | `FakeLarkCli` behavior tests |
| `tests/integration/test_tmux_real.py` | Real tmux smoke test (`@skipif_no_tmux`) |
| `tests/integration/test_feishu_real.py` | Real lark-cli smoke test (`@skipif_no_lark_cli`) — only checks subprocess startup and `--help`, not real Feishu auth |

---

## Phase 3 Tasks

### Task 3.1: Tmux interface + FakeTmux

**Files:**
- Create: `feishu_bot_claude/daemon/tmux.py`
- Create: `tests/unit/test_tmux_fake.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_tmux_fake.py`:
```python
"""Tests for FakeTmux — records calls, replays canned responses."""

import pytest

from feishu_bot_claude.daemon.tmux import FakeTmux, Tmux


def test_fake_records_new_session():
    tmux: Tmux = FakeTmux()
    tmux.new_session(name="claude-foo", cwd="/abs/foo", command="claude")
    assert tmux.calls == [
        ("new_session", {"name": "claude-foo", "cwd": "/abs/foo", "command": "claude"}),
    ]


def test_fake_has_session_returns_configured_value():
    tmux = FakeTmux()
    tmux.set_session("claude-foo", exists=True)
    assert tmux.has_session("claude-foo") is True
    assert tmux.has_session("claude-other") is False


def test_fake_send_keys_records():
    tmux = FakeTmux()
    tmux.set_session("claude-foo", exists=True)
    tmux.send_keys(session="claude-foo", keys="/compact\n")
    assert tmux.calls[-1] == ("send_keys", {"session": "claude-foo", "keys": "/compact\n"})


def test_fake_send_keys_raises_if_session_missing():
    tmux = FakeTmux()
    with pytest.raises(RuntimeError, match="no session"):
        tmux.send_keys(session="claude-foo", keys="x")


def test_fake_kill_session_records():
    tmux = FakeTmux()
    tmux.set_session("claude-foo", exists=True)
    tmux.kill_session("claude-foo")
    assert ("kill_session", {"name": "claude-foo"}) in tmux.calls
    assert tmux.has_session("claude-foo") is False


def test_fake_new_session_idempotent_with_attach_existing():
    """new_session(attach_if_exists=True) on an existing session is a no-op."""
    tmux = FakeTmux()
    tmux.set_session("claude-foo", exists=True)
    tmux.new_session(name="claude-foo", cwd="/abs/foo", command="claude", attach_if_exists=True)
    # Should NOT raise, should record an "attach" call instead
    last = tmux.calls[-1]
    assert last[0] in ("attach_session", "no_op_session_exists")
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_tmux_fake.py -xvs
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `Tmux` interface and `FakeTmux`**

Create `feishu_bot_claude/daemon/tmux.py`:
```python
"""tmux process wrapper: real + fake implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Tmux(ABC):
    """Interface for tmux session management."""

    @abstractmethod
    def has_session(self, name: str) -> bool:
        """Return True if a tmux session with `name` exists."""

    @abstractmethod
    def new_session(self, name: str, cwd: str, command: str, attach_if_exists: bool = False) -> None:
        """Create a new detached tmux session named `name` running `command` in `cwd`.

        If `attach_if_exists` is True and a session with `name` already exists, behaves
        as a no-op (the caller will attach separately).
        If False and the session exists, raises ValueError.
        """

    @abstractmethod
    def send_keys(self, session: str, keys: str) -> None:
        """Send literal keystrokes to the session's primary pane.

        `keys` should include trailing newlines if you want Enter pressed.
        Raises RuntimeError if the session doesn't exist.
        """

    @abstractmethod
    def kill_session(self, name: str) -> None:
        """Kill the session. No-op if missing."""


class FakeTmux(Tmux):
    """In-memory fake — records all calls, lets tests configure session existence."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._sessions: set[str] = set()

    def set_session(self, name: str, exists: bool) -> None:
        """Test helper: set whether a session is considered alive."""
        if exists:
            self._sessions.add(name)
        else:
            self._sessions.discard(name)

    def has_session(self, name: str) -> bool:
        self.calls.append(("has_session", {"name": name}))
        return name in self._sessions

    def new_session(self, name: str, cwd: str, command: str, attach_if_exists: bool = False) -> None:
        if name in self._sessions:
            if attach_if_exists:
                self.calls.append(("attach_session", {"name": name}))
                return
            raise ValueError(f"session {name!r} already exists")
        self.calls.append(("new_session", {"name": name, "cwd": cwd, "command": command}))
        self._sessions.add(name)

    def send_keys(self, session: str, keys: str) -> None:
        if session not in self._sessions:
            raise RuntimeError(f"no session: {session!r}")
        self.calls.append(("send_keys", {"session": session, "keys": keys}))

    def kill_session(self, name: str) -> None:
        self.calls.append(("kill_session", {"name": name}))
        self._sessions.discard(name)
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_tmux_fake.py -xvs
```
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/tmux.py tests/unit/test_tmux_fake.py
git commit -m "feat(daemon): add Tmux interface and FakeTmux for tests"
```

---

### Task 3.2: RealTmux — actual subprocess implementation

**Files:**
- Modify: `feishu_bot_claude/daemon/tmux.py`
- Create: `tests/integration/test_tmux_real.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_tmux_real.py`:
```python
"""Real tmux smoke test — requires `tmux` binary on PATH."""

import shutil
import time
import uuid

import pytest

from feishu_bot_claude.daemon.tmux import RealTmux

pytestmark = pytest.mark.skipif(
    shutil.which("tmux") is None,
    reason="tmux not installed",
)


def test_real_tmux_lifecycle():
    """Create → has_session → send_keys → kill_session lifecycle works."""
    session = f"fbc-test-{uuid.uuid4().hex[:8]}"
    tmux = RealTmux()
    try:
        assert tmux.has_session(session) is False
        tmux.new_session(name=session, cwd="/tmp", command="sleep 30")
        assert tmux.has_session(session) is True
        # Send a harmless key; verify no exception
        tmux.send_keys(session=session, keys="echo hi\n")
        time.sleep(0.1)  # let tmux apply
    finally:
        tmux.kill_session(session)
        assert tmux.has_session(session) is False


def test_real_tmux_new_session_rejects_duplicate():
    session = f"fbc-test-{uuid.uuid4().hex[:8]}"
    tmux = RealTmux()
    try:
        tmux.new_session(name=session, cwd="/tmp", command="sleep 30")
        with pytest.raises(ValueError, match="already exists"):
            tmux.new_session(name=session, cwd="/tmp", command="sleep 30")
    finally:
        tmux.kill_session(session)


def test_real_tmux_new_session_attaches_if_requested():
    """attach_if_exists=True on existing session is a no-op."""
    session = f"fbc-test-{uuid.uuid4().hex[:8]}"
    tmux = RealTmux()
    try:
        tmux.new_session(name=session, cwd="/tmp", command="sleep 30")
        tmux.new_session(name=session, cwd="/tmp", command="sleep 30", attach_if_exists=True)
        # Should not raise; session still alive
        assert tmux.has_session(session) is True
    finally:
        tmux.kill_session(session)


def test_real_tmux_send_keys_to_missing_session_raises():
    tmux = RealTmux()
    with pytest.raises(RuntimeError, match="no session"):
        tmux.send_keys(session="absolutely-not-existing-abcxyz", keys="x")
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/integration/test_tmux_real.py -xvs
```
Expected: `ImportError: cannot import name 'RealTmux'` (or skip if no tmux).

- [ ] **Step 3: Implement `RealTmux`**

Append to `feishu_bot_claude/daemon/tmux.py`:
```python
import subprocess


class RealTmux(Tmux):
    """Real tmux backend — shells out to `tmux` binary."""

    _NO_SESSION_RETURNCODE = 1  # tmux's exit code when the session is missing

    def has_session(self, name: str) -> bool:
        result = subprocess.run(
            ["tmux", "has-session", "-t", name],
            capture_output=True, text=True,
        )
        return result.returncode == 0

    def new_session(self, name: str, cwd: str, command: str, attach_if_exists: bool = False) -> None:
        if self.has_session(name):
            if attach_if_exists:
                return
            raise ValueError(f"session {name!r} already exists")
        result = subprocess.run(
            ["tmux", "new-session", "-d", "-s", name, "-c", cwd, command],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"tmux new-session failed (exit {result.returncode}): {result.stderr.strip()}"
            )

    def send_keys(self, session: str, keys: str) -> None:
        # Use -l (literal) so /, $, etc. aren't interpreted by tmux's key syntax.
        # Send the keys themselves, then a separate Enter so newlines are reliable.
        # But: caller passes \n in `keys` expecting Enter; we strip trailing \n
        # and send Enter explicitly so it behaves the same across tmux versions.
        stripped = keys
        needs_enter = stripped.endswith("\n")
        if needs_enter:
            stripped = stripped.rstrip("\n")

        if stripped:
            result = subprocess.run(
                ["tmux", "send-keys", "-t", session, "-l", stripped],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                # tmux returns 1 when session doesn't exist (among other things)
                msg = result.stderr.strip()
                if "can't find session" in msg or "no session" in msg.lower():
                    raise RuntimeError(f"no session: {session!r}")
                raise RuntimeError(f"tmux send-keys failed: {msg}")

        if needs_enter:
            result = subprocess.run(
                ["tmux", "send-keys", "-t", session, "Enter"],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                msg = result.stderr.strip()
                if "can't find session" in msg or "no session" in msg.lower():
                    raise RuntimeError(f"no session: {session!r}")
                raise RuntimeError(f"tmux send-keys Enter failed: {msg}")

    def kill_session(self, name: str) -> None:
        result = subprocess.run(
            ["tmux", "kill-session", "-t", name],
            capture_output=True, text=True,
        )
        # Exit 1 with "can't find session" is fine — it's a no-op
        if result.returncode != 0 and "can't find session" not in result.stderr:
            raise RuntimeError(f"tmux kill-session failed: {result.stderr.strip()}")
```

- [ ] **Step 4: Verify**

```bash
pytest tests/integration/test_tmux_real.py -xvs
```
Expected: `4 passed` on macOS (with tmux). `4 skipped` if no tmux.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/tmux.py tests/integration/test_tmux_real.py
git commit -m "feat(daemon): add RealTmux backend via tmux subprocess"
```

---

### Task 3.3: LarkCli interface + FakeLarkCli

**Files:**
- Create: `feishu_bot_claude/daemon/feishu.py`
- Create: `tests/unit/test_feishu_fake.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_feishu_fake.py`:
```python
"""Tests for FakeLarkCli — records send/consume calls, replays canned events."""

import json
import asyncio

import pytest

from feishu_bot_claude.daemon.feishu import FakeLarkCli, LarkCli


@pytest.mark.asyncio
async def test_fake_send_text_records():
    lark: LarkCli = FakeLarkCli()
    msg_id = await lark.send_text(chat_id="oc_xxx", text="hello", idempotency_key="k1")
    assert msg_id.startswith("om_fake_")  # fake generates an om_ id
    assert lark.send_calls[-1] == {
        "kind": "text",
        "chat_id": "oc_xxx",
        "text": "hello",
        "idempotency_key": "k1",
    }


@pytest.mark.asyncio
async def test_fake_send_card_records():
    lark = FakeLarkCli()
    card = {"elements": [{"tag": "markdown", "content": "hi"}]}
    msg_id = await lark.send_card(chat_id="oc_xxx", card=card, idempotency_key="k2")
    assert msg_id.startswith("om_fake_")
    assert lark.send_calls[-1] == {
        "kind": "card",
        "chat_id": "oc_xxx",
        "card": card,
        "idempotency_key": "k2",
    }


@pytest.mark.asyncio
async def test_fake_update_card_records():
    lark = FakeLarkCli()
    card = {"elements": []}
    await lark.update_card(message_id="om_fake_1", card=card)
    assert lark.send_calls[-1] == {
        "kind": "update",
        "message_id": "om_fake_1",
        "card": card,
    }


@pytest.mark.asyncio
async def test_fake_consume_yields_queued_events():
    lark = FakeLarkCli()
    # Queue two events before subscribing
    lark.enqueue_event({"type": "im.message.receive_v1", "event": {"message": {"content": '{"text":"hi"}'}}})
    lark.enqueue_event({"type": "im.message.receive_v1", "event": {"message": {"content": '{"text":"again"}'}}})

    received = []
    async for evt in lark.consume_events(event_key="im.message.receive_v1", max_events=2):
        received.append(evt)

    assert len(received) == 2
    assert received[0]["event"]["message"]["content"] == '{"text":"hi"}'


@pytest.mark.asyncio
async def test_fake_consume_obeys_max_events():
    lark = FakeLarkCli()
    for i in range(5):
        lark.enqueue_event({"event": {"i": i}})

    received = []
    async for evt in lark.consume_events(event_key="im.message.receive_v1", max_events=3):
        received.append(evt)
    assert len(received) == 3
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_feishu_fake.py -xvs
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `LarkCli` interface + `FakeLarkCli`**

Create `feishu_bot_claude/daemon/feishu.py`:
```python
"""lark-cli subprocess wrapper: real + fake implementations.

Real implementation spawns `lark-cli` subprocesses for each operation.
Fake records calls and replays canned NDJSON events for tests.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import AsyncIterator


class LarkCli(ABC):
    """Async wrapper around the `lark-cli` binary."""

    @abstractmethod
    async def send_text(self, chat_id: str, text: str, idempotency_key: str | None = None) -> str:
        """Send a plain text message. Returns the message_id (om_xxx)."""

    @abstractmethod
    async def send_card(self, chat_id: str, card: dict, idempotency_key: str | None = None) -> str:
        """Send an interactive card. Returns the message_id."""

    @abstractmethod
    async def update_card(self, message_id: str, card: dict) -> None:
        """Update the content of a previously-sent card by message_id."""

    @abstractmethod
    def consume_events(self, event_key: str, max_events: int = 0) -> AsyncIterator[dict]:
        """Subscribe to a Feishu event key, yielding event dicts as they arrive.

        max_events=0 means unlimited.
        Returns an async generator; cancellation cleanly terminates the subprocess.
        """


class FakeLarkCli(LarkCli):
    """In-memory fake — records send calls, replays queued consume events."""

    def __init__(self) -> None:
        self.send_calls: list[dict] = []
        self._consume_queue: list[dict] = []
        self._counter = 0

    def _next_message_id(self) -> str:
        self._counter += 1
        return f"om_fake_{self._counter}"

    def enqueue_event(self, event: dict) -> None:
        """Test helper: add an event for the next consume() call to yield."""
        self._consume_queue.append(event)

    async def send_text(self, chat_id: str, text: str, idempotency_key: str | None = None) -> str:
        self.send_calls.append({
            "kind": "text",
            "chat_id": chat_id,
            "text": text,
            "idempotency_key": idempotency_key,
        })
        return self._next_message_id()

    async def send_card(self, chat_id: str, card: dict, idempotency_key: str | None = None) -> str:
        self.send_calls.append({
            "kind": "card",
            "chat_id": chat_id,
            "card": card,
            "idempotency_key": idempotency_key,
        })
        return self._next_message_id()

    async def update_card(self, message_id: str, card: dict) -> None:
        self.send_calls.append({
            "kind": "update",
            "message_id": message_id,
            "card": card,
        })

    async def consume_events(self, event_key: str, max_events: int = 0) -> AsyncIterator[dict]:
        emitted = 0
        while True:
            if not self._consume_queue:
                # No more queued events: in tests, exit cleanly.
                break
            yield self._consume_queue.pop(0)
            emitted += 1
            if max_events > 0 and emitted >= max_events:
                break
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_feishu_fake.py -xvs
```
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/feishu.py tests/unit/test_feishu_fake.py
git commit -m "feat(daemon): add LarkCli interface and FakeLarkCli for tests"
```

---

### Task 3.4: RealLarkCli — subprocess wrapper

**Files:**
- Modify: `feishu_bot_claude/daemon/feishu.py`
- Create: `tests/integration/test_feishu_real.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_feishu_real.py`:
```python
"""Real lark-cli smoke test — only verifies subprocess startup, no Feishu auth required."""

import shutil

import pytest

from feishu_bot_claude.daemon.feishu import RealLarkCli

pytestmark = pytest.mark.skipif(
    shutil.which("lark-cli") is None,
    reason="lark-cli not installed (run `npm install -g @larksuite/cli`)",
)


@pytest.mark.asyncio
async def test_lark_cli_help_succeeds():
    """`lark-cli --help` should exit 0 — proves binary is on PATH and runnable."""
    lark = RealLarkCli()
    out, code = await lark._run_raw(["--help"], timeout=5.0)
    assert code == 0
    assert "lark-cli" in out.lower() or "usage" in out.lower()


@pytest.mark.asyncio
async def test_lark_cli_version_format():
    lark = RealLarkCli()
    out, code = await lark._run_raw(["--version"], timeout=5.0)
    assert code == 0
    # Version output should contain digits
    assert any(c.isdigit() for c in out)
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/integration/test_feishu_real.py -xvs
```
Expected: `ImportError: cannot import name 'RealLarkCli'`.

- [ ] **Step 3: Implement `RealLarkCli`**

Append to `feishu_bot_claude/daemon/feishu.py`:
```python
import json
import os


class RealLarkCli(LarkCli):
    """Real backend — spawns `lark-cli` subprocesses for each operation.

    Authentication is expected to be set up externally before instantiating
    this (via `lark-cli auth login` or via env vars). Each `send`/`consume`
    runs a fresh subprocess.
    """

    def __init__(self, binary: str = "lark-cli", as_bot: bool = True, extra_env: dict[str, str] | None = None) -> None:
        self._binary = binary
        self._as_bot = as_bot
        self._extra_env = dict(extra_env or {})

    async def _run_raw(self, args: list[str], timeout: float = 30.0) -> tuple[str, int]:
        """Run `lark-cli <args>`. Return (stdout, returncode)."""
        env = os.environ.copy()
        env.update(self._extra_env)
        proc = await asyncio.create_subprocess_exec(
            self._binary, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise
        return stdout.decode(), proc.returncode

    def _common_args(self) -> list[str]:
        return ["--as", "bot"] if self._as_bot else []

    async def send_text(self, chat_id: str, text: str, idempotency_key: str | None = None) -> str:
        args = [
            "im", "+messages-send",
            *self._common_args(),
            "--chat-id", chat_id,
            "--type", "text",
            "--text", text,
        ]
        if idempotency_key:
            args += ["--idempotency-key", idempotency_key]
        out, code = await self._run_raw(args, timeout=30.0)
        if code != 0:
            raise RuntimeError(f"lark-cli im +messages-send failed (exit {code}): {out!r}")
        # Output is JSON containing message_id (per lark-cli docs)
        try:
            payload = json.loads(out.strip().splitlines()[-1])
            return payload["message_id"]
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            raise RuntimeError(f"could not extract message_id from lark-cli output: {out!r}") from e

    async def send_card(self, chat_id: str, card: dict, idempotency_key: str | None = None) -> str:
        args = [
            "im", "+messages-send",
            *self._common_args(),
            "--chat-id", chat_id,
            "--type", "interactive",
            "--card", json.dumps(card, ensure_ascii=False),
        ]
        if idempotency_key:
            args += ["--idempotency-key", idempotency_key]
        out, code = await self._run_raw(args, timeout=30.0)
        if code != 0:
            raise RuntimeError(f"lark-cli send_card failed (exit {code}): {out!r}")
        try:
            payload = json.loads(out.strip().splitlines()[-1])
            return payload["message_id"]
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            raise RuntimeError(f"could not extract message_id: {out!r}") from e

    async def update_card(self, message_id: str, card: dict) -> None:
        args = [
            "im", "messages", "patch",
            *self._common_args(),
            "--message-id", message_id,
            "--card", json.dumps(card, ensure_ascii=False),
        ]
        out, code = await self._run_raw(args, timeout=30.0)
        if code != 0:
            raise RuntimeError(f"lark-cli update_card failed (exit {code}): {out!r}")

    async def consume_events(self, event_key: str, max_events: int = 0) -> AsyncIterator[dict]:
        args = [
            "event", "consume", event_key,
            *self._common_args(),
        ]
        if max_events > 0:
            args += ["--max-events", str(max_events)]

        env = os.environ.copy()
        env.update(self._extra_env)
        proc = await asyncio.create_subprocess_exec(
            self._binary, *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                line_str = line.decode().rstrip("\n")
                if not line_str.strip():
                    continue
                try:
                    yield json.loads(line_str)
                except json.JSONDecodeError:
                    # Skip non-JSON output (e.g. stderr-style banners)
                    continue
        finally:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
```

- [ ] **Step 4: Verify**

```bash
pytest tests/integration/test_feishu_real.py -xvs
```
Expected: `2 passed` if `lark-cli` is installed; `2 skipped` otherwise.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/feishu.py tests/integration/test_feishu_real.py
git commit -m "feat(daemon): add RealLarkCli subprocess wrapper"
```

---

### Task 3.5: Phase 3 wrap-up

**Files:**
- Create: `docs/phase-3-summary.md`

- [ ] **Step 1: Write summary**

Create `docs/phase-3-summary.md`:
```markdown
# Phase 3 Summary

**Date completed:** <fill in>

## What's in place

- `daemon/tmux.py` — `Tmux` ABC, `FakeTmux` (records calls + configurable session
  state), `RealTmux` (subprocess wrapper around `tmux has-session/new-session/send-keys/kill-session`)
- `daemon/feishu.py` — `LarkCli` ABC, `FakeLarkCli` (records send + queued
  consume events), `RealLarkCli` (subprocess wrapper around `lark-cli` for
  send_text/send_card/update_card/consume_events)
- Real-binary smoke tests (skip when binaries absent)
- Fake-only unit tests for behavior

## Verification

```bash
pytest tests/unit/test_tmux_fake.py tests/unit/test_feishu_fake.py -v
pytest tests/integration/test_tmux_real.py tests/integration/test_feishu_real.py -v
```

## What's intentionally missing

- No `auth bot-new` wrapper yet (Phase 7 covers OAuth flow)
- No menu push API (Phase 7)
- No file upload (Phase 4 / `uploads.py` will use `lark-cli drive +upload`)
- No retry/backoff logic in adapters (Phase 9 hardening adds this around the call sites)

## Next phase preview

Phase 4 — Card rendering: `card.py`, `turn.py`, `tools.py`, `uploads.py` with
golden fixtures for every Claude jsonl event type.
```

- [ ] **Step 2: Commit + tag**

```bash
git add docs/phase-3-summary.md
git commit -m "docs: phase 3 summary"
git tag -a phase-3-complete -m "Phase 3: external adapters (tmux + lark-cli) complete"
```

---

## Phase 3 Done. Next: Phase 4 — Card Rendering

The next plan covers `rendering/` package: turn-based card building, per-tool
formatting, long-output upload, and golden-file testing.
