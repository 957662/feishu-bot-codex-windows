#!/usr/bin/env bash
# setup.sh — install/upgrade/uninstall/doctor for feishu-bot-codex.
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
        echo "[ok] lark-cli already installed: $(lark-cli --version 2>/dev/null | head -1 || echo present)"
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

# Pick a global bin directory that's on most users' PATH.
# Apple Silicon Homebrew → /opt/homebrew/bin
# Intel Homebrew / Linux → /usr/local/bin
# Last resort → ~/.local/bin (usually on PATH from .zshrc/.bashrc)
global_bin_dir() {
    for d in /opt/homebrew/bin /usr/local/bin; do
        if [ -d "$d" ] && [ -w "$d" ]; then
            echo "$d"
            return 0
        fi
    done
    mkdir -p "$HOME/.local/bin"
    echo "$HOME/.local/bin"
}

install_global_symlink() {
    local target="$SCRIPT_DIR/.venv/bin/feishu-bot-codex"
    local bin_dir; bin_dir="$(global_bin_dir)"
    local link="$bin_dir/feishu-bot-codex"
    if [ ! -x "$target" ]; then
        echo "WARN: $target not found; skipping symlink" >&2
        return
    fi
    ln -sf "$target" "$link"
    echo "[ok] symlink: $link → $target"
    if ! command -v feishu-bot-codex >/dev/null 2>&1; then
        echo "WARN: $link is not on your PATH. Add $bin_dir to PATH in your shell rc." >&2
    fi
}

install_slash_commands() {
    bash scripts/install-commands.sh
}

install_launchd() {
    local plist_src="scripts/launchd.plist"
    local plist_dst="$HOME/Library/LaunchAgents/com.qingyun.feishu-bot-codex.plist"
    local python_bin="$SCRIPT_DIR/.venv/bin/python"
    mkdir -p "$HOME/Library/LaunchAgents"
    mkdir -p "$HOME/.feishu-bot-codex/logs"
    sed -e "s|__PYTHON__|$python_bin|g" -e "s|__HOME__|$HOME|g" "$plist_src" > "$plist_dst"
    launchctl unload "$plist_dst" 2>/dev/null || true
    launchctl load "$plist_dst"
    echo "[ok] launchd service loaded: $plist_dst"
}

install_systemd() {
    local svc_src="scripts/systemd.service"
    local svc_dst="$HOME/.config/systemd/user/feishu-bot-codex.service"
    local python_bin="$SCRIPT_DIR/.venv/bin/python"
    mkdir -p "$HOME/.config/systemd/user"
    mkdir -p "$HOME/.feishu-bot-codex/logs"
    sed -e "s|__PYTHON__|$python_bin|g" -e "s|__HOME__|$HOME|g" "$svc_src" > "$svc_dst"
    systemctl --user daemon-reload
    systemctl --user enable --now feishu-bot-codex.service
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
    local sock="$HOME/.feishu-bot-codex/control.sock"
    local deadline=$((SECONDS + 10))
    while [ "$SECONDS" -lt "$deadline" ]; do
        if [ -S "$sock" ]; then
            echo "[ok] socket appeared: $sock"
            return 0
        fi
        sleep 0.5
    done
    echo "WARN: socket did not appear within 10s. Check logs in $HOME/.feishu-bot-codex/logs/" >&2
    return 1
}

# -----------------------------------------------------------------------------
# Actions
# -----------------------------------------------------------------------------

action_install() {
    need_cmd python3 node tmux
    ensure_lark_cli
    install_python_pkg
    install_global_symlink
    install_slash_commands
    install_service
    wait_for_socket || true
    echo ""
    echo "✅ feishu-bot-codex installed."
    echo "Next steps:"
    echo "  cd <your-project>"
    echo "  feishu-bot-codex shell             # opens tmux + Codex (default)"
    echo "  feishu-bot-codex shell --agent claude   # or with Claude Code"
    echo "  /bot-new <name>                    # inside Codex/Claude TUI"
}

action_uninstall() {
    local os; os="$(detect_os)"
    case "$os" in
        macos)
            launchctl unload "$HOME/Library/LaunchAgents/com.qingyun.feishu-bot-codex.plist" 2>/dev/null || true
            rm -f "$HOME/Library/LaunchAgents/com.qingyun.feishu-bot-codex.plist"
            ;;
        linux)
            systemctl --user disable --now feishu-bot-codex.service 2>/dev/null || true
            rm -f "$HOME/.config/systemd/user/feishu-bot-codex.service"
            systemctl --user daemon-reload 2>/dev/null || true
            ;;
    esac
    # Remove the global symlink (only if it points at our venv)
    for d in /opt/homebrew/bin /usr/local/bin "$HOME/.local/bin"; do
        local link="$d/feishu-bot-codex"
        if [ -L "$link" ] && [[ "$(readlink "$link")" == *"feishu-bot-codex/.venv/bin/feishu-bot-codex"* ]]; then
            rm -f "$link"
            echo "[ok] removed symlink: $link"
        fi
    done
    rm -f "$HOME/.feishu-bot-codex/control.sock"
    echo "✅ Daemon stopped and service files removed."
    echo "Bindings preserved at: $HOME/.feishu-bot-codex/bindings.toml"
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
    echo "[check] python3:           $(command -v python3 || echo MISSING)"
    echo "[check] tmux:              $(command -v tmux || echo MISSING)"
    echo "[check] node:              $(command -v node || echo MISSING)"
    echo "[check] lark-cli:          $(command -v lark-cli || echo MISSING)"
    echo "[check] codex:             $(command -v codex || echo MISSING)"
    echo "[check] claude (optional): $(command -v claude || echo MISSING)"
    echo "[check] feishu-bot-codex: $(command -v feishu-bot-codex || echo 'MISSING (run ./setup.sh install)')"
    echo "[check] socket:            $([ -S "$HOME/.feishu-bot-codex/control.sock" ] && echo OK || echo MISSING)"
    echo "[check] bindings.toml:     $([ -f "$HOME/.feishu-bot-codex/bindings.toml" ] && echo OK || echo NONE)"
    # Daemon must be able to find lark-cli + tmux on its own PATH
    local plist="$HOME/Library/LaunchAgents/com.qingyun.feishu-bot-codex.plist"
    if [ -f "$plist" ]; then
        if grep -q "EnvironmentVariables" "$plist"; then
            echo "[check] launchd PATH env:  OK"
        else
            echo "[check] launchd PATH env:  MISSING (re-run ./setup.sh install to fix)"
        fi
    fi
    if [ -S "$HOME/.feishu-bot-codex/control.sock" ]; then
        # shellcheck source=/dev/null
        [ -f .venv/bin/activate ] && source .venv/bin/activate
        feishu-bot-codex ping || echo "WARN: daemon socket exists but ping failed"
    fi
}

case "$ACTION" in
    install)   action_install ;;
    uninstall|--uninstall) action_uninstall ;;
    update|--update)       action_update ;;
    doctor|--doctor)       action_doctor ;;
    *) echo "Usage: $0 [install|uninstall|update|doctor]" >&2; exit 1 ;;
esac
