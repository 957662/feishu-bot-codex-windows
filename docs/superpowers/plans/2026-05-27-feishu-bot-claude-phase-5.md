# feishu-bot-claude — Phase 5: Mirror Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the outbound and inbound mirror pipelines. After Phase 5, given a running daemon with one binding (configured via fake adapters), changes to a jsonl file produce Feishu card updates, and incoming Feishu messages produce tmux send-keys calls. End-to-end with fakes; no orchestrator yet.

**Architecture:** Two async pipelines per binding. Outbound: `OutboundPipeline` watches a jsonl path with `watchfiles`, groups new events into turns, calls `LarkCli.send_card`/`update_card` via a `TokenBucket`-rate-limited queue. Inbound: `InboundPipeline` consumes `lark-cli event consume` NDJSON, parses each event, dispatches to `Tmux.send_keys` (text/slash) or daemon-internal handler (bridge ops). Both use injected `LarkCli` and `Tmux` (real or fake).

**Tech Stack:** Adds `watchfiles >= 0.21` (async-friendly file watcher). asyncio queues.

**Prerequisite:** Phase 4 complete.

**Scope (Phase 5 deliverables):**
- `feishu_bot_claude/daemon/ratelimit.py` — `TokenBucket` + 11232 backoff
- `feishu_bot_claude/daemon/outbound.py` — `OutboundPipeline`
- `feishu_bot_claude/daemon/inbound.py` — `InboundPipeline`
- `feishu_bot_claude/daemon/state.py` — per-binding state (current turn card msg_id, jsonl offset)
- All unit-tested with `FakeTmux`/`FakeLarkCli` + tempfile jsonl

---

## File Structure (Phase 5)

| Path | Responsibility |
|---|---|
| `feishu_bot_claude/daemon/ratelimit.py` | `TokenBucket` (async wait/try_acquire), `BackoffPolicy` for 11232 errors |
| `feishu_bot_claude/daemon/state.py` | `BindingRuntimeState` — current turn card msg_id, jsonl byte_offset, last assistant event |
| `feishu_bot_claude/daemon/outbound.py` | `OutboundPipeline` class: watch jsonl, render turns, send cards |
| `feishu_bot_claude/daemon/inbound.py` | `InboundPipeline` class: read NDJSON from `LarkCli.consume_events`, route to tmux/handler |
| `tests/unit/test_ratelimit.py` | `TokenBucket` + backoff tests |
| `tests/unit/test_state.py` | `BindingRuntimeState` tests |
| `tests/unit/test_outbound.py` | Pipeline tests with fakes |
| `tests/unit/test_inbound.py` | Pipeline tests with fakes |

---

## Phase 5 Tasks

### Task 5.1: ratelimit.py — TokenBucket

