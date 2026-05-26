# feishu-bot-claude — Phase 9: Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Production-ready resilience and security. After Phase 9, the daemon recovers cleanly from crashes, applies rate-limit backoff on 11232 errors, detects stale tmux sessions, and supports opt-in security settings (user whitelist, dangerous-command confirmation, idle timeout). Final acceptance: a real end-to-end run with the user's actual project hits zero crashes over a week.

**Prerequisite:** Phase 8 complete (real usable system).

**Scope (Phase 9 deliverables):**
- Daemon state recovery on restart (re-attach running bindings from disk)
- 11232 backoff wired into LarkCli wrapper (`feishu.py`)
- Stale binding detection loop (`Orchestrator.health_check_loop`)
- Confirmation card flow for `/clear`-style prompts
- `BindingConfig.security` opt-in fields (allow_users, require_confirm_patterns, max_message_length, session_idle_timeout)
- chat_id resolution from first inbound message
- E2E hardening test: simulate daemon crash + restart, verify replay continues from offset
- Final README + user docs polish

---

## Phase 9 Tasks

### Task 9.1: Orchestrator state recovery on daemon restart

**Files:**
- Modify: `feishu_bot_claude/daemon/orchestrator.py`
- Modify: `feishu_bot_claude/__main__.py`
- Create: `tests/integration/test_state_recovery.py`

- [ ] **Step 1: Write failing test**

Create `tests/integration/test_state_recovery.py`:
```python
"""Test that daemon restart restores running bindings from disk state."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from feishu_bot_claude.config.binding import BindingConfig, BindingStore
from feishu_bot_claude.daemon.feishu import FakeLarkCli
from feishu_bot_claude.daemon.orchestrator import Orchestrator
from feishu_bot_claude.daemon.state import BindingRuntimeState
from feishu_bot_claude.daemon.tmux import FakeTmux


@pytest.mark.asyncio
async def test_orchestrator_restores_bindings_from_disk(tmp_path):
    project_dir = tmp_path / "p"; project_dir.mkdir()
    jsonl = tmp_path / "p.jsonl"
    jsonl.write_text("")

    cfg = BindingConfig(
        name="bot-p", project_dir=str(project_dir),
        tmux_session="claude-bot-p", feishu_app_id="cli_x",
        secret_ref="x", created_at=datetime.now(timezone.utc),
    )
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(cfg)

    # Simulate that the binding was running before crash: state.json exists with offset
    state = BindingRuntimeState(binding_name="bot-p", jsonl_offset=42)
    state.save(tmp_path / "state-bot-p.json")
    # Also write a "running" marker
    (tmp_path / "running-bot-p").write_text(json.dumps({"jsonl_path": str(jsonl)}))

    tmux = FakeTmux()
    tmux.set_session("claude-bot-p", exists=True)

    orch = Orchestrator(
        store=store,
        tmux_factory=lambda n: tmux,
        lark_factory=lambda c: FakeLarkCli(),
        data_dir=tmp_path,
    )

    # Restore — should re-start bot-p
    await orch.restore_from_disk()
    try:
        assert "bot-p" in orch.list_running()
        running = orch.get_running("bot-p")
        # Offset preserved
        assert running.state.jsonl_offset == 42
    finally:
        await orch.stop_all()


@pytest.mark.asyncio
async def test_restore_skips_bindings_with_missing_tmux(tmp_path):
    """If tmux session was killed during crash, restore should mark stale."""
    project_dir = tmp_path / "p"; project_dir.mkdir()
    cfg = BindingConfig(
        name="bot-p", project_dir=str(project_dir),
        tmux_session="claude-bot-p", feishu_app_id="cli_x",
        secret_ref="x", created_at=datetime.now(timezone.utc),
    )
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(cfg)
    (tmp_path / "running-bot-p").write_text("{}")

    tmux = FakeTmux()  # No session registered → stale

    orch = Orchestrator(
        store=store,
        tmux_factory=lambda n: tmux,
        lark_factory=lambda c: FakeLarkCli(),
        data_dir=tmp_path,
    )

    stale = await orch.restore_from_disk()
    assert "bot-p" not in orch.list_running()
    assert "bot-p" in stale
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/integration/test_state_recovery.py -xvs
```
Expected: `AttributeError` — `Orchestrator.restore_from_disk` doesn't exist.

