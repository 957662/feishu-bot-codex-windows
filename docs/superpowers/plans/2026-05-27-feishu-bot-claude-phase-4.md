# feishu-bot-claude — Phase 4: Card Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the rendering layer that turns Claude jsonl events into Feishu interactive cards. After Phase 4, you can feed sample jsonl fixtures into a pure function and get back card JSON identical to golden files. No I/O, no daemon — just data → data.

**Architecture:** Four modules. `card.py` has small composable JSON builders (header, markdown, divider, action button, collapsible section). `turn.py` groups raw jsonl events into "turns" (one user message → one assistant response). `tools.py` formats each tool_use/tool_result pair into a collapsible card block. `uploads.py` decides when to truncate vs upload large outputs (uses `LarkCli.upload_file` — uses fake in tests).

**Tech Stack:** Python only. Golden file comparison via JSON diffing.

**Prerequisite:** Phase 3 complete.

**Scope (Phase 4 deliverables):**
- `feishu_bot_claude/rendering/__init__.py`
- `feishu_bot_claude/rendering/card.py` — JSON builders (one fn per element)
- `feishu_bot_claude/rendering/turn.py` — `Turn` dataclass + jsonl → turns
- `feishu_bot_claude/rendering/tools.py` — per-tool renderers
- `feishu_bot_claude/rendering/uploads.py` — long-output upload threshold
- `tests/golden/fixtures/*.jsonl` — input fixtures
- `tests/golden/expected/*.card.json` — expected output JSON
- `tests/unit/test_card_builders.py`
- `tests/unit/test_turn_grouping.py`
- `tests/unit/test_tool_rendering.py`
- `tests/unit/test_uploads.py`
- `tests/golden/test_golden_cards.py`

---

## File Structure (Phase 4)

| Path | Responsibility |
|---|---|
| `feishu_bot_claude/rendering/card.py` | Pure functions returning Feishu card JSON fragments |
| `feishu_bot_claude/rendering/turn.py` | `Turn`, `JsonlEvent`, `group_into_turns()` |
| `feishu_bot_claude/rendering/tools.py` | `render_tool_block(tool_use, tool_result, render_style)` |
| `feishu_bot_claude/rendering/uploads.py` | `LongOutputPolicy` — truncate vs upload, threshold logic |
| `tests/golden/fixtures/turn_simple.jsonl` | Single user → assistant text, no tools |
| `tests/golden/fixtures/turn_with_read.jsonl` | user → assistant + Read tool |
| `tests/golden/fixtures/turn_with_bash_long.jsonl` | user → assistant + Bash with 500-line output |
| `tests/golden/fixtures/turn_with_subagent.jsonl` | user → assistant + Task subagent dispatch |
| `tests/golden/fixtures/turn_confirmation.jsonl` | `/clear` Y/N confirmation prompt |
| `tests/golden/expected/turn_*.card.json` | Pretty-printed expected cards |

---

## Phase 4 Tasks

### Task 4.1: card.py — atomic element builders

**Files:**
- Create: `feishu_bot_claude/rendering/__init__.py`
- Create: `feishu_bot_claude/rendering/card.py`
- Create: `tests/unit/test_card_builders.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_card_builders.py`:
```python
"""Tests for atomic card JSON builders."""

from feishu_bot_claude.rendering.card import (
    build_card,
    build_header,
    build_markdown,
    build_divider,
    build_note,
    build_collapsible,
    build_action_buttons,
)


def test_header_basic():
    h = build_header(title="🤖 Claude · foo · opus-4-7")
    assert h == {
        "template": "purple",
        "title": {"tag": "plain_text", "content": "🤖 Claude · foo · opus-4-7"},
    }


def test_header_custom_template():
    h = build_header(title="x", template="green")
    assert h["template"] == "green"


def test_markdown_element():
    m = build_markdown("hello *world*")
    assert m == {"tag": "markdown", "content": "hello *world*"}


def test_divider_element():
    assert build_divider() == {"tag": "hr"}


def test_note_element():
    n = build_note("1.2K tokens · 4.3s")
    assert n == {
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": "1.2K tokens · 4.3s"}],
    }


def test_collapsible_element():
    c = build_collapsible(
        summary="📖 Read auth.go  ✓ 50 lines",
        body_markdown="```\npackage auth\n```",
    )
    assert c["tag"] == "collapsible_panel"
    assert c["header"]["title"]["content"] == "📖 Read auth.go  ✓ 50 lines"
    body_elements = c["elements"]
    assert len(body_elements) == 1
    assert body_elements[0]["tag"] == "markdown"
    assert "package auth" in body_elements[0]["content"]


def test_action_buttons_two():
    buttons = build_action_buttons([
        ("confirm_yes", "确认", "primary"),
        ("confirm_no", "取消", "default"),
    ])
    assert buttons["tag"] == "action"
    actions = buttons["actions"]
    assert len(actions) == 2
    assert actions[0]["text"]["content"] == "确认"
    assert actions[0]["type"] == "primary"
    assert actions[0]["value"] == {"event_key": "confirm_yes"}


def test_build_card_combines_elements():
    card = build_card(
        header=build_header(title="t"),
        elements=[build_markdown("hi"), build_divider(), build_note("done")],
    )
    assert card["header"]["title"]["content"] == "t"
    assert len(card["elements"]) == 3
    assert card["elements"][0]["tag"] == "markdown"
    assert card["elements"][1]["tag"] == "hr"
    assert card["elements"][2]["tag"] == "note"
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_card_builders.py -xvs
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement builders**

Create `feishu_bot_claude/rendering/__init__.py`:
```python
"""Rendering layer — jsonl events → Feishu card JSON."""
```

Create `feishu_bot_claude/rendering/card.py`:
```python
"""Atomic Feishu interactive card JSON builders.

Each function returns a single element or a complete card dict. They compose:
build_card(header=..., elements=[build_markdown(...), build_divider(), ...]).
"""