**Files:**
- Create: `feishu_bot_claude/daemon/ratelimit.py`
- Create: `tests/unit/test_ratelimit.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_ratelimit.py`:
```python
"""Tests for TokenBucket rate limiter."""

import asyncio
import time

import pytest

from feishu_bot_claude.daemon.ratelimit import TokenBucket


@pytest.mark.asyncio
async def test_acquire_immediate_when_tokens_available():
    bucket = TokenBucket(rate_per_sec=10, capacity=10)
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05  # immediate


@pytest.mark.asyncio
async def test_acquire_blocks_when_empty():
    bucket = TokenBucket(rate_per_sec=10, capacity=2)
    # Drain
    await bucket.acquire()
    await bucket.acquire()
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    # At 10/sec, next token takes ~100ms
    assert 0.07 <= elapsed <= 0.25, f"expected ~0.1s, got {elapsed:.3f}"


@pytest.mark.asyncio
async def test_refill_over_time():
    bucket = TokenBucket(rate_per_sec=10, capacity=5)
    # Drain all
    for _ in range(5):
        await bucket.acquire()
    # Wait 250ms — should refill ~2 tokens
    await asyncio.sleep(0.25)
    # Both of these should be immediate
    start = time.monotonic()
    await bucket.acquire()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.05, f"expected near-zero, got {elapsed:.3f}"


@pytest.mark.asyncio
async def test_try_acquire_returns_false_when_empty():
    bucket = TokenBucket(rate_per_sec=10, capacity=1)
    assert bucket.try_acquire() is True
    assert bucket.try_acquire() is False
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_ratelimit.py -xvs
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `TokenBucket`**

Create `feishu_bot_claude/daemon/ratelimit.py`:
```python
"""Rate limiting: TokenBucket and exponential backoff for Feishu 11232 throttle."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


class TokenBucket:
    """Async token bucket. capacity tokens, refills at rate_per_sec."""

    def __init__(self, rate_per_sec: float, capacity: int) -> None:
        self._rate = rate_per_sec
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    async def acquire(self) -> None:
        """Block until one token is available, then consume it."""
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                deficit = 1.0 - self._tokens
                wait_seconds = deficit / self._rate
            await asyncio.sleep(wait_seconds + 0.001)

    def try_acquire(self) -> bool:
        """Non-blocking: return True if a token was consumed, False otherwise."""
        self._refill()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


@dataclass(frozen=True)
class BackoffPolicy:
    """Exponential backoff for Feishu 11232 throttle and similar transient errors."""

    initial_sec: float = 1.0
    multiplier: float = 2.0
    max_sec: float = 30.0
    max_attempts: int = 7  # 1+2+4+8+16+30+30 = 91 seconds total

    def delay_for(self, attempt: int) -> float:
        """Return the sleep duration after `attempt` failures (1-based)."""
        delay = self.initial_sec * (self.multiplier ** (attempt - 1))
        return min(delay, self.max_sec)
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_ratelimit.py -xvs
```
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/ratelimit.py tests/unit/test_ratelimit.py
git commit -m "feat(daemon): add TokenBucket and BackoffPolicy"
```

---

### Task 5.2: state.py — BindingRuntimeState

**Files:**
- Create: `feishu_bot_claude/daemon/state.py`
- Create: `tests/unit/test_state.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_state.py`:
```python
"""Tests for BindingRuntimeState — per-binding live state."""

import pytest

from feishu_bot_claude.daemon.state import BindingRuntimeState


def test_initial_state_empty():
    s = BindingRuntimeState(binding_name="foo-bot")
    assert s.current_turn_card_id is None
    assert s.jsonl_offset == 0
    assert s.last_event_uuid is None


def test_set_current_turn_card():
    s = BindingRuntimeState(binding_name="foo-bot")
    s.set_current_turn_card("om_xxx")
    assert s.current_turn_card_id == "om_xxx"


def test_reset_clears_card_keeps_offset():
    s = BindingRuntimeState(binding_name="foo-bot")
    s.set_current_turn_card("om_xxx")
    s.advance_offset(100)
    s.reset_current_turn()
    assert s.current_turn_card_id is None
    assert s.jsonl_offset == 100


def test_persist_and_restore(tmp_path):
    path = tmp_path / "state.json"
    s = BindingRuntimeState(binding_name="foo-bot")
    s.set_current_turn_card("om_xxx")
    s.advance_offset(42)
    s.last_event_uuid = "e-99"
    s.save(path)

    restored = BindingRuntimeState.load("foo-bot", path)
    assert restored.current_turn_card_id == "om_xxx"
    assert restored.jsonl_offset == 42
    assert restored.last_event_uuid == "e-99"


def test_load_missing_file_returns_fresh_state(tmp_path):
    state = BindingRuntimeState.load("missing-bot", tmp_path / "nope.json")
    assert state.binding_name == "missing-bot"
    assert state.current_turn_card_id is None
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_state.py -xvs
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `BindingRuntimeState`**

Create `feishu_bot_claude/daemon/state.py`:
```python
"""Per-binding runtime state — what jsonl byte we're at, what card we're updating."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class BindingRuntimeState:
    """Mutable per-binding state, persisted as JSON for crash recovery."""

    binding_name: str
    current_turn_card_id: str | None = None
    jsonl_offset: int = 0
    last_event_uuid: str | None = None

    def set_current_turn_card(self, message_id: str) -> None:
        self.current_turn_card_id = message_id

    def reset_current_turn(self) -> None:
        self.current_turn_card_id = None

    def advance_offset(self, delta: int) -> None:
        self.jsonl_offset += delta

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "binding_name": self.binding_name,
            "current_turn_card_id": self.current_turn_card_id,
            "jsonl_offset": self.jsonl_offset,
            "last_event_uuid": self.last_event_uuid,
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        tmp.replace(path)

    @classmethod
    def load(cls, binding_name: str, path: Path) -> "BindingRuntimeState":
        if not path.exists():
            return cls(binding_name=binding_name)
        data = json.loads(path.read_text())
        return cls(
            binding_name=binding_name,
            current_turn_card_id=data.get("current_turn_card_id"),
            jsonl_offset=data.get("jsonl_offset", 0),
            last_event_uuid=data.get("last_event_uuid"),
        )
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_state.py -xvs
```
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/state.py tests/unit/test_state.py
git commit -m "feat(daemon): per-binding runtime state with persist/restore"
```