- [ ] **Step 3: Implement `restore_from_disk`**

In `orchestrator.py`, add:
```python
    async def restore_from_disk(self) -> list[str]:
        """Re-attach bindings that were running when the daemon last shut down.

        Reads `running-<name>` marker files from data_dir. For each, if the
        tmux session is alive, calls `start_binding`. Returns the names of
        bindings that couldn't be restored (stale).
        """
        stale: list[str] = []
        for marker in self._data_dir.glob("running-*"):
            name = marker.name[len("running-"):]
            cfg = self._store.find_by_name(name)
            if cfg is None:
                marker.unlink(missing_ok=True)
                continue
            tmux = self._tmux_factory(name)
            if not tmux.has_session(cfg.tmux_session):
                stale.append(name)
                marker.unlink(missing_ok=True)
                continue
            data = {}
            try:
                data = json.loads(marker.read_text())
            except Exception:
                pass
            jsonl_path = Path(data.get("jsonl_path", "")) if data.get("jsonl_path") else None
            await self.start_binding(cwd=cfg.project_dir, jsonl_path=jsonl_path)
        return stale
```

Update `start_binding` to write the marker; `stop_binding` to remove it:
```python
        # in start_binding, after starting tasks:
        marker = self._data_dir / f"running-{cfg.name}"
        marker.write_text(json.dumps({"jsonl_path": str(jsonl_path)}))

        # in stop_binding, before returning:
        marker = self._data_dir / f"running-{cfg.name}"
        marker.unlink(missing_ok=True)
```

Update `__main__.py` to call `orchestrator.restore_from_disk()` after building the server.

- [ ] **Step 4: Verify**

```bash
pytest tests/integration/test_state_recovery.py -xvs
```
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/orchestrator.py feishu_bot_claude/__main__.py tests/integration/test_state_recovery.py
git commit -m "feat(daemon): restore running bindings from disk on startup"
```

---

### Task 9.2: 11232 backoff in LarkCli wrapper

**Files:**
- Modify: `feishu_bot_claude/daemon/feishu.py`
- Modify: `tests/unit/test_feishu_fake.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_feishu_fake.py`:
```python
@pytest.mark.asyncio
async def test_fake_simulates_11232_then_succeeds():
    """FakeLarkCli can be configured to fail with 11232 N times before succeeding."""
    lark = FakeLarkCli()
    lark.simulate_throttle(times=2)  # Fail twice, then succeed
    msg_id = await lark.send_text(chat_id="oc", text="hi")
    assert msg_id.startswith("om_fake_")
    # Should have logged the retry attempts
    assert lark.throttle_attempts == 2
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_feishu_fake.py::test_fake_simulates_11232_then_succeeds -xvs
```
Expected: `AttributeError: simulate_throttle`.

- [ ] **Step 3: Add backoff to FakeLarkCli + wrap RealLarkCli calls in backoff**

In `FakeLarkCli`:
```python
    def __init__(self) -> None:
        ...
        self._pending_throttle = 0
        self.throttle_attempts = 0

    def simulate_throttle(self, times: int) -> None:
        """Test helper: the next `times` calls fail with throttle, then succeed."""
        self._pending_throttle = times

    async def send_text(self, chat_id, text, idempotency_key=None) -> str:
        if self._pending_throttle > 0:
            self._pending_throttle -= 1
            self.throttle_attempts += 1
            raise FeishuThrottled("11232")
        # existing logic...
```

Add a `FeishuThrottled` exception class to `feishu.py`:
```python
class FeishuThrottled(RuntimeError):
    """Raised when Feishu returns error 11232 (rate limited)."""
```

Wrap `RealLarkCli.send_text`/`send_card`/`update_card` in a retry decorator using `BackoffPolicy` from `ratelimit.py`. Add a helper:
```python
async def with_backoff(operation, policy: BackoffPolicy):
    last_err = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await operation()
        except FeishuThrottled as e:
            last_err = e
            await asyncio.sleep(policy.delay_for(attempt))
    raise last_err
