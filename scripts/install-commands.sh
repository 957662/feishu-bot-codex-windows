#!/usr/bin/env bash
set -euo pipefail

# Install slash / skill commands for feishu-bot-codex.
#
# - Codex CLI gets the plugin + skill via the marketplace mechanism.
# - We deliberately DO NOT touch ~/.claude/commands/ here. If the user is
#   running feishu-bot-claude side by side, our codex variant of the
#   commands would shadow Claude's — breaking that install. Claude users
#   should install feishu-bot-claude instead.
#
# If you want Claude Code's /bot-* commands to drive *both* feishu-bot-claude
# AND feishu-bot-codex (e.g. via different binding names), install both
# repos: feishu-bot-claude handles ~/.claude/commands/, this repo handles
# the codex plugin. They live in separate daemons / data dirs by design.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MARKETPLACE_DIR="$PROJECT_ROOT/codex-plugin"

# ---- Codex CLI: register marketplace + install plugin ----
if command -v codex >/dev/null 2>&1; then
    if [ -f "$MARKETPLACE_DIR/.agents/plugins/marketplace.json" ]; then
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
            echo "   Open Codex TUI and type (WITHOUT leading slash): bot-new <name>"
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

# ---- Notice for Claude Code users ----
if command -v claude >/dev/null 2>&1; then
    echo ""
    echo "ℹ️  Detected Claude Code on PATH."
    echo "   feishu-bot-codex deliberately leaves ~/.claude/commands/ alone so it"
    echo "   doesn't clobber feishu-bot-claude's bot-*.md files."
    echo "   If you want Claude's /bot-* slash commands, install"
    echo "   https://github.com/957662/feishu-bot-claude separately."
fi
