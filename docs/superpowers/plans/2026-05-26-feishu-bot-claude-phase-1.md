# feishu-bot-claude — Phase 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the project skeleton plus the foundational library layer (IPC protocol types + binding config storage with secure secret handling). After Phase 1, no daemon or CLI runs yet, but the `feishu_bot_claude` Python package is importable, fully unit-tested, and the data layer is solid enough to build the rest on.

**Architecture:** Pure library layer — no I/O except TOML files and macOS Keychain via the `security` command. Three modules with strict responsibilities: `proto.py` (typed IPC messages), `config/binding.py` (BindingConfig dataclass + TOML roundtrip), `config/keychain.py` (KeychainStore wrapper). All public API surfaces tested with golden behavior.

**Tech Stack:** Python 3.11+, dataclasses, `tomllib` (read, stdlib) + `tomli-w` (write), pytest, pytest-asyncio, `keyring` *not used* (subprocess to `security` instead — fewer deps, simpler audit).

**Companion spec:** `docs/superpowers/specs/2026-05-26-feishu-bot-claude-design.md`

**Scope (Phase 1 deliverables):**
- Project scaffolding (`pyproject.toml`, `.gitignore`, README placeholder)
- Git repo initialized
- pytest test infrastructure
- `feishu_bot_claude/proto.py` — typed request/response dataclasses + validation
- `feishu_bot_claude/config/binding.py` — `BindingConfig`, `BindingStore`, atomic TOML I/O
- `feishu_bot_claude/config/keychain.py` — `KeychainStore` with macOS `security` backend + in-memory fake for tests
- Concurrent-write safety on `bindings.toml`

**Out of scope (later phases):**
- daemon, CLI, anything that opens sockets or runs subprocesses for the product
- tmux wrappers
- lark-cli wrappers
- card rendering
- slash commands
- setup.sh

---

## File Structure (Phase 1)

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata + deps + tool config |
| `.gitignore` | Standard Python ignores |
| `README.md` | Placeholder + link to spec |
| `feishu_bot_claude/__init__.py` | Public package surface |
| `feishu_bot_claude/proto.py` | IPC message dataclasses (Request, Response, all event types) |
| `feishu_bot_claude/config/__init__.py` | Re-exports `BindingConfig`, `BindingStore`, `KeychainStore` |
| `feishu_bot_claude/config/binding.py` | `BindingConfig` dataclass + `BindingStore` (TOML I/O, flock, lookup) |
| `feishu_bot_claude/config/keychain.py` | `KeychainStore` ABC + `MacOSKeychainStore` + `InMemoryKeychainStore` |
| `tests/conftest.py` | Shared pytest fixtures (tmp paths, fake keychain) |
| `tests/unit/test_proto.py` | proto serialization + validation tests |
| `tests/unit/test_binding_config.py` | BindingConfig dataclass tests |
| `tests/unit/test_binding_store.py` | BindingStore TOML roundtrip + concurrent access |
| `tests/unit/test_keychain.py` | KeychainStore behavior tests (using fake backend) |
| `tests/integration/test_macos_keychain.py` | Real macOS keychain integration test (marked `@skip_if_not_macos`) |

**Decomposition rationale:** Each test file maps to exactly one module; modules are <300 lines; `proto.py` and `config/` have zero shared imports so they're independently testable.

---

## Phase 1 Tasks

Tasks run in order. Each task starts with the failing test, then minimal implementation, then commit. Run `pytest -xvs` after each implementation step to verify.

---

### Task 1.1: Initialize git repo

**Files:**
- Create: `.gitignore`
- Create: `README.md`

- [ ] **Step 1: Initialize the repo**

Run:
```bash
cd ~/project/feishu-bot-claude
git init
```
Expected: `Initialized empty Git repository in .../feishu-bot-claude/.git/`

- [ ] **Step 2: Create `.gitignore`**

Write the file `~/project/feishu-bot-claude/.gitignore`:
```
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.venv/
.coverage
htmlcov/
dist/
build/
.DS_Store
~/.feishu-bot-claude/
vendor/lark-cli/
```

- [ ] **Step 3: Create placeholder `README.md`**

Write `~/project/feishu-bot-claude/README.md`:
```markdown
# feishu-bot-claude

Bridges local Claude Code TUI sessions to dedicated Feishu (Lark) bots — one bot per project, full bidirectional mirror with native slash command support.

See `docs/superpowers/specs/2026-05-26-feishu-bot-claude-design.md` for full design.

Phase 1 status: scaffolding + config layer. Daemon and CLI come in later phases.
```

- [ ] **Step 4: First commit**

Run:
```bash
git add .gitignore README.md docs/
git commit -m "chore: initialize repo with gitignore, README, and design spec"
```
Expected: commit succeeds, lists `.gitignore`, `README.md`, and any docs already present.

---

### Task 1.2: pyproject.toml + dependencies

**Files:**
- Create: `pyproject.toml`

- [ ] **Step 1: Write `pyproject.toml`**

Write `~/project/feishu-bot-claude/pyproject.toml`:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "feishu-bot-claude"
version = "0.1.0"
description = "Bridge local Claude Code TUI to dedicated Feishu bots"
requires-python = ">=3.11"
dependencies = [
    "tomli-w >= 1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest >= 8.0.0",
    "pytest-asyncio >= 0.23.0",
    "pytest-cov >= 5.0.0",
]

