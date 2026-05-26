"""Secret storage abstraction with macOS Keychain backend."""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod


class KeychainStore(ABC):
    """Abstract secret store. Backed by macOS Keychain in production."""

    @abstractmethod
    def put(self, key: str, secret: str) -> None:
        """Store or overwrite a secret under `key`."""

    @abstractmethod
    def get(self, key: str) -> str | None:
        """Return the secret for `key`, or None if missing."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete the secret for `key`. No-op if missing."""


class InMemoryKeychainStore(KeychainStore):
    """In-memory store for tests. Not persistent, not secure."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def put(self, key: str, secret: str) -> None:
        self._data[key] = secret

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)


class MacOSKeychainStore(KeychainStore):
    """macOS Keychain backend via the `security` command.

    Each item is stored as a generic password where:
      - `-s` (service) is the shared `service_prefix`
      - `-a` (account) is the per-binding key
    """

    _NOT_FOUND_RETURNCODE = 44  # `security` exit code for "item not found"

    def __init__(self, service_prefix: str = "feishu-bot-claude") -> None:
        self._service = service_prefix

    def put(self, key: str, secret: str) -> None:
        result = subprocess.run(
            [
                "security", "add-generic-password",
                "-U",                 # update if exists
                "-a", key,            # account
                "-s", self._service,  # service
                "-w", secret,         # password (read from arg, not stdin)
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"keychain put failed (exit {result.returncode}): {result.stderr.strip()}"
            )

    def get(self, key: str) -> str | None:
        result = subprocess.run(
            [
                "security", "find-generic-password",
                "-a", key,
                "-s", self._service,
                "-w",  # output password only
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == self._NOT_FOUND_RETURNCODE:
            return None
        if result.returncode != 0:
            raise RuntimeError(
                f"keychain get failed (exit {result.returncode}): {result.stderr.strip()}"
            )
        return result.stdout.rstrip("\n")

    def delete(self, key: str) -> None:
        result = subprocess.run(
            [
                "security", "delete-generic-password",
                "-a", key,
                "-s", self._service,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode in (0, self._NOT_FOUND_RETURNCODE):
            return
        raise RuntimeError(
            f"keychain delete failed (exit {result.returncode}): {result.stderr.strip()}"
        )
