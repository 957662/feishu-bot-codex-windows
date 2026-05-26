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