[tool.hatch.build.targets.wheel]
packages = ["feishu_bot_claude"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-ra -q"

[tool.coverage.run]
source = ["feishu_bot_claude"]
branch = true
```

- [ ] **Step 2: Create venv and install in editable mode**

Run:
```bash
cd ~/project/feishu-bot-claude
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```
Expected: `Successfully installed feishu-bot-claude-0.1.0 pytest ... tomli-w ...`

- [ ] **Step 3: Verify install**

Run:
```bash
python -c "import feishu_bot_claude; print(feishu_bot_claude.__name__)"
```
Expected: failure with `ModuleNotFoundError` — package directory doesn't exist yet. This confirms the install picked up the project but the module is not yet created.

(If unexpectedly succeeds, that's because a stale install exists — clean with `pip uninstall feishu-bot-claude -y`.)

- [ ] **Step 4: Commit**

Run:
```bash
git add pyproject.toml
git commit -m "chore: add pyproject.toml with dev dependencies"
```

---

### Task 1.3: Package skeleton + smoke test

**Files:**
- Create: `feishu_bot_claude/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/test_smoke.py`

- [ ] **Step 1: Write the failing smoke test**

Create `tests/unit/test_smoke.py`:
```python
"""Smoke test: package can be imported and exposes version."""

import feishu_bot_claude


def test_package_exposes_version():
    assert feishu_bot_claude.__version__ == "0.1.0"
```

- [ ] **Step 2: Run and verify it fails**

Run:
```bash
pytest tests/unit/test_smoke.py -xvs
```
Expected: `ModuleNotFoundError: No module named 'feishu_bot_claude'`

- [ ] **Step 3: Create package skeleton**

Create `feishu_bot_claude/__init__.py`:
```python
"""feishu-bot-claude — Feishu bot bridge for Claude Code."""

__version__ = "0.1.0"
```

Create empty `tests/__init__.py` and `tests/unit/__init__.py` (touch).

Create `tests/conftest.py`:
```python
"""Shared pytest fixtures."""

import pytest
```

- [ ] **Step 4: Run and verify it passes**

Run:
```bash
pytest tests/unit/test_smoke.py -xvs
```
Expected: `1 passed`

- [ ] **Step 5: Commit**

Run:
```bash
git add feishu_bot_claude/__init__.py tests/
git commit -m "feat: package skeleton with version smoke test"
```

---

### Task 1.4: proto.py — Request type

**Files:**
- Create: `feishu_bot_claude/proto.py`
- Modify: `tests/unit/test_proto.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_proto.py`:
```python
"""Tests for IPC protocol types."""

import json

import pytest

from feishu_bot_claude.proto import Request


def test_request_serializes_to_json_line():
    """A Request can be serialized to a single-line JSON string."""
    req = Request(op="bind", args={"name": "foo-bot", "cwd": "/x/y"}, request_id="r-1")
    line = req.to_json_line()
    assert "\n" not in line
    parsed = json.loads(line)
    assert parsed == {
        "op": "bind",
        "args": {"name": "foo-bot", "cwd": "/x/y"},
        "request_id": "r-1",
    }


def test_request_parses_from_json_line():
    """A JSON line round-trips into an equivalent Request."""
    line = '{"op": "list", "args": {}, "request_id": "r-2"}'
    req = Request.from_json_line(line)
    assert req.op == "list"
    assert req.args == {}
    assert req.request_id == "r-2"


def test_request_roundtrip():
    """Serializing then parsing produces an equal Request."""
    original = Request(op="start", args={"cwd": "/p"}, request_id="r-3")
    restored = Request.from_json_line(original.to_json_line())
    assert restored == original
```

- [ ] **Step 2: Run and verify it fails**

Run:
```bash
pytest tests/unit/test_proto.py -xvs
```
Expected: `ImportError: cannot import name 'Request' from 'feishu_bot_claude.proto'`

- [ ] **Step 3: Implement `Request`**

Create `feishu_bot_claude/proto.py`:
```python
"""IPC protocol types — request/response dataclasses with JSON roundtrip."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Request:
    """A single CLI → daemon request line."""

    op: str
    args: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""

    def to_json_line(self) -> str:
        """Serialize to a single line of JSON (no trailing newline)."""
        return json.dumps(asdict(self), separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json_line(cls, line: str) -> Request:
        """Parse one JSON line into a Request."""
        data = json.loads(line)
        return cls(
            op=data["op"],
            args=data.get("args", {}),
            request_id=data.get("request_id", ""),
        )
```

- [ ] **Step 4: Run and verify it passes**

Run:
```bash
pytest tests/unit/test_proto.py -xvs
```
Expected: `3 passed`

- [ ] **Step 5: Commit**

Run:
```bash
git add feishu_bot_claude/proto.py tests/unit/test_proto.py
git commit -m "feat(proto): add Request dataclass with JSON line roundtrip"
```

---

### Task 1.5: proto.py — Response event types

**Files:**
- Modify: `feishu_bot_claude/proto.py`
- Modify: `tests/unit/test_proto.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_proto.py`:
```python
from feishu_bot_claude.proto import (
    LogEvent,
    QRCodeEvent,
    ProgressEvent,
    ResultEvent,
    DoneEvent,
    parse_response_line,
)


def test_log_event_roundtrip():
    e = LogEvent(level="info", msg="hello")
    line = e.to_json_line()
    parsed = parse_response_line(line)
    assert parsed == e


def test_qrcode_event_roundtrip():
    e = QRCodeEvent(ascii="█▀█", url="https://example/qr")
    parsed = parse_response_line(e.to_json_line())
    assert parsed == e


def test_progress_event_roundtrip():
    e = ProgressEvent(value=0.42, msg="working")
    parsed = parse_response_line(e.to_json_line())
    assert parsed == e


def test_result_event_roundtrip_ok():
    e = ResultEvent(ok=True, data={"x": 1}, error=None)
    parsed = parse_response_line(e.to_json_line())
    assert parsed == e


def test_result_event_roundtrip_err():
    e = ResultEvent(ok=False, data=None, error="something failed")
    parsed = parse_response_line(e.to_json_line())
    assert parsed == e


def test_done_event_roundtrip():
    e = DoneEvent()
    parsed = parse_response_line(e.to_json_line())
    assert parsed == e


def test_parse_unknown_event_type_raises():
    with pytest.raises(ValueError, match="unknown event type"):
        parse_response_line('{"type": "alien", "foo": 1}')
```

- [ ] **Step 2: Run and verify it fails**

Run:
```bash
pytest tests/unit/test_proto.py -xvs
```
Expected: `ImportError` on the new event types.

- [ ] **Step 3: Implement event types and parser**

Replace `feishu_bot_claude/proto.py` with:
```python
"""IPC protocol types — request/response dataclasses with JSON roundtrip."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Union


@dataclass(frozen=True)
class Request:
    op: str
    args: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def from_json_line(cls, line: str) -> Request:
        data = json.loads(line)
        return cls(
            op=data["op"],
            args=data.get("args", {}),
            request_id=data.get("request_id", ""),
        )


@dataclass(frozen=True)
class LogEvent:
    level: Literal["debug", "info", "warn", "error"]
    msg: str
    type: Literal["log"] = "log"

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class QRCodeEvent:
    ascii: str
    url: str
    type: Literal["qrcode"] = "qrcode"

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class ProgressEvent:
    value: float
    msg: str
    type: Literal["progress"] = "progress"

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class ResultEvent:
    ok: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    type: Literal["result"] = "result"

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), ensure_ascii=False)


