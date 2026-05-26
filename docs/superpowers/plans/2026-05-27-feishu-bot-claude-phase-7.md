# feishu-bot-claude — Phase 7: Real OAuth + Menu Push Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the stub `bind` handler with a real implementation that drives `lark-cli` to create a new Feishu app via QR-scan, persists the credentials to macOS Keychain, and pushes a default menu config to the new bot. After Phase 7, `feishu-bot-claude bind foo-bot --cwd ~/proj` actually works end-to-end against real Feishu.

**Architecture:** New `daemon/auth.py` module wraps `lark-cli auth bot-new` (QR + polling). Output ASCII QR is streamed to CLI via the IPC protocol's `qrcode` event type. On success, credentials are written to Keychain via the existing `MacOSKeychainStore`. A separate `daemon/menu.py` module pushes the default menu JSON (defined in `feishu_bot_claude/menu_template.py`) via lark-cli OpenAPI, with file-write fallback if the API call fails.

**Prerequisite:** Phase 6 complete. lark-cli installed and globally authenticated as a Feishu developer (so it can create apps).

**Scope (Phase 7 deliverables):**
- `feishu_bot_claude/daemon/auth.py` — `bot_new` flow wrapper
- `feishu_bot_claude/daemon/menu.py` — menu push with fallback
- `feishu_bot_claude/menu_template.py` — the default 50-item menu JSON
- Real `handle_bind_with_orchestrator` replacing the stub
- Real `handle_unbind_with_orchestrator` revoking Keychain entry
- Manual smoke-test recipe in `docs/phase-7-smoke.md`

---

## Phase 7 Tasks

### Task 7.1: menu_template.py — default 50-button menu

**Files:**
- Create: `feishu_bot_claude/menu_template.py`
- Create: `tests/unit/test_menu_template.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_menu_template.py`:
```python
"""Tests for the default menu JSON template."""

from feishu_bot_claude.menu_template import DEFAULT_MENU, build_menu_json


def test_default_menu_has_5_top_level_groups():
    assert len(DEFAULT_MENU) == 5


def test_total_buttons_within_limit():
    """Floating-style menu supports 5 main × 10 sub = 50 buttons."""
    total = sum(len(group["children"]) for group in DEFAULT_MENU)
    assert total <= 50


def test_each_button_has_event_key_and_label():
    for group in DEFAULT_MENU:
        for btn in group["children"]:
            assert btn["event_key"]
            assert btn["label"]


def test_event_keys_unique():
    keys = []
    for group in DEFAULT_MENU:
        for btn in group["children"]:
            keys.append(btn["event_key"])
    assert len(keys) == len(set(keys)), "duplicate event_key in menu"


def test_build_menu_json_structure():
    out = build_menu_json()
    assert "menu_items" in out
    # Top-level items
    assert len(out["menu_items"]) == 5
    # First group has children with the right shape
    first_group = out["menu_items"][0]
    assert "label" in first_group
    assert "children" in first_group
    for child in first_group["children"]:
        assert child["action_type"] == "send_event"
        assert "event_key" in child
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_menu_template.py -xvs
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the template**

Create `feishu_bot_claude/menu_template.py`:
```python
"""Default Feishu bot menu — 5 groups × up to 10 buttons each."""

from __future__ import annotations

