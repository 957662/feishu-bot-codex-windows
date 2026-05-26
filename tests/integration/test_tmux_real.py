"""Real tmux smoke test — requires `tmux` binary on PATH."""

import shutil
import time
import uuid

import pytest

from feishu_bot_codex.daemon.tmux import RealTmux

pytestmark = pytest.mark.skipif(
    shutil.which("tmux") is None,
    reason="tmux not installed",
)


def test_real_tmux_lifecycle():
    """Create → has_session → send_keys → kill_session lifecycle works."""
    session = f"fbc-test-{uuid.uuid4().hex[:8]}"
    tmux = RealTmux()
    try:
        assert tmux.has_session(session) is False
        tmux.new_session(name=session, cwd="/tmp", command="sleep 30")
        assert tmux.has_session(session) is True
        tmux.send_keys(session=session, keys="echo hi\n")
        time.sleep(0.1)
    finally:
        tmux.kill_session(session)
        assert tmux.has_session(session) is False


def test_real_tmux_new_session_rejects_duplicate():
    session = f"fbc-test-{uuid.uuid4().hex[:8]}"
    tmux = RealTmux()
    try:
        tmux.new_session(name=session, cwd="/tmp", command="sleep 30")
        with pytest.raises(ValueError, match="already exists"):
            tmux.new_session(name=session, cwd="/tmp", command="sleep 30")
    finally:
        tmux.kill_session(session)


def test_real_tmux_new_session_attaches_if_requested():
    """attach_if_exists=True on existing session is a no-op."""
    session = f"fbc-test-{uuid.uuid4().hex[:8]}"
    tmux = RealTmux()
    try:
        tmux.new_session(name=session, cwd="/tmp", command="sleep 30")
        tmux.new_session(name=session, cwd="/tmp", command="sleep 30", attach_if_exists=True)
        assert tmux.has_session(session) is True
    finally:
        tmux.kill_session(session)


def test_real_tmux_send_keys_to_missing_session_raises():
    tmux = RealTmux()
    with pytest.raises(RuntimeError, match="no session"):
        tmux.send_keys(session="absolutely-not-existing-abcxyz", keys="x")