@dataclass(frozen=True)
class DoneEvent:
    type: Literal["done"] = "done"

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), ensure_ascii=False)


ResponseEvent = Union[LogEvent, QRCodeEvent, ProgressEvent, ResultEvent, DoneEvent]

_EVENT_TYPES: dict[str, type] = {
    "log": LogEvent,
    "qrcode": QRCodeEvent,
    "progress": ProgressEvent,
    "result": ResultEvent,
    "done": DoneEvent,
}


def parse_response_line(line: str) -> ResponseEvent:
    """Parse one JSON line into the appropriate event dataclass."""
    data = json.loads(line)
    type_name = data.get("type")
    cls = _EVENT_TYPES.get(type_name)
    if cls is None:
        raise ValueError(f"unknown event type: {type_name!r}")
    payload = {k: v for k, v in data.items() if k != "type"}
    return cls(**payload)
```

- [ ] **Step 4: Run and verify all proto tests pass**

Run:
```bash
pytest tests/unit/test_proto.py -xvs
```
Expected: `10 passed` (3 from Task 1.4 + 7 new).

- [ ] **Step 5: Commit**

Run:
```bash
git add feishu_bot_claude/proto.py tests/unit/test_proto.py
git commit -m "feat(proto): add response event types and parser"
```

---

### Task 1.6: proto.py — Request validation

**Files:**
- Modify: `feishu_bot_claude/proto.py`
- Modify: `tests/unit/test_proto.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_proto.py`:
```python
def test_request_rejects_unknown_op():
    with pytest.raises(ValueError, match="unknown op"):
        Request(op="not-a-real-op", args={}).validate()


def test_request_accepts_known_ops():
    for op in ["bind", "unbind", "start", "stop", "list", "config", "status", "shell"]:
        Request(op=op, args={}).validate()  # no raise


def test_request_bind_requires_name_and_cwd():
    with pytest.raises(ValueError, match="bind requires"):
        Request(op="bind", args={"name": "foo"}).validate()
    with pytest.raises(ValueError, match="bind requires"):
        Request(op="bind", args={"cwd": "/x"}).validate()
    Request(op="bind", args={"name": "foo", "cwd": "/x"}).validate()  # ok


def test_request_start_requires_cwd():
    with pytest.raises(ValueError, match="start requires"):
        Request(op="start", args={}).validate()
    Request(op="start", args={"cwd": "/x"}).validate()  # ok
```

- [ ] **Step 2: Run and verify it fails**

Run:
```bash
pytest tests/unit/test_proto.py::test_request_rejects_unknown_op -xvs
```
Expected: `AttributeError: 'Request' object has no attribute 'validate'`

- [ ] **Step 3: Implement validation**

Add to `feishu_bot_claude/proto.py` (inside the `Request` class, after `from_json_line`):
```python
    def validate(self) -> None:
        """Raise ValueError if the request is malformed."""
        known_ops = {"bind", "unbind", "start", "stop", "list", "config", "status", "shell"}
        if self.op not in known_ops:
            raise ValueError(f"unknown op: {self.op!r} (known: {sorted(known_ops)})")
        required = {
            "bind": ("name", "cwd"),
            "unbind": ("name",),
            "start": ("cwd",),
            "stop": ("cwd",),
            "config": ("cwd",),
            "status": (),
            "list": (),
            "shell": ("cwd",),
        }
        for key in required[self.op]:
            if key not in self.args:
                raise ValueError(f"{self.op} requires arg {key!r}")
```

- [ ] **Step 4: Run and verify all proto tests pass**

Run:
```bash
pytest tests/unit/test_proto.py -xvs
```
Expected: `14 passed`.

- [ ] **Step 5: Commit**

Run:
```bash
git add feishu_bot_claude/proto.py tests/unit/test_proto.py
git commit -m "feat(proto): validate request op and required args"
```

---

### Task 1.7: config/keychain.py — Abstract interface + in-memory fake

**Files:**
- Create: `feishu_bot_claude/config/__init__.py`
- Create: `feishu_bot_claude/config/keychain.py`
- Create: `tests/unit/test_keychain.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_keychain.py`:
```python
"""Tests for KeychainStore abstraction with in-memory fake."""

import pytest

from feishu_bot_claude.config.keychain import InMemoryKeychainStore, KeychainStore


def test_in_memory_store_put_and_get():
    store: KeychainStore = InMemoryKeychainStore()
    store.put("svc.alpha", "secret-1")
    assert store.get("svc.alpha") == "secret-1"


def test_in_memory_store_get_missing_returns_none():
    store = InMemoryKeychainStore()
    assert store.get("nonexistent") is None


def test_in_memory_store_overwrites():
    store = InMemoryKeychainStore()
    store.put("svc.alpha", "v1")
    store.put("svc.alpha", "v2")
    assert store.get("svc.alpha") == "v2"


def test_in_memory_store_delete():
    store = InMemoryKeychainStore()
    store.put("svc.alpha", "secret-1")
    store.delete("svc.alpha")
    assert store.get("svc.alpha") is None


def test_in_memory_store_delete_missing_is_noop():
    store = InMemoryKeychainStore()
    store.delete("nonexistent")  # no raise
```

- [ ] **Step 2: Run and verify it fails**

Run:
```bash
pytest tests/unit/test_keychain.py -xvs
```
Expected: `ModuleNotFoundError: No module named 'feishu_bot_claude.config'`

- [ ] **Step 3: Implement the interface and fake**

Create `feishu_bot_claude/config/__init__.py`:
```python
"""Configuration storage layer."""