DEFAULT_MENU: list[dict] = [
    {
        "label": "会话",
        "children": [
            {"event_key": "cmd_clear", "label": "/clear"},
            {"event_key": "cmd_compact", "label": "/compact"},
            {"event_key": "cmd_resume", "label": "/resume"},
            {"event_key": "cmd_cost", "label": "/cost"},
            {"event_key": "cmd_status_repl", "label": "/status"},
            {"event_key": "cmd_quit", "label": "/quit"},
        ],
    },
    {
        "label": "配置",
        "children": [
            {"event_key": "cmd_model", "label": "/model"},
            {"event_key": "cmd_config", "label": "/config"},
            {"event_key": "cmd_init", "label": "/init"},
            {"event_key": "cmd_permissions", "label": "/permissions"},
            {"event_key": "cmd_login", "label": "/login"},
            {"event_key": "cmd_logout", "label": "/logout"},
        ],
    },
    {
        "label": "工具",
        "children": [
            {"event_key": "cmd_agents", "label": "/agents"},
            {"event_key": "cmd_mcp", "label": "/mcp"},
            {"event_key": "cmd_memory", "label": "/memory"},
            {"event_key": "cmd_hooks", "label": "/hooks"},
            {"event_key": "cmd_skills", "label": "/skills"},
            {"event_key": "cmd_add_dir", "label": "/add-dir"},
        ],
    },
    {
        "label": "信息",
        "children": [
            {"event_key": "cmd_help", "label": "/help"},
            {"event_key": "cmd_usage", "label": "/usage"},
            {"event_key": "cmd_doctor", "label": "/doctor"},
            {"event_key": "cmd_bug", "label": "/bug"},
        ],
    },
    {
        "label": "桥接",
        "children": [
            {"event_key": "bridge_pause", "label": "暂停镜像"},
            {"event_key": "bridge_resume", "label": "恢复镜像"},
            {"event_key": "bridge_reload", "label": "重载配置"},
            {"event_key": "bridge_show", "label": "查看绑定"},
        ],
    },
]


# Map event_key → tmux keystrokes for slash commands (consumed by InboundPipeline)
DEFAULT_MENU_COMMAND_MAP: dict[str, str] = {
    "cmd_clear": "/clear",
    "cmd_compact": "/compact",
    "cmd_resume": "/resume",
    "cmd_cost": "/cost",
    "cmd_status_repl": "/status",
    "cmd_quit": "/quit",
    "cmd_model": "/model",
    "cmd_config": "/config",
    "cmd_init": "/init",
    "cmd_permissions": "/permissions",
    "cmd_login": "/login",
    "cmd_logout": "/logout",
    "cmd_agents": "/agents",
    "cmd_mcp": "/mcp",
    "cmd_memory": "/memory",
    "cmd_hooks": "/hooks",
    "cmd_skills": "/skills",
    "cmd_add_dir": "/add-dir",
    "cmd_help": "/help",
    "cmd_usage": "/usage",
    "cmd_doctor": "/doctor",
    "cmd_bug": "/bug",
    # bridge_* keys are NOT in this map — they're handled internally, not injected
}


def build_menu_json() -> dict:
    """Return the menu config dict ready for Feishu open platform consumption."""
    menu_items = []
    for group in DEFAULT_MENU:
        children = [
            {
                "label": btn["label"],
                "action_type": "send_event",
                "event_key": btn["event_key"],
            }
            for btn in group["children"]
        ]
        menu_items.append({
            "label": group["label"],
            "children": children,
        })
    return {"menu_items": menu_items}
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_menu_template.py -xvs
```
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/menu_template.py tests/unit/test_menu_template.py
git commit -m "feat: default 50-button Feishu bot menu template"
```

---

### Task 7.2: auth.py — bot_new with QR streaming

**Files:**
- Create: `feishu_bot_claude/daemon/auth.py`
- Create: `tests/unit/test_auth.py`

- [ ] **Step 1: Write tests using a mock lark-cli output**

