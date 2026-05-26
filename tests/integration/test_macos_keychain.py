"""Real macOS Keychain integration test.

Runs only on darwin. Uses a unique service prefix to avoid clashing with
production keys. Cleans up after itself.
"""

import platform
import uuid

import pytest

from feishu_bot_codex.config.keychain import MacOSKeychainStore

pytestmark = pytest.mark.skipif(
    platform.system() != "Darwin",
    reason="MacOSKeychainStore only runs on macOS",
)


def test_macos_keychain_full_lifecycle():
    """put → get → overwrite → get → delete → get should all behave correctly."""
    # Use a unique prefix so this test never collides with real data.
    prefix = f"feishu-bot-claude-test-{uuid.uuid4().hex[:8]}"
    store = MacOSKeychainStore(service_prefix=prefix)
    key = "lifecycle-key"

    try:
        # missing initially
        assert store.get(key) is None

        # put
        store.put(key, "v1")
        assert store.get(key) == "v1"

        # overwrite
        store.put(key, "v2")
        assert store.get(key) == "v2"

        # delete
        store.delete(key)
        assert store.get(key) is None

        # delete missing again — no-op
        store.delete(key)
    finally:
        # Defensive cleanup in case any step failed mid-way
        store.delete(key)