from __future__ import annotations

from typing import Iterable, Literal

Template = Literal["red", "orange", "yellow", "green", "blue", "purple", "indigo", "wathet", "turquoise", "carmine", "violet", "grey"]
ButtonType = Literal["default", "primary", "danger"]


def build_header(title: str, template: Template = "purple") -> dict:
    return {
        "template": template,
        "title": {"tag": "plain_text", "content": title},
    }


def build_markdown(content: str) -> dict:
    return {"tag": "markdown", "content": content}


def build_divider() -> dict:
    return {"tag": "hr"}


def build_note(content: str) -> dict:
    return {
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": content}],
    }


def build_collapsible(summary: str, body_markdown: str, expanded: bool = False) -> dict:
    return {
        "tag": "collapsible_panel",
        "expanded": expanded,
        "header": {
            "title": {"tag": "plain_text", "content": summary},
        },
        "elements": [build_markdown(body_markdown)],
    }


def build_action_buttons(buttons: Iterable[tuple[str, str, ButtonType]]) -> dict:
    """buttons is iterable of (event_key, label, type)."""
    actions = []
    for event_key, label, btn_type in buttons:
        actions.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": label},
            "type": btn_type,
            "value": {"event_key": event_key},
        })
    return {"tag": "action", "actions": actions}


def build_card(header: dict, elements: list[dict]) -> dict:
    return {
        "schema": "2.0",
        "header": header,
        "elements": elements,
    }
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_card_builders.py -xvs
```
Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/rendering/ tests/unit/test_card_builders.py
git commit -m "feat(rendering): atomic Feishu card element builders"
```

---

### Task 4.2: turn.py — JsonlEvent + group_into_turns

