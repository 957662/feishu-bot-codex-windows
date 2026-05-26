"""Real lark-cli smoke test — only verifies subprocess startup, no Feishu auth required."""

import shutil

import pytest

from feishu_bot_codex.daemon.feishu import RealLarkCli

pytestmark = pytest.mark.skipif(
    shutil.which("lark-cli") is None,
    reason="lark-cli not installed (run `npm install -g @larksuite/cli`)",
)


@pytest.mark.asyncio
async def test_lark_cli_help_succeeds():
    """`lark-cli --help` should exit 0 — proves binary is on PATH and runnable."""
    lark = RealLarkCli()
    out, code = await lark._run_raw(["--help"], timeout=5.0)
    assert code == 0
    assert "lark-cli" in out.lower() or "usage" in out.lower()


@pytest.mark.asyncio
async def test_lark_cli_version_format():
    lark = RealLarkCli()
    out, code = await lark._run_raw(["--version"], timeout=5.0)
    assert code == 0
    assert any(c.isdigit() for c in out)