Create `tests/unit/test_auth.py`:
```python
"""Tests for auth.bot_new — drives lark-cli QR-scan, parses output, returns creds."""

import asyncio

import pytest

from feishu_bot_claude.daemon.auth import BotCreationResult, bot_new


class FakeAuthSubprocess:
    """Simulates `lark-cli auth bot-new` output."""

    def __init__(self, lines: list[str], returncode: int = 0):
        self._lines = list(lines)
        self.returncode = returncode

    async def readline_stream(self):
        for line in self._lines:
            await asyncio.sleep(0)  # yield to loop
            yield line + "\n"


@pytest.mark.asyncio
async def test_bot_new_parses_qr_then_success():
    """When subprocess emits a QR ASCII block then a credentials line, return parsed creds."""
    fake_output = [
        "[lark-cli] starting auth flow...",
        "===QR===",
        "█▀▀▀▀▀█ ▄ █▀▀▀▀▀█",  # ASCII QR fragment 1
        "█ ███ █  ▀ █ ███ █",
        "===QR===",
        "URL: https://open.feishu.cn/app/cli_xxx/qr",
        "[lark-cli] waiting for scan...",
        '{"app_id":"cli_xxx123","app_secret":"sec_yyy456","tenant_key":"t"}',
    ]
    fake = FakeAuthSubprocess(fake_output, returncode=0)

    progress_events: list[dict] = []

    async def on_progress(event):
        progress_events.append(event)

    result = await bot_new(
        runner=fake.readline_stream(),
        on_event=on_progress,
    )

    assert isinstance(result, BotCreationResult)
    assert result.app_id == "cli_xxx123"
    assert result.app_secret == "sec_yyy456"

    qr_events = [e for e in progress_events if e["type"] == "qrcode"]
    assert len(qr_events) == 1
    assert "█▀▀▀▀▀█" in qr_events[0]["ascii"]
    assert qr_events[0]["url"].startswith("https://open.feishu.cn")


@pytest.mark.asyncio
async def test_bot_new_no_creds_raises():
    """If lark-cli exits without emitting a creds line, raise."""
    fake = FakeAuthSubprocess(["[lark-cli] error: timeout"], returncode=1)

    with pytest.raises(RuntimeError, match="auth flow failed"):
        await bot_new(runner=fake.readline_stream(), on_event=lambda e: None)
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_auth.py -xvs
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `auth.py`**

Create `feishu_bot_claude/daemon/auth.py`:
```python
"""OAuth bot-new flow wrapper: parses lark-cli output, emits qrcode/progress events."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import AsyncIterator, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BotCreationResult:
    app_id: str
    app_secret: str
    tenant_key: str | None = None


_QR_DELIMITER = "===QR==="
_URL_PREFIX = "URL:"
_CREDS_PATTERN = re.compile(r'^\s*\{.*"app_id"\s*:\s*"([^"]+)".*"app_secret"\s*:\s*"([^"]+)"')


async def bot_new(
    runner: AsyncIterator[str],
    on_event: Callable[[dict], Awaitable[None] | None],
) -> BotCreationResult:
    """Drive the bot-new flow, parsing QR + URL + creds from a stream of output lines.

    `runner` is an async iterator yielding output lines. `on_event` is called
    with each `{type: "qrcode"|"progress"|"log", ...}` event for streaming back
    to the CLI via the IPC protocol.

    Returns the parsed credentials. Raises if the flow ends without creds.
    """
    in_qr = False
    qr_lines: list[str] = []
    qr_url: str = ""

    async def _emit(event: dict) -> None:
        result = on_event(event)
        if asyncio.iscoroutine(result):
            await result

    async for line in runner:
        line = line.rstrip("\n")

        if line.strip() == _QR_DELIMITER:
            if in_qr:
                # Closing the QR block — emit it
                ascii_qr = "\n".join(qr_lines)
                await _emit({"type": "qrcode", "ascii": ascii_qr, "url": qr_url})
                in_qr = False
                qr_lines = []
            else:
                in_qr = True
                qr_lines = []
            continue

        if in_qr:
            qr_lines.append(line)
            continue

        if line.startswith(_URL_PREFIX):
            qr_url = line[len(_URL_PREFIX):].strip()
            continue

        m = _CREDS_PATTERN.match(line)
        if m:
            payload = json.loads(line)
            return BotCreationResult(
                app_id=payload["app_id"],
                app_secret=payload["app_secret"],
                tenant_key=payload.get("tenant_key"),
            )

        # Other lines: forward as log events
        if line.strip():
            await _emit({"type": "log", "level": "info", "msg": line})

    raise RuntimeError("auth flow failed: subprocess ended without credentials")
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_auth.py -xvs
```
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/auth.py tests/unit/test_auth.py
git commit -m "feat(daemon): bot_new OAuth flow output parser"
```

---

### Task 7.3: menu.py — push menu with fallback to file

**Files:**
- Create: `feishu_bot_claude/daemon/menu.py`
- Create: `tests/unit/test_menu_push.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_menu_push.py`:
```python
"""Tests for menu push with file-write fallback."""

import json
from pathlib import Path

import pytest

from feishu_bot_claude.daemon.menu import MenuPushResult, push_menu_with_fallback


class FakeLarkMenu:
    """Test double — simulates lark-cli menu push API."""

    def __init__(self, succeed: bool = True):
        self.succeed = succeed
        self.calls: list[dict] = []

    async def push_menu(self, app_id: str, menu_json: dict) -> None:
        self.calls.append({"app_id": app_id, "menu": menu_json})
        if not self.succeed:
            raise RuntimeError("API endpoint not supported")


@pytest.mark.asyncio
async def test_push_succeeds_via_api(tmp_path):
    fake = FakeLarkMenu(succeed=True)
    result = await push_menu_with_fallback(
        lark_menu=fake,
        app_id="cli_xxx",
        menu_json={"menu_items": []},
        fallback_dir=tmp_path,
        binding_name="foo-bot",
    )
    assert result.method == "api"
    assert result.fallback_path is None
    assert fake.calls[0]["app_id"] == "cli_xxx"


@pytest.mark.asyncio
async def test_push_falls_back_to_file_on_api_failure(tmp_path):
    fake = FakeLarkMenu(succeed=False)
    result = await push_menu_with_fallback(
        lark_menu=fake,
        app_id="cli_xxx",
        menu_json={"menu_items": [{"label": "x"}]},
        fallback_dir=tmp_path,
        binding_name="foo-bot",
    )
    assert result.method == "file"
    assert result.fallback_path is not None
    assert result.fallback_path.exists()
    contents = json.loads(result.fallback_path.read_text())
    assert contents == {"menu_items": [{"label": "x"}]}
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_menu_push.py -xvs
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `menu.py`**

Create `feishu_bot_claude/daemon/menu.py`:
```python
"""Push bot menu config to Feishu, with file fallback if API unsupported."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