**Files:**
- Create: `feishu_bot_claude/rendering/turn.py`
- Create: `tests/unit/test_turn_grouping.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_turn_grouping.py`:
```python
"""Tests for grouping jsonl events into Turns."""

import json
from pathlib import Path

import pytest

from feishu_bot_claude.rendering.turn import JsonlEvent, Turn, group_into_turns


def _evt(role: str, **extra) -> dict:
    base = {"role": role, "uuid": f"u-{role}-{extra.get('idx', 0)}"}
    base.update(extra)
    return base


def test_single_user_message_creates_one_turn():
    events = [JsonlEvent.from_dict(_evt("user", content=[{"type": "text", "text": "hi"}]))]
    turns = group_into_turns(events)
    assert len(turns) == 1
    assert turns[0].user_event is not None
    assert turns[0].assistant_events == []


def test_user_then_assistant_groups_into_one_turn():
    events = [
        JsonlEvent.from_dict(_evt("user", content=[{"type": "text", "text": "hi"}])),
        JsonlEvent.from_dict(_evt("assistant", content=[{"type": "text", "text": "hello"}])),
    ]
    turns = group_into_turns(events)
    assert len(turns) == 1
    assert len(turns[0].assistant_events) == 1


def test_assistant_with_tool_use_and_result_in_same_turn():
    events = [
        JsonlEvent.from_dict(_evt("user", content=[{"type": "text", "text": "read"}])),
        JsonlEvent.from_dict(_evt("assistant", content=[{"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/x"}}])),
        JsonlEvent.from_dict(_evt("user", content=[{"type": "tool_result", "tool_use_id": "t1", "content": "data"}])),
        JsonlEvent.from_dict(_evt("assistant", content=[{"type": "text", "text": "done"}])),
    ]
    turns = group_into_turns(events)
    # tool_result is technically role=user in Claude's format but logically belongs to the same turn
    assert len(turns) == 1
    assert len(turns[0].assistant_events) == 3


def test_two_user_messages_create_two_turns():
    events = [
        JsonlEvent.from_dict(_evt("user", content=[{"type": "text", "text": "first"}])),
        JsonlEvent.from_dict(_evt("assistant", content=[{"type": "text", "text": "a"}])),
        JsonlEvent.from_dict(_evt("user", content=[{"type": "text", "text": "second"}])),
        JsonlEvent.from_dict(_evt("assistant", content=[{"type": "text", "text": "b"}])),
    ]
    turns = group_into_turns(events)
    assert len(turns) == 2
    assert turns[0].user_event.text() == "first"
    assert turns[1].user_event.text() == "second"


def test_load_jsonl_file(tmp_path):
    path = tmp_path / "session.jsonl"
    lines = [
        json.dumps({"role": "user", "uuid": "u1", "content": [{"type": "text", "text": "hi"}]}),
        json.dumps({"role": "assistant", "uuid": "a1", "content": [{"type": "text", "text": "hello"}]}),
    ]
    path.write_text("\n".join(lines) + "\n")

    events = list(JsonlEvent.load_file(path))
    assert len(events) == 2
    assert events[0].role == "user"
    assert events[1].role == "assistant"


def test_jsonl_event_skips_blank_lines(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text(
        '{"role": "user", "uuid": "u1", "content": []}\n'
        '\n'
        '   \n'
        '{"role": "assistant", "uuid": "a1", "content": []}\n'
    )
    events = list(JsonlEvent.load_file(path))
    assert len(events) == 2


def test_jsonl_event_text_method():
    e = JsonlEvent.from_dict({"role": "user", "uuid": "u1",
                              "content": [{"type": "text", "text": "first"}, {"type": "text", "text": " more"}]})
    assert e.text() == "first more"


def test_tool_use_only_user_event_belongs_to_previous_turn():
    """A user message whose content is ONLY tool_result(s) (no text) belongs to the previous turn."""
    events = [
        JsonlEvent.from_dict(_evt("user", content=[{"type": "text", "text": "go"}])),
        JsonlEvent.from_dict(_evt("assistant", content=[{"type": "tool_use", "id": "t1", "name": "Read", "input": {}}])),
        JsonlEvent.from_dict(_evt("user", content=[{"type": "tool_result", "tool_use_id": "t1", "content": "x"}])),
    ]
    turns = group_into_turns(events)
    assert len(turns) == 1
    assert turns[0].user_event.text() == "go"
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_turn_grouping.py -xvs
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `JsonlEvent` + `Turn` + `group_into_turns`**

Create `feishu_bot_claude/rendering/turn.py`:
```python
"""Group raw Claude jsonl events into Turns for rendering."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator


@dataclass(frozen=True)
class JsonlEvent:
    """One line from Claude's session jsonl."""

    role: str             # "user" | "assistant" | "system"
    uuid: str
    content: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> JsonlEvent:
        return cls(
            role=d.get("role", ""),
            uuid=d.get("uuid", ""),
            content=d.get("content", []),
            raw=d,
        )

    @classmethod
    def load_file(cls, path: Path) -> Iterator[JsonlEvent]:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield cls.from_dict(json.loads(line))

    def text(self) -> str:
        return "".join(c.get("text", "") for c in self.content if c.get("type") == "text")

    def has_only_tool_results(self) -> bool:
        if not self.content:
            return False
        return all(c.get("type") == "tool_result" for c in self.content)


@dataclass
class Turn:
    """One conversation turn: a user message and the assistant response(s)."""

    user_event: JsonlEvent | None
    assistant_events: list[JsonlEvent] = field(default_factory=list)


def group_into_turns(events: Iterable[JsonlEvent]) -> list[Turn]:
    """Group an iterable of JsonlEvents into Turn list.

    A new Turn starts on a `user` event that contains at least one text part
    (i.e., a real user message, not just tool_result delivery).
    """
    turns: list[Turn] = []
    current: Turn | None = None

    for event in events:
        if event.role == "user" and not event.has_only_tool_results():
            current = Turn(user_event=event)
            turns.append(current)
        else:
            if current is None:
                # Orphan event before any user message — start a turn with no user_event
                current = Turn(user_event=None)
                turns.append(current)
            current.assistant_events.append(event)

    return turns
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_turn_grouping.py -xvs
```
Expected: `8 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/rendering/turn.py tests/unit/test_turn_grouping.py
git commit -m "feat(rendering): group jsonl events into Turns"
```

---

### Task 4.3: tools.py — per-tool block renderers

**Files:**
- Create: `feishu_bot_claude/rendering/tools.py`
- Create: `tests/unit/test_tool_rendering.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_tool_rendering.py`:
```python
"""Tests for per-tool block rendering."""

