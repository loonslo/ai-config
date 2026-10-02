"""Secrets are scoped by server / verified account, never saved in device JSON."""
from __future__ import annotations

import hashlib
import json


def scope(server: str, account: str = "login") -> str:
    return hashlib.sha256((server + "\x00" + account).encode()).hexdigest()


class SystemVault:
    service = "io.ai-config.cloud.v1"

    def _backend(self):
        import keyring
        backend = keyring.get_keyring()
        # Fail closed if somebody installed a plaintext third-party backend.
        allowed = ("keyring.backends.Windows", "keyring.backends.macOS", "keyring.backends.SecretService")
        if not type(backend).__module__.startswith(allowed):
            raise ValueError("当前系统安全存储不可用；离线功能仍可使用。")
        return keyring

    def get(self, server: str, account: str = "login") -> dict:
        raw = self._backend().get_password(self.service, scope(server, account))
        return json.loads(raw) if raw else {}

    def put(self, server: str, value: dict, account: str = "login") -> None:
        self._backend().set_password(self.service, scope(server, account), json.dumps(value))

    def delete(self, server: str, account: str = "login") -> None:
        backend = self._backend()
        if backend.get_password(self.service, scope(server, account)) is not None:
            backend.delete_password(self.service, scope(server, account))