logger = logging.getLogger(__name__)


class MenuPusher(Protocol):
    async def push_menu(self, app_id: str, menu_json: dict) -> None: ...


@dataclass(frozen=True)
class MenuPushResult:
    method: str  # "api" | "file"
    fallback_path: Path | None = None


async def push_menu_with_fallback(
    lark_menu: MenuPusher,
    app_id: str,
    menu_json: dict,
    fallback_dir: Path,
    binding_name: str,
) -> MenuPushResult:
    """Try API push; on any error, write JSON to fallback file and return."""
    try:
        await lark_menu.push_menu(app_id=app_id, menu_json=menu_json)
        return MenuPushResult(method="api")
    except Exception as e:  # noqa: BLE001
        logger.warning("menu API push failed (%s); writing fallback file", e)
        fallback_dir.mkdir(parents=True, exist_ok=True)
        path = fallback_dir / f"{binding_name}.menu.json"
        path.write_text(json.dumps(menu_json, ensure_ascii=False, indent=2), encoding="utf-8")
        return MenuPushResult(method="file", fallback_path=path)
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_menu_push.py -xvs
```
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/menu.py tests/unit/test_menu_push.py
git commit -m "feat(daemon): menu push with file-write fallback"
```

---

### Task 7.4: Real `bind` / `unbind` handlers

**Files:**
- Modify: `feishu_bot_claude/daemon/handlers.py`
- Modify: `feishu_bot_claude/daemon/server.py`
- Modify: `tests/unit/test_handlers.py`

- [ ] **Step 1: Write tests with mock auth runner**

