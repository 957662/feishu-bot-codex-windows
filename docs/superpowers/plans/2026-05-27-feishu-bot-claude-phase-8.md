# feishu-bot-claude — Phase 8: Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the system actually usable as a daily tool. After Phase 8, the user can run `./setup.sh` from a fresh checkout and have a working daemon (auto-starting on login), six `/bot-*` slash commands installed globally for Claude Code, and `feishu-bot-claude shell` as an entry to start tmux-wrapped Claude.

**Architecture:** A single `setup.sh` bash script handles install/uninstall/update/doctor flows. It detects platform, ensures dependencies, installs the Python package, copies slash command markdown to `~/.claude/commands/`, generates and loads launchd plist (macOS) or systemd unit (Linux), and runs a health check. Slash commands are pre-written markdown files in `commands/`.

**Prerequisite:** Phase 7 complete (real bind works).

**Scope (Phase 8 deliverables):**
- `commands/bot-{new,list,remove,start,stop,config}.md` (6 files)
- `scripts/install-commands.sh`
- `scripts/launchd.plist` (macOS service definition, template)
- `scripts/systemd.service` (Linux service definition, template)
- `scripts/feishu-bot-claude-shell` (the `feishu-bot-claude shell` implementation — bash helper that starts tmux + claude)
- `setup.sh` (full install/uninstall/update/doctor)
- `docs/install.md` (user-facing install guide)

---

## Phase 8 Tasks

### Task 8.1: commands/*.md slash command files

**Files:**
- Create: `commands/bot-new.md`
- Create: `commands/bot-list.md`
- Create: `commands/bot-remove.md`
- Create: `commands/bot-start.md`
- Create: `commands/bot-stop.md`
- Create: `commands/bot-config.md`
- Create: `tests/unit/test_commands_template.py`

- [ ] **Step 1: Create the six command files**

Create `commands/bot-new.md`:
```markdown
---
allowed-tools: Bash(feishu-bot-claude:*)
description: Bind current project to a new Feishu bot (QR-scan to create app)
argument-hint: <bot-name>
---

!`feishu-bot-claude bind "$ARGUMENTS" --cwd "$PWD"`
```

Create `commands/bot-list.md`:
```markdown
---
allowed-tools: Bash(feishu-bot-claude:*)
description: List all Feishu bot bindings on this machine
---

!`feishu-bot-claude list`
```

Create `commands/bot-remove.md`:
```markdown
---
allowed-tools: Bash(feishu-bot-claude:*)
description: Remove a Feishu bot binding (keeps the Feishu app)
argument-hint: <bot-name>
---

!`feishu-bot-claude unbind "$ARGUMENTS"`
```

Create `commands/bot-start.md`:
```markdown
---
allowed-tools: Bash(feishu-bot-claude:*)
description: Start mirror for the current project
---

!`feishu-bot-claude start --cwd "$PWD"`
```

Create `commands/bot-stop.md`:
```markdown
---
allowed-tools: Bash(feishu-bot-claude:*)
description: Stop mirror for the current project (Claude TUI keeps running)
---

!`feishu-bot-claude stop --cwd "$PWD"`
```

Create `commands/bot-config.md`:
```markdown
---
allowed-tools: Bash(feishu-bot-claude:*)
description: Adjust binding parameters (e.g., render_style=full)
argument-hint: <key=value>
---

!`feishu-bot-claude config --cwd "$PWD" $ARGUMENTS`
```

- [ ] **Step 2: Write a basic structural test**