---

### Task 5.3: outbound.py — OutboundPipeline

**Files:**
- Modify: `pyproject.toml` (add `watchfiles >= 0.21`)
- Create: `feishu_bot_claude/daemon/outbound.py`
- Create: `tests/unit/test_outbound.py`

- [ ] **Step 1: Add `watchfiles` dependency**

Edit `pyproject.toml`:
```toml
dependencies = [
    "tomli-w >= 1.0.0",
    "click >= 8.1.0",
    "watchfiles >= 0.21.0",
]
```
Reinstall: `pip install -e ".[dev]"`.

- [ ] **Step 2: Write failing tests**

Create `tests/unit/test_outbound.py`:
```python
"""Tests for OutboundPipeline — jsonl tail → card send/update."""

import asyncio
import json
from pathlib import Path

import pytest

from feishu_bot_claude.daemon.feishu import FakeLarkCli
from feishu_bot_claude.daemon.outbound import OutboundPipeline
from feishu_bot_claude.daemon.ratelimit import TokenBucket
from feishu_bot_claude.daemon.state import BindingRuntimeState


def _append_event(path: Path, event: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


@pytest.mark.asyncio
async def test_outbound_processes_existing_events_on_start(tmp_path):
    jsonl = tmp_path / "session.jsonl"
    _append_event(jsonl, {"role": "user", "uuid": "u1", "content": [{"type": "text", "text": "hi"}]})
    _append_event(jsonl, {"role": "assistant", "uuid": "a1", "content": [{"type": "text", "text": "hello"}]})

    lark = FakeLarkCli()
    state = BindingRuntimeState(binding_name="foo")
    bucket = TokenBucket(rate_per_sec=100, capacity=10)
    pipeline = OutboundPipeline(
        jsonl_path=jsonl,
        chat_id="oc_xxx",
        project_name="foo",
        state=state,
        lark=lark,
        bucket=bucket,
        render_style="rich",
    )

    # Process backlog without watching for new events
    await pipeline.process_backlog()

    # One user turn → one card sent (the assistant card)
    card_sends = [c for c in lark.send_calls if c.get("kind") == "card"]
    assert len(card_sends) == 1
    assert state.jsonl_offset > 0


@pytest.mark.asyncio
async def test_outbound_updates_card_on_tool_use(tmp_path):
    jsonl = tmp_path / "session.jsonl"
    _append_event(jsonl, {"role": "user", "uuid": "u1", "content": [{"type": "text", "text": "read it"}]})
    _append_event(jsonl, {"role": "assistant", "uuid": "a1", "content": [
        {"type": "text", "text": "ok"},
        {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/x"}},
    ]})
    _append_event(jsonl, {"role": "user", "uuid": "u2", "content": [
        {"type": "tool_result", "tool_use_id": "t1", "content": "data"},
    ]})

    lark = FakeLarkCli()
    state = BindingRuntimeState(binding_name="foo")
    pipeline = OutboundPipeline(
        jsonl_path=jsonl,
        chat_id="oc_xxx",
        project_name="foo",
        state=state,
        lark=lark,
        bucket=TokenBucket(rate_per_sec=100, capacity=10),
        render_style="rich",
    )
    await pipeline.process_backlog()

    # Should be: send_card (assistant initial) + update_card (after tool_result)
    kinds = [c["kind"] for c in lark.send_calls]
    assert kinds.count("card") == 1
    assert kinds.count("update") >= 1


@pytest.mark.asyncio
async def test_outbound_new_user_event_creates_new_card(tmp_path):
    jsonl = tmp_path / "session.jsonl"
    _append_event(jsonl, {"role": "user", "uuid": "u1", "content": [{"type": "text", "text": "first"}]})
    _append_event(jsonl, {"role": "assistant", "uuid": "a1", "content": [{"type": "text", "text": "a"}]})
    _append_event(jsonl, {"role": "user", "uuid": "u2", "content": [{"type": "text", "text": "second"}]})
    _append_event(jsonl, {"role": "assistant", "uuid": "a2", "content": [{"type": "text", "text": "b"}]})

    lark = FakeLarkCli()
    state = BindingRuntimeState(binding_name="foo")
    pipeline = OutboundPipeline(
        jsonl_path=jsonl,
        chat_id="oc_xxx",
        project_name="foo",
        state=state,
        lark=lark,
        bucket=TokenBucket(rate_per_sec=100, capacity=10),
        render_style="rich",
    )
    await pipeline.process_backlog()

    card_sends = [c for c in lark.send_calls if c["kind"] == "card"]
    # Two distinct assistant cards for two turns
    assert len(card_sends) == 2


@pytest.mark.asyncio
async def test_outbound_resume_from_offset(tmp_path):
    jsonl = tmp_path / "session.jsonl"
    _append_event(jsonl, {"role": "user", "uuid": "u1", "content": [{"type": "text", "text": "first"}]})
    _append_event(jsonl, {"role": "assistant", "uuid": "a1", "content": [{"type": "text", "text": "a"}]})

    lark = FakeLarkCli()
    state = BindingRuntimeState(binding_name="foo")
    # Pretend we already processed the whole file before
    state.jsonl_offset = jsonl.stat().st_size

    pipeline = OutboundPipeline(
        jsonl_path=jsonl,
        chat_id="oc_xxx",
        project_name="foo",
        state=state,
        lark=lark,
        bucket=TokenBucket(rate_per_sec=100, capacity=10),
        render_style="rich",
    )
    await pipeline.process_backlog()

    # No new events to process
    assert lark.send_calls == []

    # Append a new turn
    _append_event(jsonl, {"role": "user", "uuid": "u2", "content": [{"type": "text", "text": "second"}]})
    _append_event(jsonl, {"role": "assistant", "uuid": "a2", "content": [{"type": "text", "text": "b"}]})

    await pipeline.process_backlog()

    # Should send one new card (for the new turn)
    card_sends = [c for c in lark.send_calls if c["kind"] == "card"]
    assert len(card_sends) == 1
```

