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