```

Use this around each `send_*` call in OutboundPipeline (wire via dependency injection in Phase 9.3 if needed).

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_feishu_fake.py -xvs
```
Expected: `7 passed` (existing 5 + new 2 — including the simulated throttle test).

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/feishu.py tests/unit/test_feishu_fake.py
git commit -m "feat(daemon): FeishuThrottled exception + backoff wrapper"
```

---

### Task 9.3: BindingConfig security opt-in fields

**Files:**
- Modify: `feishu_bot_claude/config/binding.py`
- Modify: `tests/unit/test_binding_config.py`
- Modify: `feishu_bot_claude/daemon/inbound.py`

- [ ] **Step 1: Write failing tests for new config fields**

Append to `tests/unit/test_binding_config.py`:
```python
def test_binding_config_accepts_security_fields():
    cfg = _example_config(
        allow_users=["ou_xxx", "ou_yyy"],
        require_confirm_patterns=[r"rm\s+-rf"],
        max_message_length=4000,
        session_idle_timeout_seconds=1800,
    )
    assert cfg.allow_users == ["ou_xxx", "ou_yyy"]
    assert cfg.require_confirm_patterns == [r"rm\s+-rf"]
    assert cfg.max_message_length == 4000


def test_binding_config_defaults_security_empty():
    cfg = _example_config()
    assert cfg.allow_users == []
    assert cfg.require_confirm_patterns == []
    assert cfg.max_message_length == 8000  # default
    assert cfg.session_idle_timeout_seconds == 0  # disabled
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_binding_config.py -xvs
```
Expected: `TypeError: BindingConfig.__init__() got unexpected keyword argument 'allow_users'`.

- [ ] **Step 3: Add fields to BindingConfig**

In `binding.py`, add to `BindingConfig`:
```python
    allow_users: list[str] = field(default_factory=list)
    require_confirm_patterns: list[str] = field(default_factory=list)
    max_message_length: int = 8000
    session_idle_timeout_seconds: int = 0  # 0 = disabled
```

Update `_binding_to_dict` and `_dict_to_binding` to include these fields.

In `InboundPipeline`, change `__init__` to accept a `BindingConfig` or these fields and use them.

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_binding_config.py tests/unit/test_binding_store.py tests/unit/test_inbound.py -xvs
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/config/binding.py feishu_bot_claude/daemon/inbound.py tests/unit/test_binding_config.py
git commit -m "feat(config): opt-in security fields (allow_users, max_message_length, idle_timeout)"
```

---

### Task 9.4: Confirmation card flow

**Files:**
- Modify: `feishu_bot_claude/daemon/inbound.py`
- Modify: `feishu_bot_claude/daemon/outbound.py`
- Create: `tests/unit/test_confirmation.py`

- [ ] **Step 1: Detect confirmation prompts in jsonl**

In `OutboundPipeline`, when an event with `subtype == "confirmation_prompt"` is observed:
1. Stop streaming the normal turn card
2. Send a special card with two action buttons (`confirm_yes`, `confirm_no`)
3. Store the prompt ID in `BindingRuntimeState`

In `InboundPipeline._handle_menu`, recognize `confirm_yes`/`confirm_no` event_keys and send-keys `"y\n"` / `"n\n"`.

- [ ] **Step 2: Write tests**