Append to `tests/unit/test_handlers.py`:
```python
from feishu_bot_claude.daemon.handlers import handle_bind_with_orchestrator, handle_unbind_with_orchestrator
from feishu_bot_claude.config.keychain import InMemoryKeychainStore


@pytest.mark.asyncio
async def test_handle_bind_creates_binding(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    keychain = InMemoryKeychainStore()

    async def fake_auth_runner():
        # Mimic lark-cli output
        for line in [
            "===QR===",
            "█",
            "===QR===",
            "URL: https://open.feishu.cn/app/foo/qr",
            '{"app_id":"cli_test","app_secret":"sec_test"}',
        ]:
            yield line + "\n"

    events = []
    async for ev in handle_bind_with_orchestrator(
        args={"name": "foo-bot", "cwd": str(tmp_path / "proj")},
        store=store,
        keychain=keychain,
        auth_runner_factory=lambda: fake_auth_runner(),
        menu_pusher=None,  # Tests skip menu push
        data_dir=tmp_path,
    ):
        events.append(ev)

    # Expect: qrcode event + result(ok=True)
    assert any(e.__class__.__name__ == "QRCodeEvent" for e in events)
    result = next(e for e in events if e.__class__.__name__ == "ResultEvent")
    assert result.ok is True
    assert "foo-bot" in result.data["name"]

    # Verify binding was stored
    binding = store.find_by_name("foo-bot")
    assert binding is not None
    assert binding.feishu_app_id == "cli_test"

    # Verify secret in keychain
    assert keychain.get(binding.secret_ref) == "sec_test"


@pytest.mark.asyncio
async def test_handle_unbind_removes_binding_and_secret(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    keychain = InMemoryKeychainStore()
    cfg = _example_config(name="foo-bot")
    store.add(cfg)
    keychain.put(cfg.secret_ref, "the-secret")

    events = []
    async for ev in handle_unbind_with_orchestrator(
        args={"name": "foo-bot"},
        store=store,
        keychain=keychain,
    ):
        events.append(ev)

    result = next(e for e in events if e.__class__.__name__ == "ResultEvent")
    assert result.ok is True
    assert store.find_by_name("foo-bot") is None
    assert keychain.get(cfg.secret_ref) is None
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_handlers.py -k "bind_with_orchestrator or unbind_with_orchestrator" -xvs
```
Expected: `ImportError`.

- [ ] **Step 3: Implement the handlers**

Append to `feishu_bot_claude/daemon/handlers.py`:
```python
from datetime import datetime, timezone

from feishu_bot_claude.config.binding import BindingConfig
from feishu_bot_claude.config.keychain import KeychainStore
from feishu_bot_claude.daemon.auth import bot_new
from feishu_bot_claude.daemon.menu import push_menu_with_fallback
from feishu_bot_claude.menu_template import build_menu_json


async def handle_bind_with_orchestrator(
    args: dict,
    store: BindingStore,
    keychain: KeychainStore,
    auth_runner_factory,
    menu_pusher,
    data_dir,
) -> AsyncIterator[ResponseEvent]:
    name = args.get("name", "")
    cwd = args.get("cwd", "")
    if not name or not cwd:
        yield ResultEvent(ok=False, data=None, error="bind requires name and cwd")
        yield DoneEvent()
        return

    if store.find_by_cwd(cwd) is not None:
        yield ResultEvent(ok=False, data=None, error=f"cwd already bound: {cwd}")
        yield DoneEvent()
        return
    if store.find_by_name(name) is not None:
        yield ResultEvent(ok=False, data=None, error=f"name already exists: {name}")
        yield DoneEvent()
        return

    # 1) Drive the OAuth flow, streaming events through to the caller
    streamed: list = []

    async def _capture(event: dict) -> None:
        streamed.append(event)

    yield LogEvent(level="info", msg="Starting Feishu OAuth flow (扫码新建 App)...")
    try:
        creds = await bot_new(runner=auth_runner_factory(), on_event=_capture)
    except RuntimeError as e:
        yield ResultEvent(ok=False, data=None, error=f"OAuth failed: {e}")
        yield DoneEvent()
        return

    # Replay the streamed events (qrcode, log, etc.) back to caller
    for ev in streamed:
        if ev["type"] == "qrcode":
            yield QRCodeEvent(ascii=ev["ascii"], url=ev.get("url", ""))
        elif ev["type"] == "log":
            yield LogEvent(level=ev.get("level", "info"), msg=ev["msg"])
        elif ev["type"] == "progress":
            yield ProgressEvent(value=ev.get("value", 0.0), msg=ev.get("msg", ""))

    yield LogEvent(level="info", msg=f"App created: {creds.app_id}")

    # 2) Store secret in Keychain
    secret_ref = f"feishu-bot-claude.{name}.app_secret"
    keychain.put(secret_ref, creds.app_secret)

    # 3) Create binding record
    binding = BindingConfig(
        name=name,
        project_dir=cwd,
        tmux_session=f"claude-{name}",
        feishu_app_id=creds.app_id,
        secret_ref=secret_ref,
        created_at=datetime.now(timezone.utc),
    )
    store.add(binding)

    # 4) Push menu (best-effort with fallback)
    if menu_pusher is not None:
        menu_json = build_menu_json()
        menu_result = await push_menu_with_fallback(
            lark_menu=menu_pusher,
            app_id=creds.app_id,
            menu_json=menu_json,
            fallback_dir=data_dir / "menus",
            binding_name=name,
        )
        if menu_result.method == "api":
            yield LogEvent(level="info", msg="Menu pushed via lark-cli API.")
        else:
            yield LogEvent(level="warn", msg=f"Menu API unsupported; JSON written to {menu_result.fallback_path}. Paste it into the Feishu open platform.")

    yield ResultEvent(
        ok=True,
        data={"name": name, "app_id": creds.app_id, "next": "/bot-start"},
        error=None,
    )
    yield DoneEvent()


async def handle_unbind_with_orchestrator(
    args: dict,
    store: BindingStore,
    keychain: KeychainStore,
) -> AsyncIterator[ResponseEvent]:
    name = args.get("name", "")
    binding = store.find_by_name(name)
    if binding is None:
        yield ResultEvent(ok=False, data=None, error=f"no binding named {name!r}")
        yield DoneEvent()
        return
    store.remove(name)
    keychain.delete(binding.secret_ref)
    yield ResultEvent(ok=True, data={"removed": name}, error=None)
    yield DoneEvent()
```

