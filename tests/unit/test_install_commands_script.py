"""Tests for scripts/install-commands.sh — copies commands to a target dir."""

import os
import subprocess
from pathlib import Path

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