from feishu_bot_claude.rendering.tools import (
    TOOL_ICONS,
    render_tool_block,
    summarize_tool_result,
)


def test_tool_icon_for_read():
    assert TOOL_ICONS["Read"] == "📖"


def test_tool_icon_for_unknown_falls_back():
    assert TOOL_ICONS.get("UnknownTool", "🔧") == "🔧"


def test_render_read_block_rich():
    tool_use = {"name": "Read", "input": {"file_path": "/abs/auth.go"}}
    tool_result = {"content": "package auth\nfunc x() {}\n"}
    block = render_tool_block(tool_use, tool_result, render_style="rich")
    assert block["tag"] == "collapsible_panel"
    title = block["header"]["title"]["content"]
    assert "📖" in title
    assert "auth.go" in title
    assert "✓" in title  # success indicator
    body = block["elements"][0]["content"]
    assert "package auth" in body


def test_render_bash_long_output_truncates():
    tool_use = {"name": "Bash", "input": {"command": "ls -la"}}
    long = "\n".join([f"line {i}" for i in range(200)])
    tool_result = {"content": long}
    block = render_tool_block(tool_use, tool_result, render_style="rich", preview_lines=20)
    body = block["elements"][0]["content"]
    # First 20 lines present, last lines absent, with ellipsis marker
    assert "line 0" in body
    assert "line 19" in body
    assert "line 199" not in body
    assert "省略" in body or "..." in body or "omitted" in body.lower()


def test_render_edit_block_shows_diff_summary():
    tool_use = {"name": "Edit", "input": {"file_path": "/x", "old_string": "a", "new_string": "b"}}
    tool_result = {"content": "ok"}
    block = render_tool_block(tool_use, tool_result, render_style="rich")
    title = block["header"]["title"]["content"]
    assert "✏️" in title


def test_render_failed_tool_uses_failure_marker():
    tool_use = {"name": "Bash", "input": {"command": "false"}}
    tool_result = {"content": "exit 1", "is_error": True}
    block = render_tool_block(tool_use, tool_result, render_style="rich")
    title = block["header"]["title"]["content"]
    assert "✗" in title or "❌" in title


def test_render_pending_tool_no_result_yet():
    """In-flight tool call (no result yet) shows hourglass."""
    tool_use = {"name": "Read", "input": {"file_path": "/x"}}
    block = render_tool_block(tool_use, tool_result=None, render_style="rich")
    title = block["header"]["title"]["content"]
    assert "⏳" in title


def test_summarize_tool_result_for_short():
    summary = summarize_tool_result({"content": "ok"})
    assert summary == "ok"


def test_summarize_tool_result_for_long():
    summary = summarize_tool_result({"content": "a\n" * 100})
    assert "lines" in summary  # e.g. "100 lines"


def test_render_minimal_style_omits_tool_blocks():
    """In minimal mode, render_tool_block returns None."""
    tool_use = {"name": "Read", "input": {"file_path": "/x"}}
    tool_result = {"content": "data"}
    assert render_tool_block(tool_use, tool_result, render_style="minimal") is None
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_tool_rendering.py -xvs
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `tools.py`**

