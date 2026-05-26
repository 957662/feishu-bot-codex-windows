#!/usr/bin/env bash
set -euo pipefail

# Install slash commands for both Claude Code and Codex CLI.
#
# Claude Code reads markdown files directly from ~/.claude/commands/.
# Codex CLI registers them through a marketplace / plugin handshake.
# We cover both — silently skipping whichever CLI isn't installed.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="$PROJECT_ROOT/commands"
MARKETPLACE_DIR="$PROJECT_ROOT/codex-plugin"

if [ ! -d "$SOURCE_DIR" ]; then
    echo "ERROR: $SOURCE_DIR does not exist" >&2
    exit 1
fi

# ---- Claude Code: copy markdown into ~/.claude/commands/ ----
if command -v claude >/dev/null 2>&1; then
    TARGET_DIR="${CLAUDE_COMMANDS_DIR:-$HOME/.claude/commands}"
    mkdir -p "$TARGET_DIR"
    installed=0
    for src in "$SOURCE_DIR"/*.md; do
        cp -f "$src" "$TARGET_DIR/$(basename "$src")"
        installed=$((installed + 1))
    done
    echo "✅ Installed $installed slash command(s) into $TARGET_DIR (Claude Code)"
else
    echo "ℹ️  claude CLI not on PATH — skipping ~/.claude/commands/ install"
fi

# ---- Codex CLI: register marketplace + install plugin ----
if command -v codex >/dev/null 2>&1; then
    if [ -f "$MARKETPLACE_DIR/.agents/plugins/marketplace.json" ]; then
        # Remove + re-add so the local path is always fresh after a git pull.
        echo "↻ Registering Codex marketplace at $MARKETPLACE_DIR"
        codex plugin marketplace remove feishu-bot-codex >/dev/null 2>&1 || true
        if codex plugin marketplace add "$MARKETPLACE_DIR" >/dev/null 2>&1; then
            echo "   marketplace added"
        else
            echo "   ⚠️  marketplace add failed — see codex output above"
        fi
        echo "↻ Installing plugin feishu-bot-codex"
        if codex plugin add "feishu-bot-codex@feishu-bot-codex" >/dev/null 2>&1; then
            echo "✅ Plugin feishu-bot-codex installed in Codex"
            echo "   Try: open Codex TUI and type /bot-new <name>"
        else
            echo "⚠️  codex plugin add failed. Manual fallback:"
            echo "   codex plugin marketplace add $MARKETPLACE_DIR"
            echo "   codex plugin add feishu-bot-codex@feishu-bot-codex"
        fi
    else
        echo "WARN: $MARKETPLACE_DIR/.agents/plugins/marketplace.json not found — Codex install skipped"
    fi
else
    echo "ℹ️  codex CLI not on PATH — skipping Codex plugin install"
fi