Create `tests/unit/test_confirmation.py`:
```python
"""Tests for /clear-style confirmation card flow."""

import pytest

from feishu_bot_claude.daemon.feishu import FakeLarkCli
from feishu_bot_claude.daemon.inbound import InboundPipeline
from feishu_bot_claude.daemon.tmux import FakeTmux


def _menu_event(event_key, sender_id="ou_user"):
    return {
        "type": "application.bot.menu_v6",
        "event": {
            "operator": {"operator_id": {"open_id": sender_id}},
            "event_key": event_key,
        },
    }


@pytest.mark.asyncio
async def test_confirm_yes_sends_y_to_tmux():
    tmux = FakeTmux()
    tmux.set_session("claude-foo", exists=True)
    lark = FakeLarkCli()
    lark.enqueue_event(_menu_event("confirm_yes"))

    pipeline = InboundPipeline(
        tmux_session="claude-foo",
        tmux=tmux,
        lark=lark,
        menu_command_map={"confirm_yes": "y", "confirm_no": "n"},
    )
    await pipeline.process_until_idle(max_events=1)
    assert tmux.calls[-1] == ("send_keys", {"session": "claude-foo", "keys": "y\n"})


@pytest.mark.asyncio
async def test_confirm_no_sends_n_to_tmux():
    tmux = FakeTmux()
    tmux.set_session("claude-foo", exists=True)
    lark = FakeLarkCli()
    lark.enqueue_event(_menu_event("confirm_no"))

    pipeline = InboundPipeline(
        tmux_session="claude-foo",
        tmux=tmux,
        lark=lark,
        menu_command_map={"confirm_yes": "y", "confirm_no": "n"},
    )
    await pipeline.process_until_idle(max_events=1)
    assert tmux.calls[-1][1]["keys"] == "n\n"
```

- [ ] **Step 3: Verify**

```bash
pytest tests/unit/test_confirmation.py -xvs
```
Expected: `2 passed`. (The inbound side already routes via `menu_command_map`, so these tests should pass with just the right map entries.)

- [ ] **Step 4: Implement outbound confirmation card rendering**

In `OutboundPipeline._handle_event`, detect `subtype == "confirmation_prompt"` events and emit a card with buttons `[("confirm_yes", "确认", "primary"), ("confirm_no", "取消", "default")]`. Add a unit test that asserts the card sent has the action element.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/inbound.py feishu_bot_claude/daemon/outbound.py tests/unit/test_confirmation.py
git commit -m "feat(daemon): confirmation card flow for /clear-style prompts"
```

---

### Task 9.5: chat_id resolution from first inbound message

**Files:**
- Modify: `feishu_bot_claude/daemon/inbound.py`
- Modify: `feishu_bot_claude/daemon/orchestrator.py`

- [ ] **Step 1: Refactor InboundPipeline to discover chat_id**

In `InboundPipeline`, capture the `chat_id` of the first text message and notify the orchestrator. Add a callback `on_chat_id_discovered`.

In `Orchestrator`, when started, register a callback that sets `OutboundPipeline._chat_id` to the discovered value, then triggers a first card send (so a "ready" status card is delivered).

Add tests: verify `OutboundPipeline._chat_id` is updated when InboundPipeline sees the first message.

- [ ] **Step 2: Commit**

```bash
git add feishu_bot_claude/daemon/inbound.py feishu_bot_claude/daemon/orchestrator.py tests/
git commit -m "feat(daemon): resolve chat_id from first inbound message"
```

---

### Task 9.6: Final README + Phase 9 summary

**Files:**
- Modify: `README.md`
- Create: `docs/phase-9-summary.md`

- [ ] **Step 1: Promote README to full project documentation**

Replace the placeholder `README.md` with full content (overview, features, install link, common workflows, troubleshooting, contributing).

- [ ] **Step 2: Phase 9 summary**

Create `docs/phase-9-summary.md` summarizing the hardening additions and noting any remaining v2 features.

- [ ] **Step 3: Final tag**

```bash
git add README.md docs/phase-9-summary.md
git commit -m "docs: phase 9 summary + full README"
git tag -a v1.0.0 -m "v1.0.0 — first usable release"
```

---

## v1.0.0 Complete

After Phase 9, the system meets all original requirements:
- Real-time bidirectional mirror ✓
- 1 project ↔ 1 bot strict isolation ✓
- Native Claude slash commands via menu + text intercept ✓
- TUI-side `/bot-*` commands work ✓
- China Feishu (open.feishu.cn) baseline ✓
- macOS Keychain credential safety ✓
- Daemon auto-restart + state recovery ✓
- Rate-limit hardening ✓
- Opt-in user whitelist + dangerous-command confirmation ✓

## v2 candidates

- Image / file message support (Vision input)
- Multiple users on one project / one bot
- Web management dashboard
- Linux GUI integration
- Cross-device binding sync via Drive