Create `feishu_bot_claude/rendering/tools.py`:
```python
"""Per-tool block rendering — jsonl tool_use + tool_result → Feishu card block."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from feishu_bot_claude.rendering.card import build_collapsible


RenderStyle = Literal["minimal", "full", "rich"]


TOOL_ICONS: dict[str, str] = {
    "Read": "📖",
    "Write": "📝",
    "Edit": "✏️",
    "MultiEdit": "✏️",
    "Bash": "💻",
    "Grep": "🔍",
    "Glob": "📁",
    "WebFetch": "🌐",
    "WebSearch": "🌐",
    "Task": "🤖",
    "TodoWrite": "✅",
    "NotebookEdit": "📓",
}


def _icon(tool_name: str) -> str:
    return TOOL_ICONS.get(tool_name, "🔧")


def _format_title(tool_use: dict, tool_result: dict | None) -> str:
    name = tool_use.get("name", "?")
    icon = _icon(name)
    target = _tool_target(tool_use)
    status = _status_marker(tool_result)
    detail = _tool_detail(tool_use, tool_result)
    parts = [f"{icon} {name}"]
    if target:
        parts.append(target)
    parts.append(status)
    if detail:
        parts.append(detail)
    return "  ".join(parts)


def _tool_target(tool_use: dict) -> str:
    name = tool_use.get("name", "")
    args = tool_use.get("input", {}) or {}
    if name in {"Read", "Write", "Edit", "MultiEdit"}:
        path = args.get("file_path", "")
        return Path(path).name if path else ""
    if name == "Bash":
        cmd = args.get("command", "")
        return (cmd[:40] + "…") if len(cmd) > 40 else cmd
    if name == "Grep":
        return args.get("pattern", "")
    if name == "Glob":
        return args.get("pattern", "")
    if name == "WebFetch":
        return args.get("url", "")[:40]
    if name == "Task":
        return args.get("subagent_type", "")
    return ""


def _status_marker(tool_result: dict | None) -> str:
    if tool_result is None:
        return "⏳"
    if tool_result.get("is_error"):
        return "✗"
    return "✓"


def _tool_detail(tool_use: dict, tool_result: dict | None) -> str:
    if tool_result is None:
        return ""
    content = tool_result.get("content", "")
    if isinstance(content, str):
        lines = content.count("\n") + (1 if content else 0)
        if lines > 1:
            return f"{lines} lines"
    return ""


def render_tool_block(
    tool_use: dict,
    tool_result: dict | None,
    render_style: RenderStyle,
    preview_lines: int = 20,
) -> dict | None:
    """Return a collapsible card block for one tool call, or None if minimal."""
    if render_style == "minimal":
        return None

    title = _format_title(tool_use, tool_result)
    body = _build_body(tool_use, tool_result, render_style, preview_lines)
    return build_collapsible(summary=title, body_markdown=body, expanded=False)


def _build_body(tool_use: dict, tool_result: dict | None, render_style: RenderStyle, preview_lines: int) -> str:
    parts = []
    if render_style == "full":
        args = tool_use.get("input", {})
        if args:
            import json
            parts.append("**Input:**\n```json\n" + json.dumps(args, ensure_ascii=False, indent=2) + "\n```")
    if tool_result is None:
        parts.append("_pending..._")
        return "\n\n".join(parts)
    content = tool_result.get("content", "")
    if isinstance(content, list):
        content = "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    if not isinstance(content, str):
        content = str(content)
    lines = content.splitlines()
    if len(lines) > preview_lines:
        head = "\n".join(lines[:preview_lines])
        parts.append(f"```\n{head}\n```\n_...省略 {len(lines) - preview_lines} 行..._")
    elif content:
        parts.append(f"```\n{content}\n```")
    return "\n\n".join(parts) if parts else "_(empty)_"


def summarize_tool_result(tool_result: dict | None) -> str:
    if tool_result is None:
        return "(pending)"
    content = tool_result.get("content", "")
    if isinstance(content, list):
        content = "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    if not isinstance(content, str):
        content = str(content)
    lines = content.count("\n") + (1 if content else 0)
    if lines > 1:
        return f"{lines} lines"
    return content[:80]
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_tool_rendering.py -xvs
```
Expected: `9 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/rendering/tools.py tests/unit/test_tool_rendering.py
git commit -m "feat(rendering): per-tool block renderer with preview truncation"
```

---

### Task 4.4: uploads.py — LongOutputPolicy

**Files:**
- Create: `feishu_bot_claude/rendering/uploads.py`
- Create: `tests/unit/test_uploads.py`

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_uploads.py`:
```python
"""Tests for long-output upload decision policy."""

import pytest

from feishu_bot_claude.rendering.uploads import LongOutputPolicy, UploadDecision


def test_short_output_inlines():
    policy = LongOutputPolicy(inline_lines_threshold=50, upload_bytes_threshold=10_000)
    decision = policy.decide(content="line1\nline2")
    assert decision == UploadDecision.INLINE


def test_long_lines_uploads():
    policy = LongOutputPolicy(inline_lines_threshold=50, upload_bytes_threshold=10_000)
    content = "\n".join(["x"] * 100)
    decision = policy.decide(content=content)
    assert decision == UploadDecision.UPLOAD


def test_big_bytes_uploads():
    policy = LongOutputPolicy(inline_lines_threshold=10_000, upload_bytes_threshold=1024)
    content = "x" * 5000  # 5KB on one line, exceeds byte threshold
    decision = policy.decide(content=content)
    assert decision == UploadDecision.UPLOAD


def test_disabled_policy_always_inlines():
    policy = LongOutputPolicy(inline_lines_threshold=50, upload_bytes_threshold=10_000, enabled=False)
    long = "\n".join(["x"] * 10_000)
    assert policy.decide(long) == UploadDecision.INLINE