from feishu_bot_claude.config.keychain import (
    InMemoryKeychainStore,
    KeychainStore,
    MacOSKeychainStore,
)

__all__ = ["KeychainStore", "InMemoryKeychainStore", "MacOSKeychainStore"]
```

Create `feishu_bot_claude/config/keychain.py`:
```python
"""Secret storage abstraction with macOS Keychain backend."""

from __future__ import annotations

from abc import ABC, abstractmethod


class KeychainStore(ABC):
    """Abstract secret store. Backed by macOS Keychain in production."""

    @abstractmethod
    def put(self, key: str, secret: str) -> None:
        """Store or overwrite a secret under `key`."""

    @abstractmethod
    def get(self, key: str) -> str | None:
        """Return the secret for `key`, or None if missing."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete the secret for `key`. No-op if missing."""


class InMemoryKeychainStore(KeychainStore):
    """In-memory store for tests. Not persistent, not secure."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def put(self, key: str, secret: str) -> None:
        self._data[key] = secret

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


class MacOSKeychainStore(KeychainStore):
    """macOS Keychain backend via the `security` command."""

    # Implemented in Task 1.8 — placeholder raises so partial use fails loudly.
    def put(self, key: str, secret: str) -> None:
        raise NotImplementedError("MacOSKeychainStore implemented in Task 1.8")

    def get(self, key: str) -> str | None:
        raise NotImplementedError("MacOSKeychainStore implemented in Task 1.8")

    def delete(self, key: str) -> None:
        raise NotImplementedError("MacOSKeychainStore implemented in Task 1.8")
```

- [ ] **Step 4: Run and verify tests pass**

Run:
```bash
pytest tests/unit/test_keychain.py -xvs
```
Expected: `5 passed`.

- [ ] **Step 5: Commit**

Run:
```bash
git add feishu_bot_claude/config/ tests/unit/test_keychain.py
git commit -m "feat(config): add KeychainStore interface and in-memory fake"
```

---

### Task 1.8: config/keychain.py — macOS Keychain backend

**Files:**
- Modify: `feishu_bot_claude/config/keychain.py`
- Modify: `tests/unit/test_keychain.py`

- [ ] **Step 1: Write the failing tests with subprocess mock**

Append to `tests/unit/test_keychain.py`:
```python
import subprocess
from unittest.mock import patch

from feishu_bot_claude.config.keychain import MacOSKeychainStore


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


@patch("feishu_bot_claude.config.keychain.subprocess.run")
def test_macos_keychain_put_calls_security_add(mock_run):
    mock_run.return_value = _completed(0)
    store = MacOSKeychainStore(service_prefix="feishu-bot-claude")
    store.put("foo-bot.app_secret", "s3cret")
    # security add-generic-password -U -a <key> -s <service> -w <secret>
    call_args = mock_run.call_args[0][0]
    assert call_args[0:2] == ["security", "add-generic-password"]
    assert "-U" in call_args  # update-if-exists
    assert "-a" in call_args and "foo-bot.app_secret" in call_args
    assert "-s" in call_args and "feishu-bot-claude" in call_args
    assert "-w" in call_args and "s3cret" in call_args


@patch("feishu_bot_claude.config.keychain.subprocess.run")
def test_macos_keychain_get_returns_password_on_success(mock_run):
    mock_run.return_value = _completed(0, stdout="s3cret\n")
    store = MacOSKeychainStore(service_prefix="feishu-bot-claude")
    assert store.get("foo-bot.app_secret") == "s3cret"
    call_args = mock_run.call_args[0][0]
    assert call_args[0:2] == ["security", "find-generic-password"]
    assert "-w" in call_args  # password-only output


@patch("feishu_bot_claude.config.keychain.subprocess.run")
def test_macos_keychain_get_returns_none_when_missing(mock_run):
    # `security find-generic-password` returns 44 when the item is not found
    mock_run.return_value = _completed(44, stderr="security: SecKeychainSearchCopyNext: ...")
    store = MacOSKeychainStore(service_prefix="feishu-bot-claude")
    assert store.get("missing") is None


@patch("feishu_bot_claude.config.keychain.subprocess.run")
def test_macos_keychain_get_raises_on_other_errors(mock_run):
    mock_run.return_value = _completed(1, stderr="permission denied")
    store = MacOSKeychainStore(service_prefix="feishu-bot-claude")
    with pytest.raises(RuntimeError, match="keychain get failed"):
        store.get("foo")


@patch("feishu_bot_claude.config.keychain.subprocess.run")
def test_macos_keychain_delete_succeeds(mock_run):
    mock_run.return_value = _completed(0)
    store = MacOSKeychainStore(service_prefix="feishu-bot-claude")
    store.delete("foo-bot.app_secret")
    call_args = mock_run.call_args[0][0]
    assert call_args[0:2] == ["security", "delete-generic-password"]


@patch("feishu_bot_claude.config.keychain.subprocess.run")
def test_macos_keychain_delete_missing_is_noop(mock_run):
    mock_run.return_value = _completed(44)  # not found — fine
    store = MacOSKeychainStore(service_prefix="feishu-bot-claude")
    store.delete("missing")  # no raise
```

- [ ] **Step 2: Run and verify it fails**

Run:
```bash
pytest tests/unit/test_keychain.py -xvs
```
Expected: `NotImplementedError` on the new tests.

- [ ] **Step 3: Implement the real macOS backend**

Add `import subprocess` at the top of `feishu_bot_claude/config/keychain.py` (with the other imports, before the class definitions), then replace the entire `MacOSKeychainStore` class with the implementation below:
```python
class MacOSKeychainStore(KeychainStore):
    """macOS Keychain backend via the `security` command.

    Each item is stored as a generic password where:
      - `-s` (service) is the shared `service_prefix`
      - `-a` (account) is the per-binding key
    """

    _NOT_FOUND_RETURNCODE = 44  # `security` exit code for "item not found"

    def __init__(self, service_prefix: str = "feishu-bot-claude") -> None:
        self._service = service_prefix

    def put(self, key: str, secret: str) -> None:
        result = subprocess.run(
            [
                "security", "add-generic-password",
                "-U",                 # update if exists
                "-a", key,            # account
                "-s", self._service,  # service
                "-w", secret,         # password (read from arg, not stdin)
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"keychain put failed (exit {result.returncode}): {result.stderr.strip()}"
            )

    def get(self, key: str) -> str | None:
        result = subprocess.run(
            [
                "security", "find-generic-password",
                "-a", key,
                "-s", self._service,
                "-w",  # output password only
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == self._NOT_FOUND_RETURNCODE:
            return None
        if result.returncode != 0:
            raise RuntimeError(
                f"keychain get failed (exit {result.returncode}): {result.stderr.strip()}"
            )
        return result.stdout.rstrip("\n")

    def delete(self, key: str) -> None:
        result = subprocess.run(
            [
                "security", "delete-generic-password",
                "-a", key,
                "-s", self._service,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode in (0, self._NOT_FOUND_RETURNCODE):
            return
        raise RuntimeError(
            f"keychain delete failed (exit {result.returncode}): {result.stderr.strip()}"
        )
```

- [ ] **Step 4: Run and verify all keychain tests pass**

Run:
```bash
pytest tests/unit/test_keychain.py -xvs
```
Expected: `11 passed`.

- [ ] **Step 5: Commit**

Run:
```bash
git add feishu_bot_claude/config/keychain.py tests/unit/test_keychain.py
git commit -m "feat(config): implement MacOSKeychainStore via security command"
```

---

### Task 1.9: config/keychain.py — Real macOS integration test

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/test_macos_keychain.py`

- [ ] **Step 1: Write the integration test**

Create empty `tests/integration/__init__.py`.

Create `tests/integration/test_macos_keychain.py`:
```python
"""Real macOS Keychain integration test.