Create `tests/unit/test_commands_template.py`:
```python
"""Verify the commands/*.md files are well-formed Claude Code slash commands."""

import re
from pathlib import Path

COMMANDS_DIR = Path(__file__).parent.parent.parent / "commands"


def test_all_six_command_files_exist():
    expected = {"bot-new.md", "bot-list.md", "bot-remove.md", "bot-start.md", "bot-stop.md", "bot-config.md"}
    actual = {p.name for p in COMMANDS_DIR.glob("*.md")}
    assert expected.issubset(actual), f"missing: {expected - actual}"


def test_each_command_has_frontmatter():
    """Each .md file must start with a `---` frontmatter block."""
    for path in COMMANDS_DIR.glob("*.md"):
        text = path.read_text()
        assert text.startswith("---\n"), f"{path.name}: no frontmatter"


def test_each_command_has_description():
    """Frontmatter must include a `description` field."""
    pattern = re.compile(r"^description:\s*\S+", re.MULTILINE)
    for path in COMMANDS_DIR.glob("*.md"):
        text = path.read_text()
        assert pattern.search(text), f"{path.name}: missing description"


def test_each_command_has_bash_invocation():
    """Each command body must include a `!\\`feishu-bot-claude ...\\`` shell call."""
    for path in COMMANDS_DIR.glob("*.md"):
        text = path.read_text()
        assert "!`feishu-bot-claude" in text, f"{path.name}: no feishu-bot-claude invocation"


def test_each_command_declares_allowed_tools():
    """allowed-tools frontmatter must whitelist the feishu-bot-claude binary."""
    for path in COMMANDS_DIR.glob("*.md"):
        text = path.read_text()
        assert "allowed-tools: Bash(feishu-bot-claude:*)" in text, f"{path.name}: missing allowed-tools"
```

- [ ] **Step 3: Verify**

```bash
pytest tests/unit/test_commands_template.py -xvs
```
Expected: `5 passed`.

- [ ] **Step 4: Commit**

```bash
git add commands/ tests/unit/test_commands_template.py
git commit -m "feat: add 6 Claude Code slash command templates"
```

---

### Task 8.2: scripts/install-commands.sh

**Files:**
- Create: `scripts/install-commands.sh`
- Create: `tests/unit/test_install_commands_script.py`

- [ ] **Step 1: Write the script**

Create `scripts/install-commands.sh` (chmod +x after):
```bash
#!/usr/bin/env bash
set -euo pipefail

# Copy feishu-bot-claude's slash commands into ~/.claude/commands/.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="$PROJECT_ROOT/commands"
TARGET_DIR="${CLAUDE_COMMANDS_DIR:-$HOME/.claude/commands}"

if [ ! -d "$SOURCE_DIR" ]; then
    echo "ERROR: $SOURCE_DIR does not exist" >&2
    exit 1
fi

mkdir -p "$TARGET_DIR"