```

- [ ] **Step 2: Verify failure**

```bash
pytest tests/unit/test_uploads.py -xvs
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `uploads.py`**

Create `feishu_bot_claude/rendering/uploads.py`:
```python
"""Decide whether a tool's output is inlined into the card or uploaded as a file."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class UploadDecision(Enum):
    INLINE = "inline"
    UPLOAD = "upload"


@dataclass(frozen=True)
class LongOutputPolicy:
    """Decide INLINE vs UPLOAD based on line count and byte size."""

    inline_lines_threshold: int = 50
    upload_bytes_threshold: int = 10_000  # 10 KB
    enabled: bool = True

    def decide(self, content: str) -> UploadDecision:
        if not self.enabled:
            return UploadDecision.INLINE
        line_count = content.count("\n") + (1 if content else 0)
        if line_count > self.inline_lines_threshold:
            return UploadDecision.UPLOAD
        if len(content.encode("utf-8")) > self.upload_bytes_threshold:
            return UploadDecision.UPLOAD
        return UploadDecision.INLINE
```

- [ ] **Step 4: Verify**

```bash
pytest tests/unit/test_uploads.py -xvs
```
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add feishu_bot_claude/rendering/uploads.py tests/unit/test_uploads.py
git commit -m "feat(rendering): LongOutputPolicy for inline-vs-upload decisions"
```

---

### Task 4.5: Golden fixtures + comparison harness

**Files:**
- Create: `tests/golden/__init__.py`
- Create: `tests/golden/fixtures/turn_simple.jsonl`
- Create: `tests/golden/fixtures/turn_with_read.jsonl`
- Create: `tests/golden/fixtures/turn_with_bash_long.jsonl`
- Create: `tests/golden/fixtures/turn_with_subagent.jsonl`
- Create: `tests/golden/fixtures/turn_confirmation.jsonl`
- Create: `tests/golden/test_golden_cards.py`

- [ ] **Step 1: Create fixture files**

Create empty `tests/golden/__init__.py`.

Create `tests/golden/fixtures/turn_simple.jsonl` (one user, one assistant text, no tools):
```jsonl
{"role": "user", "uuid": "u1", "content": [{"type": "text", "text": "你好"}]}
{"role": "assistant", "uuid": "a1", "content": [{"type": "text", "text": "你好!有什么可以帮你?"}], "usage": {"input_tokens": 10, "output_tokens": 12}}
```

Create `tests/golden/fixtures/turn_with_read.jsonl`:
```jsonl
{"role": "user", "uuid": "u1", "content": [{"type": "text", "text": "读 auth.go"}]}
{"role": "assistant", "uuid": "a1", "content": [{"type": "text", "text": "好,我读一下。"}, {"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "/abs/auth.go"}}]}
{"role": "user", "uuid": "u2", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "package auth\nfunc Login() {}\nfunc Logout() {}\n"}]}
{"role": "assistant", "uuid": "a2", "content": [{"type": "text", "text": "看完了,有 Login 和 Logout 两个函数。"}], "usage": {"input_tokens": 50, "output_tokens": 30}}
```

Create `tests/golden/fixtures/turn_with_bash_long.jsonl`:
```jsonl
{"role": "user", "uuid": "u1", "content": [{"type": "text", "text": "看下文件"}]}
{"role": "assistant", "uuid": "a1", "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "ls -la /tmp"}}]}
```
Then append a tool_result with 200 lines of "fake-line-N":

Programmatically (write a one-off script or use:
```bash
python3 -c '
import json
content = "\n".join(f"fake-line-{i}" for i in range(200))
event = {"role": "user", "uuid": "u2", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": content}]}
print(json.dumps(event, ensure_ascii=False))
' >> tests/golden/fixtures/turn_with_bash_long.jsonl
```

Then append a final assistant message:
```jsonl
{"role": "assistant", "uuid": "a2", "content": [{"type": "text", "text": "好多文件,我列了 200 行。"}], "usage": {"input_tokens": 500, "output_tokens": 20}}
```

Create `tests/golden/fixtures/turn_with_subagent.jsonl`:
```jsonl
{"role": "user", "uuid": "u1", "content": [{"type": "text", "text": "搜索一下"}]}
{"role": "assistant", "uuid": "a1", "content": [{"type": "tool_use", "id": "t1", "name": "Task", "input": {"subagent_type": "general-purpose", "description": "search for auth code"}}]}
{"role": "user", "uuid": "u2", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "Found 3 matches in auth.go"}]}
{"role": "assistant", "uuid": "a2", "content": [{"type": "text", "text": "找到 3 处。"}]}
```

Create `tests/golden/fixtures/turn_confirmation.jsonl`:
```jsonl
{"role": "user", "uuid": "u1", "content": [{"type": "text", "text": "/clear"}]}
{"role": "system", "uuid": "s1", "content": [{"type": "text", "text": "Are you sure you want to clear the conversation? [y/N]"}], "subtype": "confirmation_prompt"}
```

- [ ] **Step 2: Write the golden test harness**

Create `tests/golden/test_golden_cards.py`:
```python
"""Golden-file tests: each fixture jsonl should render to a stored expected card JSON."""

import json
from pathlib import Path

import pytest

from feishu_bot_claude.rendering.turn import JsonlEvent, group_into_turns
from feishu_bot_claude.rendering.card import build_card, build_header, build_markdown, build_note
from feishu_bot_claude.rendering.tools import render_tool_block

FIXTURES_DIR = Path(__file__).parent / "fixtures"
EXPECTED_DIR = Path(__file__).parent / "expected"


def render_turn_to_card(turn, project_name: str = "test-project", render_style: str = "rich") -> dict:
    """Reference implementation: turn → card JSON. Promoted from this test into
    `rendering/turn.py` as a real function in Task 4.6.
    """
    elements: list[dict] = []
    for event in turn.assistant_events:
        for part in event.content:
            if part.get("type") == "text" and part.get("text"):
                elements.append(build_markdown(part["text"]))
            elif part.get("type") == "tool_use":
                # find matching tool_result in later events
                tool_use = part
                tool_result = None
                for later in turn.assistant_events:
                    for p in later.content:
                        if p.get("type") == "tool_result" and p.get("tool_use_id") == tool_use.get("id"):
                            tool_result = p
                            break
                block = render_tool_block(tool_use, tool_result, render_style=render_style)
                if block is not None:
                    elements.append(block)

    # Footer note: token usage
    total_in = sum(e.raw.get("usage", {}).get("input_tokens", 0) for e in turn.assistant_events)
    total_out = sum(e.raw.get("usage", {}).get("output_tokens", 0) for e in turn.assistant_events)
    if total_in or total_out:
        elements.append(build_note(f"{total_in}+{total_out} tokens"))

    header = build_header(title=f"🤖 Claude · {project_name}")
    return build_card(header=header, elements=elements)


def _load_or_write_golden(name: str, actual: dict, write: bool = False) -> dict | None:
    """Load expected/<name>.card.json; if write=True or missing, write the actual."""
    EXPECTED_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPECTED_DIR / f"{name}.card.json"
    if write or not path.exists():
        path.write_text(json.dumps(actual, ensure_ascii=False, indent=2), encoding="utf-8")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", [
    "turn_simple",
    "turn_with_read",
    "turn_with_bash_long",
    "turn_with_subagent",
])
def test_golden_card(name, request):
    """Render fixture jsonl and compare to expected golden JSON."""
    fixture = FIXTURES_DIR / f"{name}.jsonl"
    events = list(JsonlEvent.load_file(fixture))
    turns = group_into_turns(events)
    assert turns, f"{name}: no turns produced"
    actual = render_turn_to_card(turns[-1], project_name="test-project")

    # If running with `--update-golden`, overwrite the golden file instead of asserting
    if request.config.getoption("--update-golden", default=False):
        _load_or_write_golden(name, actual, write=True)
        return

    expected = _load_or_write_golden(name, actual, write=False)
    if expected is None:
        # First run — auto-wrote the golden, fail with a hint
        pytest.fail(f"No golden file for {name}. Auto-created — re-run to verify.")
    assert actual == expected, (
        f"{name}: rendered card differs from golden.\n"
        f"Run with --update-golden to accept the new output."
    )