Runs only on darwin. Uses a unique service prefix to avoid clashing with
production keys. Cleans up after itself.
"""

import platform
import uuid

import pytest

from feishu_bot_claude.config.keychain import MacOSKeychainStore

pytestmark = pytest.mark.skipif(
    platform.system() != "Darwin",
    reason="MacOSKeychainStore only runs on macOS",
)


def test_macos_keychain_full_lifecycle():
    """put → get → overwrite → get → delete → get should all behave correctly."""
    # Use a unique prefix so this test never collides with real data.
    prefix = f"feishu-bot-claude-test-{uuid.uuid4().hex[:8]}"
    store = MacOSKeychainStore(service_prefix=prefix)
    key = "lifecycle-key"

    try:
        # missing initially
        assert store.get(key) is None

        # put
        store.put(key, "v1")
        assert store.get(key) == "v1"

        # overwrite
        store.put(key, "v2")
        assert store.get(key) == "v2"

        # delete
        store.delete(key)
        assert store.get(key) is None

        # delete missing again — no-op
        store.delete(key)
    finally:
        # Defensive cleanup in case any step failed mid-way
        store.delete(key)
```

- [ ] **Step 2: Run the integration test**

Run:
```bash
pytest tests/integration/test_macos_keychain.py -xvs
```
Expected on macOS: `1 passed`.
Expected on Linux: `1 skipped`.

- [ ] **Step 3: Commit**

Run:
```bash
git add tests/integration/
git commit -m "test(config): add real macOS Keychain lifecycle integration test"
```

---

### Task 1.10: config/binding.py — BindingConfig dataclass

**Files:**
- Create: `feishu_bot_claude/config/binding.py`
- Create: `tests/unit/test_binding_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_binding_config.py`:
```python
"""Tests for BindingConfig dataclass."""

from datetime import datetime, timezone

import pytest

from feishu_bot_claude.config.binding import BindingConfig


def _example_config(**overrides) -> BindingConfig:
    defaults = dict(
        name="foo-bot",
        project_dir="/Users/me/project/foo",
        tmux_session="claude-foo",
        feishu_app_id="cli_xxxxxxxx",
        secret_ref="feishu-bot-claude.foo-bot.app_secret",
        render_style="rich",
        replay_on_start="all",
        mute_thinking=False,
        card_throttle_ms=300,
        domain="https://open.feishu.cn",
        api_timeout_ms=5000,
        upload_timeout_ms=60000,
        event_silent_threshold_ms=60000,
        event_dead_threshold_ms=120000,
        reconnect_grace_failures=3,
        created_at=datetime(2026, 5, 26, 18, 50, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return BindingConfig(**defaults)


def test_binding_config_accepts_valid_values():
    cfg = _example_config()
    assert cfg.name == "foo-bot"
    assert cfg.render_style == "rich"


def test_binding_config_rejects_invalid_render_style():
    with pytest.raises(ValueError, match="render_style"):
        _example_config(render_style="fancy")


def test_binding_config_rejects_invalid_replay_value():
    with pytest.raises(ValueError, match="replay_on_start"):
        _example_config(replay_on_start="2")  # only "0" / "100" / "all"
    with pytest.raises(ValueError, match="replay_on_start"):
        _example_config(replay_on_start="some")


def test_binding_config_rejects_negative_timeouts():
    with pytest.raises(ValueError, match="api_timeout_ms"):
        _example_config(api_timeout_ms=-1)


def test_binding_config_rejects_empty_name():
    with pytest.raises(ValueError, match="name"):
        _example_config(name="")


def test_binding_config_rejects_non_absolute_project_dir():
    with pytest.raises(ValueError, match="project_dir"):
        _example_config(project_dir="relative/path")
```

- [ ] **Step 2: Run and verify it fails**

Run:
```bash
pytest tests/unit/test_binding_config.py -xvs
```
Expected: `ImportError: cannot import name 'BindingConfig'`.

- [ ] **Step 3: Implement BindingConfig with validation**

Create `feishu_bot_claude/config/binding.py`:
```python
"""BindingConfig dataclass: per-binding configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


_VALID_RENDER_STYLES = {"minimal", "full", "rich"}
_VALID_REPLAY = {"0", "100", "all"}


