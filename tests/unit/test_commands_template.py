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