def pytest_addoption(parser):
    parser.addoption("--update-golden", action="store_true", default=False,
                     help="Update golden files instead of comparing")
```

- [ ] **Step 3: First run — auto-writes golden files**

```bash
pytest tests/golden/test_golden_cards.py -xvs
```
Expected: 4 failures, each saying "No golden file for X. Auto-created — re-run to verify."

- [ ] **Step 4: Second run — should pass**

```bash
pytest tests/golden/test_golden_cards.py -xvs
```
Expected: `4 passed`.

- [ ] **Step 5: Inspect generated golden files**

Run:
```bash
ls -la tests/golden/expected/
cat tests/golden/expected/turn_simple.card.json
```
Verify the JSON looks sensible (header, markdown body, optional collapsible tool blocks, note footer).

- [ ] **Step 6: Commit**

```bash
git add tests/golden/
git commit -m "test(rendering): golden fixtures + comparison harness for turn cards"
```

---

### Task 4.6: Promote `render_turn_to_card` to `turn.py`

**Files:**
- Modify: `feishu_bot_claude/rendering/turn.py`
- Modify: `tests/golden/test_golden_cards.py`

The reference implementation `render_turn_to_card` lives in the test for now. Promote it to production.

- [ ] **Step 1: Move function to `turn.py`**

Cut the `render_turn_to_card` function from `tests/golden/test_golden_cards.py` and paste it into `feishu_bot_claude/rendering/turn.py`. Add necessary imports.

In `turn.py`, append:
```python
from feishu_bot_claude.rendering.card import build_card, build_header, build_markdown, build_note
from feishu_bot_claude.rendering.tools import render_tool_block


