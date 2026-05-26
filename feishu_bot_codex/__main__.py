"""Module entry: `python -m feishu_bot_codex {daemon|<cli-op>}`.

When invoked with `daemon` it starts the server. Otherwise it delegates to
the Click CLI (so `python -m feishu_bot_codex ping` works just like
`feishu-bot-claude ping`).
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from feishu_bot_codex.daemon import serve

_DEFAULT_DATA_DIR = Path.home() / ".feishu-bot-claude"


async def _run_daemon() -> None:
    socket_path = Path(os.environ.get(
        "FEISHU_BOT_CLAUDE_SOCKET",
        _DEFAULT_DATA_DIR / "control.sock",
    ))
    bindings_path = Path(os.environ.get(
        "FEISHU_BOT_CLAUDE_BINDINGS",
        _DEFAULT_DATA_DIR / "bindings.toml",
    ))
    data_dir = Path(os.environ.get(
        "FEISHU_BOT_CLAUDE_DATA_DIR",
        _DEFAULT_DATA_DIR,
    ))

    from feishu_bot_codex.config.binding import BindingStore
    from feishu_bot_codex.daemon.orchestrator import Orchestrator
    from feishu_bot_codex.daemon.tmux import RealTmux
    from feishu_bot_codex.daemon.feishu import RealLarkCli
    from feishu_bot_codex.config.keychain import MacOSKeychainStore

    store = BindingStore(bindings_path)
    orchestrator = Orchestrator(
        store=store,
        tmux_factory=lambda name: RealTmux(),
        lark_factory=lambda cfg: RealLarkCli(),
        data_dir=data_dir,
    )

    keychain = MacOSKeychainStore()
    real_lark = RealLarkCli()

    server = await serve(
        socket_path=socket_path,
        bindings_path=bindings_path,
        orchestrator=orchestrator,
        keychain=keychain,
        auth_runner_factory=lambda name: real_lark.auth_bot_new_stream(name),
        menu_pusher=real_lark,
        data_dir=data_dir,
    )
    try:
        # Restore any bindings that were running before the daemon was last stopped
        stale = await orchestrator.restore_from_disk()
        if stale:
            import logging
            logging.getLogger(__name__).warning("Stale bindings (tmux missing): %s", stale)
        async with server:
            await server.serve_forever()
    except asyncio.CancelledError:
        pass
    finally:
        await orchestrator.stop_all()


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "daemon":
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s: %(message)s")
        try:
            asyncio.run(_run_daemon())
        except KeyboardInterrupt:
            pass
        return 0
    # Delegate to Click CLI
    from feishu_bot_codex.cli import main as click_main
    click_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