@dataclass(frozen=True)
class BindingConfig:
    """Configuration for one project ↔ bot binding.

    Frozen because BindingStore returns immutable snapshots; mutations create
    a new BindingConfig and write a fresh TOML file.
    """

    name: str
    project_dir: str
    tmux_session: str
    feishu_app_id: str
    secret_ref: str
    render_style: str = "rich"
    replay_on_start: str = "all"
    mute_thinking: bool = False
    card_throttle_ms: int = 300
    domain: str = "https://open.feishu.cn"
    api_timeout_ms: int = 5000
    upload_timeout_ms: int = 60000
    event_silent_threshold_ms: int = 60000
    event_dead_threshold_ms: int = 120000
    reconnect_grace_failures: int = 3
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("name must be non-empty")
        if not Path(self.project_dir).is_absolute():
            raise ValueError(f"project_dir must be absolute: {self.project_dir!r}")
        if self.render_style not in _VALID_RENDER_STYLES:
            raise ValueError(
                f"render_style must be one of {sorted(_VALID_RENDER_STYLES)}, "
                f"got {self.render_style!r}"
            )
        if self.replay_on_start not in _VALID_REPLAY:
            raise ValueError(
                f"replay_on_start must be one of {sorted(_VALID_REPLAY)}, "
                f"got {self.replay_on_start!r}"
            )
        for fname in ("api_timeout_ms", "upload_timeout_ms", "card_throttle_ms",
                      "event_silent_threshold_ms", "event_dead_threshold_ms",
                      "reconnect_grace_failures"):
            value = getattr(self, fname)
            if value < 0:
                raise ValueError(f"{fname} must be non-negative, got {value}")
```

- [ ] **Step 4: Run and verify all tests pass**

Run:
```bash
pytest tests/unit/test_binding_config.py -xvs
```
Expected: `6 passed`.

- [ ] **Step 5: Commit**

Run:
```bash
git add feishu_bot_claude/config/binding.py tests/unit/test_binding_config.py
git commit -m "feat(config): add BindingConfig dataclass with validation"
```

---

### Task 1.11: config/binding.py — BindingStore TOML roundtrip

**Files:**
- Modify: `feishu_bot_claude/config/binding.py`
- Modify: `feishu_bot_claude/config/__init__.py`
- Create: `tests/unit/test_binding_store.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_binding_store.py`:
```python
"""Tests for BindingStore: TOML I/O, lookup, lifecycle."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from feishu_bot_claude.config.binding import BindingConfig, BindingStore


def _make_config(name="foo-bot", project_dir="/abs/foo", **overrides) -> BindingConfig:
    defaults = dict(
        name=name,
        project_dir=project_dir,
        tmux_session=f"claude-{name}",
        feishu_app_id=f"cli_{name}",
        secret_ref=f"feishu-bot-claude.{name}.app_secret",
        created_at=datetime(2026, 5, 26, 18, 50, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return BindingConfig(**defaults)


def test_empty_store_returns_no_bindings(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    assert store.all() == []


def test_add_then_find_by_name(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    cfg = _make_config()
    store.add(cfg)
    assert store.find_by_name("foo-bot") == cfg


def test_find_by_name_returns_none_when_absent(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    assert store.find_by_name("nope") is None


def test_find_by_cwd_returns_matching_binding(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(_make_config(name="foo-bot", project_dir="/abs/foo"))
    store.add(_make_config(name="bar-bot", project_dir="/abs/bar"))
    found = store.find_by_cwd("/abs/foo")
    assert found is not None
    assert found.name == "foo-bot"


def test_find_by_cwd_returns_none_when_no_match(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(_make_config(name="foo-bot", project_dir="/abs/foo"))
    assert store.find_by_cwd("/abs/other") is None


def test_add_persists_to_disk(tmp_path):
    path = tmp_path / "bindings.toml"
    store1 = BindingStore(path)
    cfg = _make_config()
    store1.add(cfg)

    # Reload from disk and verify
    store2 = BindingStore(path)
    assert store2.find_by_name("foo-bot") == cfg


def test_remove_deletes_binding(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(_make_config())
    store.remove("foo-bot")
    assert store.find_by_name("foo-bot") is None
    assert store.all() == []


def test_remove_missing_raises(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    with pytest.raises(KeyError, match="foo-bot"):
        store.remove("foo-bot")


def test_add_duplicate_name_raises(tmp_path):
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(_make_config(name="foo-bot"))
    with pytest.raises(ValueError, match="already exists"):
        store.add(_make_config(name="foo-bot", project_dir="/abs/different"))


def test_add_duplicate_project_dir_raises(tmp_path):
    """Hard invariant: one project dir ↔ one binding."""
    store = BindingStore(tmp_path / "bindings.toml")
    store.add(_make_config(name="foo-bot", project_dir="/abs/foo"))
    with pytest.raises(ValueError, match="project_dir.*already bound"):
        store.add(_make_config(name="another-bot", project_dir="/abs/foo"))


def test_toml_file_has_secure_permissions(tmp_path):
    """bindings.toml must be 0600 after any write."""
    path = tmp_path / "bindings.toml"
    store = BindingStore(path)
    store.add(_make_config())

    mode = path.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"
```

- [ ] **Step 2: Run and verify it fails**

Run:
```bash
pytest tests/unit/test_binding_store.py -xvs
```
Expected: `ImportError: cannot import name 'BindingStore'`.

- [ ] **Step 3: Implement BindingStore**

Add these imports at the top of `feishu_bot_claude/config/binding.py` (next to the existing ones):

```python
import os
import tomllib

import tomli_w
```

Then append everything below to the end of the file:
```python
_DEFAULT_FILE_MODE = 0o600


class BindingStore:
    """TOML-backed store of BindingConfig records.

    File format:
        [[binding]]
        name = "foo-bot"
        project_dir = "/abs/foo"
        ...

    Writes are atomic (write to tempfile, then rename) and enforce 0600 perms.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._cache: list[BindingConfig] = self._load()

    # --- public API ---

    def all(self) -> list[BindingConfig]:
        return list(self._cache)

    def find_by_name(self, name: str) -> BindingConfig | None:
        return next((b for b in self._cache if b.name == name), None)

    def find_by_cwd(self, cwd: str) -> BindingConfig | None:
        cwd_resolved = str(Path(cwd).resolve())
        return next(
            (b for b in self._cache if str(Path(b.project_dir).resolve()) == cwd_resolved),
            None,
        )

    def add(self, binding: BindingConfig) -> None:
        if self.find_by_name(binding.name) is not None:
            raise ValueError(f"binding {binding.name!r} already exists")
        if self.find_by_cwd(binding.project_dir) is not None:
            raise ValueError(
                f"project_dir {binding.project_dir!r} already bound to a binding"
            )
        self._cache.append(binding)
        self._save()

    def remove(self, name: str) -> None:
        for i, b in enumerate(self._cache):
            if b.name == name:
                del self._cache[i]
                self._save()
                return
        raise KeyError(name)

    # --- internals ---

    def _load(self) -> list[BindingConfig]:
        if not self._path.exists():
            return []
        with self._path.open("rb") as f:
            data = tomllib.load(f)
        return [_dict_to_binding(b) for b in data.get("binding", [])]

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"binding": [_binding_to_dict(b) for b in self._cache]}
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        with tmp.open("wb") as f:
            tomli_w.dump(payload, f)
        os.chmod(tmp, _DEFAULT_FILE_MODE)
        os.replace(tmp, self._path)