installed=0
for src in "$SOURCE_DIR"/*.md; do
    dest="$TARGET_DIR/$(basename "$src")"
    cp -f "$src" "$dest"
    installed=$((installed + 1))
done

echo "Installed $installed slash command(s) into $TARGET_DIR"
echo "Try them in Claude Code: /bot-new, /bot-list, /bot-start, etc."
```

```bash
chmod +x scripts/install-commands.sh
```

- [ ] **Step 2: Write tests**

Create `tests/unit/test_install_commands_script.py`:
```python
"""Tests for scripts/install-commands.sh — copies commands to a target dir."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "install-commands.sh"


def test_install_copies_all_files(tmp_path):
    env = os.environ.copy()
    env["CLAUDE_COMMANDS_DIR"] = str(tmp_path)
    result = subprocess.run([str(SCRIPT)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    files = sorted(p.name for p in tmp_path.glob("*.md"))
    assert files == sorted([
        "bot-config.md", "bot-list.md", "bot-new.md",
        "bot-remove.md", "bot-start.md", "bot-stop.md",
    ])


def test_install_is_idempotent(tmp_path):
    """Running twice yields the same final state."""
    env = os.environ.copy()
    env["CLAUDE_COMMANDS_DIR"] = str(tmp_path)
    for _ in range(2):
        result = subprocess.run([str(SCRIPT)], env=env, capture_output=True, text=True)
        assert result.returncode == 0
    files = sorted(p.name for p in tmp_path.glob("*.md"))
    assert len(files) == 6
```

- [ ] **Step 3: Verify**

```bash
pytest tests/unit/test_install_commands_script.py -xvs
```
Expected: `2 passed`.

- [ ] **Step 4: Commit**

```bash
git add scripts/install-commands.sh tests/unit/test_install_commands_script.py
git commit -m "feat: install-commands.sh copies slash commands to ~/.claude/commands"
```

---

### Task 8.3: launchd.plist and systemd.service templates

**Files:**
- Create: `scripts/launchd.plist`
- Create: `scripts/systemd.service`
- Create: `scripts/feishu-bot-claude-shell`

- [ ] **Step 1: launchd plist template (macOS)**

Create `scripts/launchd.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.qingyun.feishu-bot-claude</string>
    <key>ProgramArguments</key>
    <array>
        <string>__PYTHON__</string>
        <string>-m</string>
        <string>feishu_bot_claude</string>
        <string>daemon</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>__HOME__/.feishu-bot-claude/logs/daemon.out.log</string>
    <key>StandardErrorPath</key>
    <string>__HOME__/.feishu-bot-claude/logs/daemon.err.log</string>
    <key>WorkingDirectory</key>
    <string>__HOME__</string>
</dict>
</plist>
```

`__PYTHON__` and `__HOME__` are placeholders that `setup.sh` substitutes.

- [ ] **Step 2: systemd unit template (Linux)**

Create `scripts/systemd.service`:
```ini
[Unit]
Description=feishu-bot-claude daemon
After=network.target

[Service]
Type=simple
ExecStart=__PYTHON__ -m feishu_bot_claude daemon
Restart=on-failure
RestartSec=5
StandardOutput=append:__HOME__/.feishu-bot-claude/logs/daemon.log
StandardError=append:__HOME__/.feishu-bot-claude/logs/daemon.err.log

[Install]
WantedBy=default.target
```

- [ ] **Step 3: `feishu-bot-claude-shell` helper script**

Create `scripts/feishu-bot-claude-shell` (this is what `feishu-bot-claude shell` ultimately invokes):
```bash
#!/usr/bin/env bash
set -euo pipefail

# Launch a tmux session named claude-<basename(cwd)> with `claude` running inside.
# Idempotent: if the session exists, attaches instead.

if ! command -v tmux >/dev/null 2>&1; then
    echo "ERROR: tmux not installed. Install with: brew install tmux  (or apt install tmux)" >&2
    exit 1
fi

if ! command -v claude >/dev/null 2>&1; then
    echo "ERROR: claude (Claude Code CLI) not on PATH. See https://docs.claude.com/en/docs/claude-code" >&2
    exit 1
fi

CWD="${1:-$PWD}"
NAME="claude-$(basename "$CWD")"

cd "$CWD"

if tmux has-session -t "$NAME" 2>/dev/null; then
    echo "Attaching to existing tmux session: $NAME"
    exec tmux attach -t "$NAME"
else
    echo "Creating tmux session: $NAME"
    exec tmux new-session -A -s "$NAME" -c "$CWD" claude
fi
```

```bash
chmod +x scripts/feishu-bot-claude-shell
```

- [ ] **Step 4: Commit**

```bash
git add scripts/launchd.plist scripts/systemd.service scripts/feishu-bot-claude-shell
git commit -m "feat: launchd plist, systemd unit, and shell helper scripts"
```

---

### Task 8.4: setup.sh full implementation

**Files:**
- Create: `setup.sh`

- [ ] **Step 1: Write setup.sh**

Create `setup.sh`:
```bash
#!/usr/bin/env bash
# setup.sh — install/upgrade/uninstall/doctor for feishu-bot-claude.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ACTION="${1:-install}"

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

detect_os() {
    case "$(uname -s)" in
        Darwin) echo "macos" ;;
        Linux)  echo "linux" ;;
        *)      echo "unsupported" ;;
    esac
}

need_cmd() {
    local missing=()
    for cmd in "$@"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            missing+=("$cmd")
        fi
    done
    if [ ${#missing[@]} -gt 0 ]; then
        echo "ERROR: missing required commands: ${missing[*]}" >&2
        echo "On macOS:   brew install ${missing[*]}" >&2
        echo "On Linux:   apt install ${missing[*]}    (or your distro's equivalent)" >&2
        return 1
    fi
}

ensure_lark_cli() {
    if command -v lark-cli >/dev/null 2>&1; then
        echo "[ok] lark-cli already installed: $(lark-cli --version | head -1)"
    else
        echo "[install] lark-cli via npm..."
        npm install -g @larksuite/cli
    fi
}

install_python_pkg() {
    if [ ! -d .venv ]; then
        echo "[install] creating .venv..."
        python3 -m venv .venv
    fi
    # shellcheck source=/dev/null
    source .venv/bin/activate
    echo "[install] pip install -e .[dev]"
    pip install --quiet --upgrade pip
    pip install --quiet -e ".[dev]"
}

install_slash_commands() {
    bash scripts/install-commands.sh
}

install_launchd() {
    local plist_src="scripts/launchd.plist"
    local plist_dst="$HOME/Library/LaunchAgents/com.qingyun.feishu-bot-claude.plist"
    local python_bin="$SCRIPT_DIR/.venv/bin/python"
    mkdir -p "$HOME/Library/LaunchAgents"
    mkdir -p "$HOME/.feishu-bot-claude/logs"
    sed -e "s|__PYTHON__|$python_bin|g" -e "s|__HOME__|$HOME|g" "$plist_src" > "$plist_dst"
    launchctl unload "$plist_dst" 2>/dev/null || true
    launchctl load "$plist_dst"
    echo "[ok] launchd service loaded: $plist_dst"
}

install_systemd() {
    local svc_src="scripts/systemd.service"
    local svc_dst="$HOME/.config/systemd/user/feishu-bot-claude.service"
    local python_bin="$SCRIPT_DIR/.venv/bin/python"
    mkdir -p "$HOME/.config/systemd/user"
    mkdir -p "$HOME/.feishu-bot-claude/logs"
    sed -e "s|__PYTHON__|$python_bin|g" -e "s|__HOME__|$HOME|g" "$svc_src" > "$svc_dst"
    systemctl --user daemon-reload
    systemctl --user enable --now feishu-bot-claude.service
    echo "[ok] systemd user service enabled: $svc_dst"
}

install_service() {
    local os; os="$(detect_os)"
    case "$os" in
        macos) install_launchd ;;
        linux) install_systemd ;;
        *)     echo "WARN: unsupported OS $os; daemon must be started manually." ;;
    esac
}

wait_for_socket() {
    local sock="$HOME/.feishu-bot-claude/control.sock"
    local deadline=$((SECONDS + 10))
    while [ "$SECONDS" -lt "$deadline" ]; do
        if [ -S "$sock" ]; then
            echo "[ok] socket appeared: $sock"
            return 0
        fi
        sleep 0.5
    done
    echo "WARN: socket did not appear within 10s. Check logs in $HOME/.feishu-bot-claude/logs/" >&2
    return 1
}

# -----------------------------------------------------------------------------
# Actions
# -----------------------------------------------------------------------------

action_install() {
    need_cmd python3 node tmux
    ensure_lark_cli
    install_python_pkg
    install_slash_commands
    install_service
    wait_for_socket || true
    echo ""
    echo "✅ feishu-bot-claude installed."
    echo "Next steps:"
    echo "  cd <your-project>"
    echo "  feishu-bot-claude shell    # opens tmux + Claude Code"
    echo "  /bot-new <name>            # inside Claude TUI"
}

action_uninstall() {
    local os; os="$(detect_os)"
    case "$os" in
        macos)
            launchctl unload "$HOME/Library/LaunchAgents/com.qingyun.feishu-bot-claude.plist" 2>/dev/null || true
            rm -f "$HOME/Library/LaunchAgents/com.qingyun.feishu-bot-claude.plist"
            ;;
        linux)
            systemctl --user disable --now feishu-bot-claude.service 2>/dev/null || true
            rm -f "$HOME/.config/systemd/user/feishu-bot-claude.service"
            systemctl --user daemon-reload 2>/dev/null || true
            ;;
    esac
    rm -f "$HOME/.feishu-bot-claude/control.sock"
    echo "✅ Daemon stopped and service files removed."
    echo "Bindings preserved at: $HOME/.feishu-bot-claude/bindings.toml"
    echo "Slash commands kept at: $HOME/.claude/commands/bot-*.md"
}

action_update() {
    git pull --ff-only
    install_python_pkg
    install_slash_commands
    action_doctor
    echo "✅ Update complete. Daemon will auto-restart on the next file change."
}

action_doctor() {
    echo "[check] python3:       $(command -v python3 || echo MISSING)"
    echo "[check] tmux:          $(command -v tmux || echo MISSING)"
    echo "[check] node:          $(command -v node || echo MISSING)"
    echo "[check] lark-cli:      $(command -v lark-cli || echo MISSING)"
    echo "[check] claude:        $(command -v claude || echo MISSING)"
    echo "[check] socket:        $([ -S "$HOME/.feishu-bot-claude/control.sock" ] && echo OK || echo MISSING)"
    echo "[check] bindings.toml: $([ -f "$HOME/.feishu-bot-claude/bindings.toml" ] && echo OK || echo NONE)"
    if [ -S "$HOME/.feishu-bot-claude/control.sock" ]; then
        # shellcheck source=/dev/null
        [ -f .venv/bin/activate ] && source .venv/bin/activate
        feishu-bot-claude ping || echo "WARN: daemon socket exists but ping failed"
    fi
}

case "$ACTION" in
    install)   action_install ;;
    uninstall|--uninstall) action_uninstall ;;
    update|--update)       action_update ;;
    doctor|--doctor)       action_doctor ;;
    *) echo "Usage: $0 [install|uninstall|update|doctor]" >&2; exit 1 ;;
esac
```

```bash
chmod +x setup.sh
```

- [ ] **Step 2: Smoke test (dry run on macOS — skip actual launchctl)**

Test that doctor at least runs without crashing:
```bash
./setup.sh doctor
```
Expected: prints check rows; some may say MISSING which is fine.

- [ ] **Step 3: Commit**

```bash
git add setup.sh
git commit -m "feat: setup.sh — install/uninstall/update/doctor entry"
```

---

### Task 8.5: `feishu-bot-claude shell` op wiring

**Files:**
- Modify: `feishu_bot_claude/cli.py`
- Modify: `feishu_bot_claude/daemon/handlers.py`

- [ ] **Step 1: Real `shell` handler**

Replace `handle_shell` in `feishu_bot_claude/daemon/handlers.py` with a handler that emits an instructional `LogEvent` plus the path to the shell script (so the CLI can `exec` it).

Actually — there's a simpler approach: the `shell` op doesn't need the daemon at all. Have `cli.py shell` invoke `scripts/feishu-bot-claude-shell` directly without going through the socket.

In `feishu_bot_claude/cli.py`, replace the `shell` command:
```python
@main.command(help="Start tmux + claude shell for current project")
@click.option("--cwd", default=None, type=click.Path(path_type=Path))
@click.pass_context
def shell(ctx, cwd):
    # `shell` doesn't go through the daemon — it's a thin tmux wrapper.
    import shutil
    target = cwd or Path(os.getcwd())
    script = Path(__file__).resolve().parent.parent / "scripts" / "feishu-bot-claude-shell"
    if not script.exists():
        # Editable install — check the installed scripts dir alternative.
        click.echo(f"ERROR: shell helper not found at {script}", err=True)
        sys.exit(2)
    os.execv(str(script), [str(script), str(target)])
```

- [ ] **Step 2: Commit**

```bash
git add feishu_bot_claude/cli.py feishu_bot_claude/daemon/handlers.py
git commit -m "feat(cli): shell op execs tmux helper directly"
```

---

### Task 8.6: Phase 8 wrap-up

**Files:**
- Create: `docs/install.md`
- Create: `docs/phase-8-summary.md`

- [ ] **Step 1: User-facing install guide**

Create `docs/install.md`:
```markdown
# feishu-bot-claude — Install Guide

## Prerequisites

- macOS (preferred) or Linux
- Python 3.11+
- tmux
- Node.js (for lark-cli)
- Claude Code (`claude` on PATH)
- A Feishu (Lark) account (China version — `open.feishu.cn`)

## Install

```bash
git clone <repo> ~/project/feishu-bot-claude
cd ~/project/feishu-bot-claude
./setup.sh
```

This:
1. Installs `lark-cli` globally via npm
2. Creates a Python venv, installs `feishu-bot-claude` in editable mode
3. Copies `bot-*` slash commands to `~/.claude/commands/`
4. Installs daemon as a launchd service (macOS) or systemd user unit (Linux)
5. Verifies the daemon is up

## First-time per-project setup

```bash
cd ~/project/your-project
feishu-bot-claude shell
# Inside Claude Code TUI:
/bot-new my-project-bot
# Scan the QR with Feishu mobile
/bot-start
```

## Common commands

- `/bot-list` — show all bindings
- `/bot-start`, `/bot-stop` — control mirror
- `/bot-config render_style=full` — tweak parameters
- `/bot-remove <name>` — delete a binding (Feishu app stays)

## Troubleshooting

- `./setup.sh doctor` — runs a full system check
- Logs: `~/.feishu-bot-claude/logs/daemon.{out,err}.log`
- Reset daemon: `./setup.sh uninstall && ./setup.sh install`

## Uninstall

```bash
./setup.sh uninstall
```
Bindings and slash commands are preserved. Delete `~/.feishu-bot-claude/` to fully clean.
```

- [ ] **Step 2: Phase 8 summary**

Create `docs/phase-8-summary.md`:
```markdown
# Phase 8 Summary

**Date completed:** <fill in>

## What's in place

- `commands/bot-*.md` (6 files) — Claude Code user-level slash commands
- `scripts/install-commands.sh` — idempotent installer for slash commands
- `scripts/launchd.plist` — macOS service template
- `scripts/systemd.service` — Linux service template
- `scripts/feishu-bot-claude-shell` — tmux + claude wrapper
- `setup.sh` — full install/uninstall/update/doctor entry
- `docs/install.md` — user-facing install guide

After Phase 8, a user can:
```bash
git clone <repo> && cd <repo>
./setup.sh
cd ~/some-project
feishu-bot-claude shell
# inside Claude:
/bot-new myproject
/bot-start
```
…and be fully mirrored to Feishu.

## What's intentionally missing (Phase 9)

- Persistent state recovery (daemon restart picks up running bindings)
- Rate-limit hardening (TokenBucket already exists, but isn't always applied)
- Security opt-in fields (allow_users whitelist, dangerous-command confirm)
- Stale binding detection + Feishu warning card
- Comprehensive end-to-end e2e test with real lark-cli
```

- [ ] **Step 3: Commit + tag**

```bash
git add docs/install.md docs/phase-8-summary.md
git commit -m "docs: phase 8 install guide + summary"
git tag -a phase-8-complete -m "Phase 8: distribution + setup.sh complete"
```

---

## Phase 8 Done. Next: Phase 9 — Hardening