Update `feishu_bot_claude/daemon/server.py` `_build_dispatcher` to accept the keychain + auth_runner_factory + menu_pusher + data_dir and wire up `bind` / `unbind`. Pass them through from `serve()` and `__main__.py`.

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_handlers.py -xvs
```
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/daemon/handlers.py feishu_bot_claude/daemon/server.py tests/unit/test_handlers.py
git commit -m "feat(daemon): real bind/unbind handlers with OAuth + Keychain + menu push"
```

---

### Task 7.5: Wire RealLarkCli `auth bot-new` subprocess

**Files:**
- Modify: `feishu_bot_claude/daemon/feishu.py`
- Modify: `feishu_bot_claude/__main__.py`

- [ ] **Step 1: Add `auth_bot_new_stream` to LarkCli interface**

In `feishu_bot_claude/daemon/feishu.py`, append to the `LarkCli` ABC:
```python
    @abstractmethod
    def auth_bot_new_stream(self) -> AsyncIterator[str]:
        """Spawn `lark-cli auth bot-new` and stream its stdout line-by-line."""
```

Implement in `RealLarkCli`:
```python
    async def auth_bot_new_stream(self) -> AsyncIterator[str]:
        proc = await asyncio.create_subprocess_exec(
            self._binary, "auth", "bot-new",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # interleave stderr for parsing
            env=os.environ.copy(),
        )
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                yield line.decode("utf-8", errors="replace")
        finally:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=10.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
```

Implement a `push_menu` method on `RealLarkCli` using a likely lark-cli command (verify exact subcommand against installed lark-cli version; if not supported, raise — the `push_menu_with_fallback` wrapper handles the file fallback):
```python
    async def push_menu(self, app_id: str, menu_json: dict) -> None:
        """Push the menu config to the Feishu open platform.

        Uses `lark-cli apps menu update` if available; raises RuntimeError if
        the subcommand doesn't exist (caller falls back to file).
        """
        args = [
            "apps", "menu", "update",
            "--app-id", app_id,
            "--menu", json.dumps(menu_json, ensure_ascii=False),
        ]
        out, code = await self._run_raw(args, timeout=30.0)
        if code != 0:
            raise RuntimeError(f"lark-cli menu update failed (exit {code}): {out!r}")
```

In `FakeLarkCli`, add a matching `auth_bot_new_stream` that yields a queued list of strings (for handler tests).

- [ ] **Step 2: Update `__main__.py`**