def _binding_to_dict(b: BindingConfig) -> dict:
    return {
        "name": b.name,
        "project_dir": b.project_dir,
        "tmux_session": b.tmux_session,
        "feishu_app_id": b.feishu_app_id,
        "secret_ref": b.secret_ref,
        "render_style": b.render_style,
        "replay_on_start": b.replay_on_start,
        "mute_thinking": b.mute_thinking,
        "card_throttle_ms": b.card_throttle_ms,
        "domain": b.domain,
        "api_timeout_ms": b.api_timeout_ms,
        "upload_timeout_ms": b.upload_timeout_ms,
        "event_silent_threshold_ms": b.event_silent_threshold_ms,
        "event_dead_threshold_ms": b.event_dead_threshold_ms,
        "reconnect_grace_failures": b.reconnect_grace_failures,
        "created_at": b.created_at,
    }


def _dict_to_binding(d: dict) -> BindingConfig:
    return BindingConfig(**d)
```

Update `feishu_bot_claude/config/__init__.py`:
```python
"""Configuration storage layer."""

from feishu_bot_claude.config.binding import BindingConfig, BindingStore
from feishu_bot_claude.config.keychain import (
    InMemoryKeychainStore,
    KeychainStore,
    MacOSKeychainStore,
)

__all__ = [
    "BindingConfig",
    "BindingStore",
    "KeychainStore",
    "InMemoryKeychainStore",
    "MacOSKeychainStore",
]
```

- [ ] **Step 4: Run and verify all tests pass**

Run:
```bash
pytest tests/unit/test_binding_store.py -xvs
```
Expected: `11 passed`.

- [ ] **Step 5: Commit**

Run:
```bash
git add feishu_bot_claude/config/binding.py feishu_bot_claude/config/__init__.py tests/unit/test_binding_store.py
git commit -m "feat(config): add BindingStore with atomic TOML write and 0600 perms"
```

---

### Task 1.12: config/binding.py — Concurrent write safety (flock)

**Files:**
- Modify: `feishu_bot_claude/config/binding.py`
- Modify: `tests/unit/test_binding_store.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_binding_store.py`:
```python
import threading


def test_concurrent_writes_do_not_corrupt(tmp_path):
    """Two threads adding different bindings should both succeed and produce
    a valid TOML file with both entries."""
    path = tmp_path / "bindings.toml"
    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def add_one(name: str, dir_: str) -> None:
        try:
            barrier.wait()
            store = BindingStore(path)
            store.add(_make_config(name=name, project_dir=dir_))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t1 = threading.Thread(target=add_one, args=("alpha", "/abs/alpha"))
    t2 = threading.Thread(target=add_one, args=("beta", "/abs/beta"))
    t1.start(); t2.start()
    t1.join(); t2.join()

    # One of them may legitimately fail if it lost the lock race — but if both
    # succeed, the file must have both entries; if one fails, the file must
    # have exactly one entry.
    final = BindingStore(path).all()
    names = {b.name for b in final}
    if not errors:
        assert names == {"alpha", "beta"}
    else:
        assert len(errors) == 1
        assert len(names) == 1
```

- [ ] **Step 2: Run and verify it fails (or passes by luck — we still need the lock)**

Run:
```bash
pytest tests/unit/test_binding_store.py::test_concurrent_writes_do_not_corrupt -xvs
```
Expected: PASS or FAIL depending on race timing — but without flock the test is not deterministic. The lock makes it correct under all interleavings; check with `-count=20`:
```bash
pytest tests/unit/test_binding_store.py::test_concurrent_writes_do_not_corrupt --count=20 -xvs || true
```
(If `pytest-repeat` isn't installed, just run the single test and proceed — we want flock for correctness anyway.)

- [ ] **Step 3: Add advisory flock to BindingStore writes**

Add these imports at the top of `feishu_bot_claude/config/binding.py`:

```python
import fcntl
from contextlib import contextmanager
```

Then add this helper function near the top of the file (after the imports, before the `BindingConfig` class):

```python
@contextmanager
def _exclusive_lock(path: Path):
    """Acquire an exclusive advisory lock on a sidecar lockfile."""
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
```

Replace `_save`:
```python
    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with _exclusive_lock(self._path):
            # Re-read inside the lock to merge concurrent additions safely
            disk = self._load_unlocked()
            merged = self._merge(disk, self._cache)
            self._cache = merged
            payload = {"binding": [_binding_to_dict(b) for b in self._cache]}
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            with tmp.open("wb") as f:
                tomli_w.dump(payload, f)
            os.chmod(tmp, _DEFAULT_FILE_MODE)
            os.replace(tmp, self._path)
