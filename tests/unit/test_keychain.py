"""Tests for KeychainStore abstraction with in-memory fake."""

import pytest

from feishu_bot_codex.config.keychain import InMemoryKeychainStore, KeychainStore


def test_in_memory_store_put_and_get():
    store: KeychainStore = InMemoryKeychainStore()
    store.put("svc.alpha", "secret-1")
    assert store.get("svc.alpha") == "secret-1"


def test_in_memory_store_get_missing_returns_none():
    store = InMemoryKeychainStore()
    assert store.get("nonexistent") is None


def test_in_memory_store_overwrites():
    store = InMemoryKeychainStore()
    store.put("svc.alpha", "v1")
    store.put("svc.alpha", "v2")
    assert store.get("svc.alpha") == "v2"


def test_in_memory_store_delete():
    store = InMemoryKeychainStore()
    store.put("svc.alpha", "secret-1")
    store.delete("svc.alpha")
    assert store.get("svc.alpha") is None


def test_in_memory_store_delete_missing_is_noop():
    store = InMemoryKeychainStore()
    store.delete("nonexistent")  # no raise


import subprocess
from unittest.mock import patch

from feishu_bot_codex.config.keychain import MacOSKeychainStore


def _completed(returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


@patch("feishu_bot_codex.config.keychain.subprocess.run")
def test_macos_keychain_put_calls_security_add(mock_run):
    mock_run.return_value = _completed(0)
    store = MacOSKeychainStore(service_prefix="feishu-bot-claude")
    store.put("foo-bot.app_secret", "s3cret")
    call_args = mock_run.call_args[0][0]
    assert call_args[0:2] == ["security", "add-generic-password"]
    assert "-U" in call_args  # update-if-exists
    assert "-a" in call_args and "foo-bot.app_secret" in call_args
    assert "-s" in call_args and "feishu-bot-claude" in call_args
    assert "-w" in call_args and "s3cret" in call_args


@patch("feishu_bot_codex.config.keychain.subprocess.run")
def test_macos_keychain_get_returns_password_on_success(mock_run):
    mock_run.return_value = _completed(0, stdout="s3cret\n")
    store = MacOSKeychainStore(service_prefix="feishu-bot-claude")
    assert store.get("foo-bot.app_secret") == "s3cret"
    call_args = mock_run.call_args[0][0]
    assert call_args[0:2] == ["security", "find-generic-password"]
    assert "-w" in call_args


@patch("feishu_bot_codex.config.keychain.subprocess.run")
def test_macos_keychain_get_returns_none_when_missing(mock_run):
    mock_run.return_value = _completed(44, stderr="security: SecKeychainSearchCopyNext: ...")
    store = MacOSKeychainStore(service_prefix="feishu-bot-claude")
    assert store.get("missing") is None


@patch("feishu_bot_codex.config.keychain.subprocess.run")
def test_macos_keychain_get_raises_on_other_errors(mock_run):
    mock_run.return_value = _completed(1, stderr="permission denied")
    store = MacOSKeychainStore(service_prefix="feishu-bot-claude")
    with pytest.raises(RuntimeError, match="keychain get failed"):
        store.get("foo")


@patch("feishu_bot_codex.config.keychain.subprocess.run")
def test_macos_keychain_delete_succeeds(mock_run):
    mock_run.return_value = _completed(0)
    store = MacOSKeychainStore(service_prefix="feishu-bot-claude")
    store.delete("foo-bot.app_secret")
    call_args = mock_run.call_args[0][0]
    assert call_args[0:2] == ["security", "delete-generic-password"]


@patch("feishu_bot_codex.config.keychain.subprocess.run")
def test_macos_keychain_delete_missing_is_noop(mock_run):
    mock_run.return_value = _completed(44)
    store = MacOSKeychainStore(service_prefix="feishu-bot-claude")
    store.delete("missing")  # no raise


@patch("feishu_bot_codex.config.keychain.subprocess.run")
def test_macos_keychain_put_raises_on_error(mock_run):
    """MacOSKeychainStore.put raises RuntimeError on non-zero exit."""
    mock_run.return_value = _completed(1, stderr="permission denied")
    store = MacOSKeychainStore(service_prefix="feishu-bot-claude")
    with pytest.raises(RuntimeError, match="keychain put failed"):
        store.put("foo-bot.app_secret", "s3cret")


@patch("feishu_bot_codex.config.keychain.subprocess.run")
def test_macos_keychain_delete_raises_on_non_zero_non_44(mock_run):
    """MacOSKeychainStore.delete raises RuntimeError on exit code that is not 0 or 44."""
    mock_run.return_value = _completed(1, stderr="permission denied")
    store = MacOSKeychainStore(service_prefix="feishu-bot-claude")
    with pytest.raises(RuntimeError, match="keychain delete failed"):
        store.delete("foo-bot.app_secret")