def render_turn_to_card(turn: Turn, project_name: str = "project", render_style: str = "rich") -> dict:
    """Render a Turn to a Feishu interactive card JSON."""
    elements: list[dict] = []
    for event in turn.assistant_events:
        for part in event.content:
            if part.get("type") == "text" and part.get("text"):
                elements.append(build_markdown(part["text"]))
            elif part.get("type") == "tool_use":
                tool_use = part
                tool_result = None
                for later in turn.assistant_events:
                    for p in later.content:
                        if p.get("type") == "tool_result" and p.get("tool_use_id") == tool_use.get("id"):
                            tool_result = p
                            break
                block = render_tool_block(tool_use, tool_result, render_style=render_style)
                if block is not None:
                    elements.append(block)

    total_in = sum(e.raw.get("usage", {}).get("input_tokens", 0) for e in turn.assistant_events)
    total_out = sum(e.raw.get("usage", {}).get("output_tokens", 0) for e in turn.assistant_events)
    if total_in or total_out:
        elements.append(build_note(f"{total_in}+{total_out} tokens"))

    header = build_header(title=f"🤖 Claude · {project_name}")
    return build_card(header=header, elements=elements)
```

In `tests/golden/test_golden_cards.py`, replace the local function with an import:
```python
from feishu_bot_claude.rendering.turn import render_turn_to_card
```

- [ ] **Step 2: Verify all tests still pass**

```bash
pytest -xvs
```
Expected: all previously-passing tests still pass.

- [ ] **Step 3: Commit**

```bash
git add feishu_bot_claude/rendering/turn.py tests/golden/test_golden_cards.py
git commit -m "refactor(rendering): promote render_turn_to_card to production module"
```

---

### Task 4.7: Phase 4 wrap-up

**Files:**
- Create: `docs/phase-4-summary.md`

- [ ] **Step 1: Write summary**

Create `docs/phase-4-summary.md`:
```markdown
# Phase 4 Summary

**Date completed:** <fill in>

## What's in place

- `rendering/card.py` — 7 atomic JSON builders (header, markdown, divider, note, collapsible, action_buttons, build_card)
- `rendering/turn.py` — `JsonlEvent`, `Turn`, `group_into_turns`, `render_turn_to_card`
- `rendering/tools.py` — `render_tool_block`, per-tool icon map, preview truncation
- `rendering/uploads.py` — `LongOutputPolicy` for inline-vs-upload decisions
- 5 golden fixtures + golden test harness with `--update-golden` flag

## Verification

```bash
pytest tests/unit/test_card_builders.py tests/unit/test_turn_grouping.py \
       tests/unit/test_tool_rendering.py tests/unit/test_uploads.py \
       tests/golden/test_golden_cards.py -v
```

## What's intentionally missing

- No real file upload (uses `LarkCli.update_card`/`send_card` from Phase 3 — invocation happens in Phase 5)
- No confirmation-prompt card (still a TODO; covered in Phase 5 inbound routing)
- No diff rendering for Edit/MultiEdit beyond title detail (Phase 5+ may enhance)

## Next phase preview

Phase 5 — Mirror Pipeline (outbound + inbound):
- `daemon/outbound.py` — tail jsonl, batch events, render turn cards, call `LarkCli`
- `daemon/inbound.py` — drive `lark-cli event consume`, route text/menu/slash to tmux
- Confirmation card with action buttons routed back to tmux as keystrokes
- Token bucket + 11232 backoff in send paths
- End-to-end with FakeTmux + FakeLarkCli
```

- [ ] **Step 2: Commit + tag**

```bash
git add docs/phase-4-summary.md
git commit -m "docs: phase 4 summary"
git tag -a phase-4-complete -m "Phase 4: card rendering complete"
```

---

## Phase 4 Done. Next: Phase 5 — Mirror Pipeline
