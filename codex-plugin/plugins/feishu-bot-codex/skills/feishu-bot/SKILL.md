---
name: feishu-bot
description: "Bind / manage / mirror the current TUI session to a dedicated Feishu (Lark) bot via the feishu-bot-codex daemon. Use when the user says things like 'bind/create a Feishu bot for this project', '把当前项目绑一个飞书机器人', '启动飞书镜像', '停止飞书镜像', '列出所有飞书机器人 binding', '调整渲染样式', or types fake slash commands like /bot-new, /bot-start, /bot-stop, /bot-list, /bot-config, /bot-remove."
---

# feishu-bot

This skill lets you bridge the current Codex/Claude TUI session to a dedicated Feishu (Lark) bot via the `feishu-bot-codex` CLI. The user controls binding lifecycle (create, start, stop, list, configure, remove); you translate their request into the right CLI call and run it.

> ⚠️ Codex does **not** support user-defined `/bot-*` slash commands — they live as a `commands/` folder, but Codex only auto-registers built-in slashes. Treat any input that looks like `/bot-new`, `/bot-start`, etc. as a request to invoke this skill instead.

## Available actions

Run these via the `Bash` tool, always with `--cwd "$PWD"` (or the user's specified path):

| User intent | Command |
|---|---|
| Bind current project to a new bot (creates a fresh Feishu app via QR scan) | `feishu-bot-codex bind <name> --cwd "$PWD"` |
| List all bindings on this machine | `feishu-bot-codex list` |
| Start the mirror (jsonl → Feishu cards) for current project | `feishu-bot-codex start --cwd "$PWD"` |
| Stop the mirror (TUI keeps running) | `feishu-bot-codex stop --cwd "$PWD"` |
| Adjust binding parameters | `feishu-bot-codex config --cwd "$PWD" <key>=<value>` |
| Remove a binding (Feishu app itself stays) | `feishu-bot-codex unbind <name>` |
| Daemon health check | `feishu-bot-codex ping` |
| Daemon version / uptime | `feishu-bot-codex status` |

Common config keys: `render_style=minimal|rich|full`, `card_throttle_ms=300`, `mute_thinking=false`, `max_message_length=8000`, `allow_users=[...open_ids]`.

## Recognition patterns

Trigger this skill when the user input matches any of:

- Mentions of "feishu", "lark", "飞书", "lark 机器人", "飞书机器人"
- Slash-like syntax: `/bot-new`, `/bot-start`, `/bot-stop`, `/bot-list`, `/bot-config`, `/bot-remove`
- Bind / link / connect / mirror / 镜像 / 绑定 / 绑机器人 verbs together with a project context

## Behavior

1. Read what the user wants exactly — bind, start, stop, list, config, or remove.
2. If they used `/bot-new mybot`, treat `mybot` as the bot name argument.
3. Run the matching command via Bash. Stream stdout/stderr to the user.
4. If `bind` is requested, warn the user that it pops a browser for QR-scan OAuth — they need to scan with the Feishu mobile app.
5. After `bind` succeeds, tell the user to send the **first message** to the new bot in Feishu to bootstrap the binding (the message itself is consumed for bootstrap and not forwarded to Codex).

## Sanity checks

- If `feishu-bot-codex` is not on PATH → tell the user to run `setup.sh` in the project root or install via the published repo.
- If the daemon is not running (ping fails) → suggest `nssm start feishu-bot-codex` (Windows) or `launchctl load ~/Library/LaunchAgents/com.qingyun.feishu-bot-codex.plist` (macOS).
- If `bind` says cwd already bound → tell the user to either pick a different `--cwd` or `unbind` the existing one first.