```

Rename the old `_load` (no-lock helper) and add the merge logic. Replace the existing `_load`:
```python
    def _load(self) -> list[BindingConfig]:
        with _exclusive_lock(self._path):
            return self._load_unlocked()

    def _load_unlocked(self) -> list[BindingConfig]:
        if not self._path.exists():
            return []
        with self._path.open("rb") as f:
            data = tomllib.load(f)
        return [_dict_to_binding(b) for b in data.get("binding", [])]

    @staticmethod
    def _merge(disk: list[BindingConfig], cache: list[BindingConfig]) -> list[BindingConfig]:
        """Merge disk state with in-memory cache.

        Strategy: cache wins for entries present in cache; entries on disk but
        absent from cache (added by another process while we held no lock)
        are preserved. Conflicts on `name` raise.
        """
        by_name: dict[str, BindingConfig] = {b.name: b for b in disk}
        for b in cache:
            if b.name in by_name and by_name[b.name] != b:
                # Other process wrote a different version of the same name
                # while we were also adding — surface as a conflict.
                raise ValueError(
                    f"concurrent modification: {b.name!r} differs on disk"
                )
            by_name[b.name] = b
        return list(by_name.values())
```

- [ ] **Step 4: Run and verify**

Run:
```bash
pytest tests/unit/test_binding_store.py -xvs
```
Expected: `12 passed`. Run the concurrent test a few times to gain confidence:
```bash
for i in 1 2 3 4 5; do pytest tests/unit/test_binding_store.py::test_concurrent_writes_do_not_corrupt -x; done
```

- [ ] **Step 5: Commit**

Run:
```bash
git add feishu_bot_claude/config/binding.py tests/unit/test_binding_store.py
git commit -m "feat(config): use fcntl advisory lock for concurrent BindingStore writes"
```

---

### Task 1.13: Full test suite + coverage check

**Files:** (no new code)

- [ ] **Step 1: Run the entire test suite**

Run:
```bash
pytest --cov=feishu_bot_claude --cov-report=term-missing -v
```
Expected: all tests pass; coverage on `feishu_bot_claude/` is ≥95%. Note any uncovered lines for follow-up.

- [ ] **Step 2: Fix coverage gaps if any**

Any line marked missing in `proto.py`, `config/binding.py`, or `config/keychain.py` either:
- Add a test that exercises it
- Or document why it's uncoverable (and skip with `# pragma: no cover`)

Re-run until coverage looks clean.

- [ ] **Step 3: Lint-style sanity (manual)**

Run:
```bash
python -c "
import feishu_bot_claude
from feishu_bot_claude.proto import Request, parse_response_line
from feishu_bot_claude.config import BindingConfig, BindingStore, MacOSKeychainStore, InMemoryKeychainStore
print('all imports clean')
print('Request fields:', Request('list').to_json_line())
"
```
Expected:
```
all imports clean
Request fields: {"op":"list","args":{},"request_id":""}
```

- [ ] **Step 4: Commit (only if test/coverage tweaks were made)**

If any changes:
```bash
git add tests/ feishu_bot_claude/
git commit -m "test: close coverage gaps in proto and config"
```

If no changes, skip.

---

### Task 1.14: Phase 1 wrap-up document

**Files:**
- Create: `docs/phase-1-summary.md`

- [ ] **Step 1: Write the summary**

Create `~/project/feishu-bot-claude/docs/phase-1-summary.md`:
```markdown
# Phase 1 Summary

**Date completed:** <fill in>

## What's in place

- Project scaffolding: `pyproject.toml`, `.gitignore`, `README.md`, git repo
- Python package `feishu_bot_claude` importable via `pip install -e .`
- `proto.py` — `Request` + 5 response event dataclasses + `parse_response_line`,
  with op validation and JSON line roundtrip
- `config/keychain.py` — `KeychainStore` ABC, `InMemoryKeychainStore` fake,
  `MacOSKeychainStore` real backend (via `security` command)
- `config/binding.py` — `BindingConfig` dataclass (validated) + `BindingStore`
  with atomic TOML writes, 0600 perms, and fcntl flock for concurrent safety
- Tests: unit + integration; all pass; coverage ≥95% on `feishu_bot_claude/`

## What's intentionally missing (later phases)

- No daemon process
- No CLI
- No Feishu API integration
- No tmux integration
- No card rendering
- No `.claude/commands/` files
- No `setup.sh`

## Verification commands

```bash
cd ~/project/feishu-bot-claude
source .venv/bin/activate
pytest --cov=feishu_bot_claude -v
```

## Next phase preview

Phase 2 will add the IPC plumbing: daemon process listening on Unix socket,
CLI client talking to it, three stub ops (`list`, `ping`, `status`). Still no
real Feishu I/O — bindings will be added through a stub bind handler that
skips OAuth (uses a fake `app_id`).
```

- [ ] **Step 2: Commit**

Run:
```bash
git add docs/phase-1-summary.md
git commit -m "docs: phase 1 summary"
```

- [ ] **Step 3: Tag the milestone**

Run:
```bash
git tag -a phase-1-complete -m "Phase 1: foundation (proto + config) complete"
```

---

## Phase 1 Done. What's Next?

After Phase 1 is committed, the next plan covers:

**Phase 2 — IPC Plumbing**
- `daemon/server.py` (asyncio Unix socket server)
- `daemon/dispatcher.py` (op → handler routing)
- `cli.py` (socket client + click commands)
- 3 stub ops working end-to-end: `list`, `ping`, `status`
- `bind`/`start`/`stop` handlers return "not yet implemented" cleanly

**Phase 3 — External Adapters**
- `daemon/tmux.py` (wrap tmux commands, fake backend for tests)
- `daemon/feishu.py` (wrap lark-cli subprocess for send/consume, fake)

**Phase 4 — Card Rendering**
- `rendering/card.py`, `rendering/turn.py`, `rendering/tools.py`, `rendering/uploads.py`
- Golden file fixtures + tests

**Phase 5 — Mirror Pipeline (outbound + inbound)**

**Phase 6 — Orchestrator + Lifecycle**

**Phase 7 — Real Feishu OAuth + Menu Push**

**Phase 8 — Distribution (commands/, setup.sh, launchd/systemd)**

**Phase 9 — Hardening (rate limit, recovery, security opt-in fields)**

Each phase will be its own plan written after the previous phase lands, so we can react to discoveries.