Pass `keychain`, `lark` (for auth), `data_dir` through to `serve()`. Real wiring:
```python
from feishu_bot_claude.config.keychain import MacOSKeychainStore
from feishu_bot_claude.daemon.feishu import RealLarkCli

keychain = MacOSKeychainStore()
real_lark = RealLarkCli()

server = await serve(
    socket_path=socket_path,
    bindings_path=bindings_path,
    orchestrator=orchestrator,
    keychain=keychain,
    auth_runner_factory=lambda: real_lark.auth_bot_new_stream(),
    menu_pusher=real_lark,
    data_dir=data_dir,
)
```

- [ ] **Step 3: Verify**

```bash
pytest -xvs
```
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add feishu_bot_claude/daemon/feishu.py feishu_bot_claude/__main__.py
git commit -m "feat(daemon): wire RealLarkCli.auth_bot_new_stream and push_menu into daemon"
```

---

### Task 7.6: Manual smoke-test recipe + Phase 7 summary

**Files:**
- Create: `docs/phase-7-smoke.md`
- Create: `docs/phase-7-summary.md`

- [ ] **Step 1: Write smoke-test recipe**

Create `docs/phase-7-smoke.md`:
```markdown
# Phase 7 Smoke Test Recipe

Requires:
- `lark-cli` installed and globally authenticated (`lark-cli auth login` once)
- macOS for Keychain
- A real Feishu account

## Steps

1. Start daemon:
   ```bash
   python -m feishu_bot_claude daemon &
   ```

2. Create a sandbox project dir:
   ```bash
   mkdir -p ~/tmp/smoketest && cd ~/tmp/smoketest
   ```

3. Trigger `bind`:
   ```bash
   feishu-bot-claude bind smoketest-bot --cwd "$PWD"
   ```
   Expected: terminal shows ASCII QR + URL. Scan with Feishu mobile.

4. After scan, daemon prints `App created: cli_xxx` and writes `~/.feishu-bot-claude/bindings.toml` containing the new binding.

5. Verify Keychain:
   ```bash
   security find-generic-password -s feishu-bot-claude -a "smoketest-bot.app_secret" -w
   ```
   Should print the secret.

6. Verify list:
   ```bash
   feishu-bot-claude list
   ```
   Should show smoketest-bot with the cwd.

7. Clean up:
   ```bash
   feishu-bot-claude unbind smoketest-bot
   ```
   The Feishu app remains on the open platform (delete manually).
```

- [ ] **Step 2: Write summary**

Create `docs/phase-7-summary.md`:
```markdown
# Phase 7 Summary

**Date completed:** <fill in>

## What's in place

- `menu_template.py` — 50-button default menu + `event_key → /command` map
- `daemon/auth.py` — `bot_new` stream parser (QR + URL + creds)
- `daemon/menu.py` — `push_menu_with_fallback` (file-write on API failure)
- `daemon/feishu.py` — `RealLarkCli.auth_bot_new_stream` + `push_menu`
- Real `bind`/`unbind` handlers replacing stubs
- Daemon wires Keychain, lark-cli, menu pusher at startup

## Verification

- Unit tests: `pytest tests/unit/test_menu_template.py tests/unit/test_auth.py tests/unit/test_menu_push.py -v`
- Manual smoke: see `phase-7-smoke.md`

## What's intentionally missing

- `lark-cli apps menu update` may not exist as exact subcommand — file fallback handles this
- chat_id is still hardcoded/empty in orchestrator wiring; Phase 5 cards go to a TBD chat. The bot is added to a 1:1 chat with the user automatically when they scan; chat_id resolution happens on first Feishu message. (TODO: capture chat_id in InboundPipeline first event and feed it back to OutboundPipeline.)

## Next phase preview

Phase 8 — Distribution:
- `.claude/commands/bot-*.md` (6 markdown files)
- `scripts/install-commands.sh`
- `scripts/launchd.plist` + `scripts/systemd.service`
- `setup.sh` (full)
```

- [ ] **Step 3: Commit + tag**

```bash
git add docs/phase-7-smoke.md docs/phase-7-summary.md
git commit -m "docs: phase 7 summary + smoke test recipe"
git tag -a phase-7-complete -m "Phase 7: OAuth + menu push complete"
```

---

## Phase 7 Done. Next: Phase 8 — Distribution