- [ ] **Step 3: Verify failure**

```bash
pytest tests/unit/test_outbound.py -xvs
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 4: Implement `OutboundPipeline`**

Create `feishu_bot_claude/daemon/outbound.py`:
```python
"""Outbound pipeline: jsonl tail → group into turns → send/update Feishu cards."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from feishu_bot_claude.daemon.feishu import LarkCli
from feishu_bot_claude.daemon.ratelimit import TokenBucket
from feishu_bot_claude.daemon.state import BindingRuntimeState
from feishu_bot_claude.rendering.turn import (
    JsonlEvent,
    Turn,
    group_into_turns,
    render_turn_to_card,
)

logger = logging.getLogger(__name__)


class OutboundPipeline:
    """Read jsonl events past state.jsonl_offset, render turns, send/update cards."""

    def __init__(
        self,
        jsonl_path: Path,
        chat_id: str,
        project_name: str,
        state: BindingRuntimeState,
        lark: LarkCli,
        bucket: TokenBucket,
        render_style: str = "rich",
    ) -> None:
        self._jsonl_path = Path(jsonl_path)
        self._chat_id = chat_id
        self._project_name = project_name
        self._state = state
        self._lark = lark
        self._bucket = bucket
        self._render_style = render_style
        self._buffered: list[JsonlEvent] = []
        self._current_turn: Turn | None = None

    async def process_backlog(self) -> None:
        """Read new bytes from jsonl past current offset; render any new turns."""
        if not self._jsonl_path.exists():
            return
        size = self._jsonl_path.stat().st_size
        if size <= self._state.jsonl_offset:
            return

        with self._jsonl_path.open("rb") as f:
            f.seek(self._state.jsonl_offset)
            new_bytes = f.read()
        self._state.jsonl_offset = size

        lines = new_bytes.decode("utf-8", errors="replace").splitlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = JsonlEvent.from_dict(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("skipping malformed jsonl line: %r", line[:80])
                continue
            await self._handle_event(event)

    async def _handle_event(self, event: JsonlEvent) -> None:
        # New user message (with text) → close any current turn, start a new one
        if event.role == "user" and not event.has_only_tool_results():
            self._buffered = [event]
            self._current_turn = Turn(user_event=event)
            # Don't send the user message itself; assistant card will appear when
            # the first assistant event arrives.
            self._state.reset_current_turn()
            return

        if self._current_turn is None:
            # Orphan event (no preceding user) — start synthetic turn
            self._current_turn = Turn(user_event=None)
            self._buffered = []

        self._buffered.append(event)
        self._current_turn.assistant_events.append(event)

        await self._send_or_update()

    async def _send_or_update(self) -> None:
        if self._current_turn is None:
            return
        card = render_turn_to_card(
            self._current_turn,
            project_name=self._project_name,
            render_style=self._render_style,
        )
        await self._bucket.acquire()
        if self._state.current_turn_card_id is None:
            msg_id = await self._lark.send_card(
                chat_id=self._chat_id,
                card=card,
                idempotency_key=f"{self._state.binding_name}-{self._current_turn.user_event.uuid if self._current_turn.user_event else 'orphan'}",
            )
            self._state.set_current_turn_card(msg_id)
        else:
            await self._lark.update_card(
                message_id=self._state.current_turn_card_id,
                card=card,
            )
```

- [ ] **Step 5: Verify**

```bash
pytest tests/unit/test_outbound.py -xvs
```
Expected: `4 passed`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml feishu_bot_claude/daemon/outbound.py tests/unit/test_outbound.py
git commit -m "feat(daemon): OutboundPipeline for jsonl→card mirroring"
```

---

### Task 5.4: inbound.py — InboundPipeline

**Files:**
- Create: `feishu_bot_claude/daemon/inbound.py`
- Create: `tests/unit/test_inbound.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_inbound.py`:
```python
"""Tests for InboundPipeline — Feishu events → tmux send-keys."""

import json

import pytest

from feishu_bot_claude.daemon.feishu import FakeLarkCli
from feishu_bot_claude.daemon.inbound import InboundPipeline
from feishu_bot_claude.daemon.tmux import FakeTmux


def _text_event(text: str, sender_id: str = "ou_user") -> dict:
    return {
        "type": "im.message.receive_v1",
        "event": {
            "sender": {"sender_id": {"open_id": sender_id}},
            "message": {
                "message_type": "text",
                "content": json.dumps({"text": text}),
            },
        },
    }


def _menu_event(event_key: str, sender_id: str = "ou_user") -> dict:
    return {
        "type": "application.bot.menu_v6",
        "event": {
            "operator": {"operator_id": {"open_id": sender_id}},
            "event_key": event_key,
        },
    }


@pytest.mark.asyncio
async def test_inbound_routes_text_to_tmux():
    tmux = FakeTmux()
    tmux.set_session("claude-foo", exists=True)
    lark = FakeLarkCli()
    lark.enqueue_event(_text_event("hello claude"))

    pipeline = InboundPipeline(
        tmux_session="claude-foo",
        tmux=tmux,
        lark=lark,
    )
    await pipeline.process_until_idle(max_events=1)

    send_keys_calls = [c for c in tmux.calls if c[0] == "send_keys"]
    assert len(send_keys_calls) == 1
    assert send_keys_calls[0][1]["keys"] == "hello claude\n"


@pytest.mark.asyncio
async def test_inbound_routes_slash_command_to_tmux():
    tmux = FakeTmux()
    tmux.set_session("claude-foo", exists=True)
    lark = FakeLarkCli()
    lark.enqueue_event(_text_event("/compact"))

    pipeline = InboundPipeline(
        tmux_session="claude-foo",
        tmux=tmux,
        lark=lark,
    )
    await pipeline.process_until_idle(max_events=1)

    send_keys_calls = [c for c in tmux.calls if c[0] == "send_keys"]
    assert send_keys_calls[0][1]["keys"] == "/compact\n"


@pytest.mark.asyncio
async def test_inbound_routes_menu_button_to_command():
    tmux = FakeTmux()
    tmux.set_session("claude-foo", exists=True)
    lark = FakeLarkCli()
    lark.enqueue_event(_menu_event("cmd_clear"))

    pipeline = InboundPipeline(
        tmux_session="claude-foo",
        tmux=tmux,
        lark=lark,
        menu_command_map={"cmd_clear": "/clear", "cmd_compact": "/compact"},
    )
    await pipeline.process_until_idle(max_events=1)

    send_keys_calls = [c for c in tmux.calls if c[0] == "send_keys"]
    assert send_keys_calls[0][1]["keys"] == "/clear\n"


@pytest.mark.asyncio
async def test_inbound_unknown_menu_key_logs_and_skips():
    tmux = FakeTmux()
    tmux.set_session("claude-foo", exists=True)
    lark = FakeLarkCli()
    lark.enqueue_event(_menu_event("totally_unknown_key"))

    pipeline = InboundPipeline(
        tmux_session="claude-foo",
        tmux=tmux,
        lark=lark,
        menu_command_map={"cmd_clear": "/clear"},
    )
    await pipeline.process_until_idle(max_events=1)

    # No tmux send-keys for unknown menu keys
    send_keys_calls = [c for c in tmux.calls if c[0] == "send_keys"]
    assert send_keys_calls == []


@pytest.mark.asyncio
async def test_inbound_whitelist_drops_other_senders():
    tmux = FakeTmux()
    tmux.set_session("claude-foo", exists=True)
    lark = FakeLarkCli()
    lark.enqueue_event(_text_event("hi", sender_id="ou_attacker"))

    pipeline = InboundPipeline(
        tmux_session="claude-foo",
        tmux=tmux,
        lark=lark,
        allow_users={"ou_owner"},  # whitelist excludes the sender
    )
    await pipeline.process_until_idle(max_events=1)

    send_keys_calls = [c for c in tmux.calls if c[0] == "send_keys"]
    assert send_keys_calls == []


@pytest.mark.asyncio
async def test_inbound_truncates_long_message():
    tmux = FakeTmux()
    tmux.set_session("claude-foo", exists=True)
    lark = FakeLarkCli()
    lark.enqueue_event(_text_event("x" * 20_000))

    pipeline = InboundPipeline(
        tmux_session="claude-foo",
        tmux=tmux,
        lark=lark,
        max_message_length=100,
    )
    await pipeline.process_until_idle(max_events=1)

    send_keys_calls = [c for c in tmux.calls if c[0] == "send_keys"]
    assert send_keys_calls
    keys = send_keys_calls[0][1]["keys"]
    # Truncated to ~100 chars + newline
    assert len(keys) <= 200
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_inbound.py -xvs
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `InboundPipeline`**

Create `feishu_bot_claude/daemon/inbound.py`:
```python
"""Inbound pipeline: Feishu events → tmux send-keys (text/slash/menu)."""

from __future__ import annotations

import json
import logging
from typing import Iterable

from feishu_bot_claude.daemon.feishu import LarkCli
from feishu_bot_claude.daemon.tmux import Tmux

logger = logging.getLogger(__name__)


class InboundPipeline:
    """Drive `lark-cli event consume`, route each event to tmux or a handler."""

    def __init__(
        self,
        tmux_session: str,
        tmux: Tmux,
        lark: LarkCli,
        menu_command_map: dict[str, str] | None = None,
        allow_users: set[str] | None = None,
        max_message_length: int = 8000,
        event_key: str = "im.message.receive_v1",
    ) -> None:
        self._tmux_session = tmux_session
        self._tmux = tmux
        self._lark = lark
        self._menu_command_map = menu_command_map or {}
        self._allow_users = allow_users
        self._max_message_length = max_message_length
        self._event_key = event_key

    async def process_until_idle(self, max_events: int = 0) -> None:
        """Consume events until the fake queue drains (test mode) or max_events hit."""
        count = 0
        async for event in self._lark.consume_events(self._event_key, max_events=max_events):
            await self._handle(event)
            count += 1
            if max_events and count >= max_events:
                break

    async def _handle(self, event: dict) -> None:
        evt_type = event.get("type", "")
        if evt_type == "im.message.receive_v1":
            await self._handle_message(event)
        elif evt_type == "application.bot.menu_v6":
            await self._handle_menu(event)
        else:
            logger.debug("ignoring event type: %s", evt_type)

    async def _handle_message(self, event: dict) -> None:
        msg = event.get("event", {}).get("message", {})
        sender = event.get("event", {}).get("sender", {}).get("sender_id", {}).get("open_id", "")
        if self._allow_users is not None and sender not in self._allow_users:
            logger.info("dropping message from non-whitelisted sender %s", sender)
            return
        if msg.get("message_type") != "text":
            logger.info("skipping non-text message type: %s", msg.get("message_type"))
            return
        content_json = msg.get("content", "{}")
        try:
            text = json.loads(content_json).get("text", "")
        except json.JSONDecodeError:
            logger.warning("malformed message content: %r", content_json[:80])
            return
        if not text:
            return
        if len(text) > self._max_message_length:
            text = text[: self._max_message_length] + "\n...[truncated]"
        self._tmux.send_keys(session=self._tmux_session, keys=text + "\n")

    async def _handle_menu(self, event: dict) -> None:
        ev = event.get("event", {})
        sender = ev.get("operator", {}).get("operator_id", {}).get("open_id", "")
        if self._allow_users is not None and sender not in self._allow_users:
            return
        event_key = ev.get("event_key", "")
        command = self._menu_command_map.get(event_key)
        if command is None:
            logger.info("unknown menu event_key: %s", event_key)
            return
        self._tmux.send_keys(session=self._tmux_session, keys=command + "\n")
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_inbound.py -xvs
```
Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/inbound.py tests/unit/test_inbound.py
git commit -m "feat(daemon): InboundPipeline routing text/slash/menu to tmux"
```

---

### Task 5.5: Phase 5 wrap-up

**Files:**
- Create: `docs/phase-5-summary.md`

- [ ] **Step 1: Run the full suite**

```bash
pytest -v
```
All tests should pass.

- [ ] **Step 2: Write summary**

Create `docs/phase-5-summary.md`:
```markdown
# Phase 5 Summary

**Date completed:** <fill in>

## What's in place

- `daemon/ratelimit.py` — `TokenBucket` (async wait + try_acquire), `BackoffPolicy`
- `daemon/state.py` — `BindingRuntimeState` with persist/restore
- `daemon/outbound.py` — `OutboundPipeline` reads new jsonl bytes past stored offset, groups into turns, calls `LarkCli.send_card`/`update_card` (rate-limited)
- `daemon/inbound.py` — `InboundPipeline` consumes `lark-cli event` NDJSON, routes text/slash/menu to `Tmux.send_keys`, supports user whitelist, truncates long messages
- All tested with FakeTmux + FakeLarkCli

## What's intentionally missing

- No watchfiles-based continuous tailing (Phase 6 orchestrator wires it up)
- No confirmation-button card rendering (Phase 6 handles the round-trip)
- No 11232 backoff *invocation* (the policy exists; orchestrator uses it in Phase 6)
- No backlog progress card (Phase 6)

## Next phase preview

Phase 6 — Orchestrator + Lifecycle:
- `daemon/orchestrator.py` — per-binding coroutine group (jsonl watcher + inbound + health)
- Wire `OutboundPipeline.process_backlog` + watchfiles for live tailing
- Implement real `bind`/`start`/`stop`/`unbind` handlers using the pipelines
- Backlog replay progress card with `--replay-on-start = all`
- Daemon-side state recovery on restart
```

- [ ] **Step 3: Commit + tag**

```bash
git add docs/phase-5-summary.md
git commit -m "docs: phase 5 summary"
git tag -a phase-5-complete -m "Phase 5: mirror pipeline complete"
```

---

## Phase 5 Done. Next: Phase 6 — Orchestrator + Lifecycle
