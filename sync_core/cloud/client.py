"""Explicit OIDC device login and encrypted transport shared by the desktop RPC."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any
from urllib.parse import urlsplit
import webbrowser

import httpx

from .crypto import decrypt, encrypt, key_id, new_key, recover_key, recovery_text
from .vault import SystemVault
from ..package.check import check_package, _read_regular_file, _reject_reparse
from ..package.importer import SUPPORTED_ADAPTERS
from ..utils import atomic_write

_PENDING_LOGIN: dict[str, dict[str, Any]] = {}
CHUNK = 4 * 1024 * 1024
MAX_BYTES = 256 * 1024 * 1024


def secure_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("服务器和身份地址必须是无凭据的 HTTPS URL。")
    return value.rstrip("/")


def read_upload_package(path: Path):
    """Validate the same bounded archive bytes that will enter encryption."""
    path = path.expanduser().absolute()
    if path.suffix.casefold() != ".aiconfig":
        raise ValueError("请先生成已检查的 .aiconfig 单文件包。")
    for parent in (path, *path.parents):
        _reject_reparse(parent)
    plaintext = _read_regular_file(path, limit=MAX_BYTES - 16384)
    with tempfile.TemporaryDirectory(prefix="ai-config-upload-") as directory:
        stage = Path(directory) / "checked.aiconfig"
        stage.write_bytes(plaintext)
        checked = check_package(stage, supported_adapters=SUPPORTED_ADAPTERS)
    if not checked.importable:
        raise ValueError("上传包包含未支持适配器。")
    return checked, plaintext


class CloudClient:
    def __init__(self, server: str, state: Path, *, vault=None, transport=None) -> None:
        self.server = secure_url(server)
        self.state = state / "cloud"
        self.vault = vault or SystemVault()
        self.http = httpx.Client(timeout=30, follow_redirects=False, transport=transport)

    def close(self) -> None:
        self.http.close()

    def _request(self, method: str, path: str, **kwargs):
        login = self.vault.get(self.server)
        if not login.get("access_token") or login.get("expires", 0) <= time.time():
            raise ValueError("请先登录；身份已过期时需要重新认证。")
        headers = {"Authorization": "Bearer " + login["access_token"]}
        if login.get("device_id"):
            headers["X-AI-Device"] = login["device_id"]
            headers["X-AI-Device-Token"] = login["device_token"]
        response = self.http.request(method, self.server + path, headers=headers, **kwargs)
        if response.status_code >= 300:
            raise ValueError(f"服务器请求未完成（HTTP {response.status_code}）；本机包保留，请重新检查身份、容量或版本。")
        return response

    def begin_login(self, issuer: str, client_id: str, audience: str) -> dict:
        issuer = secure_url(issuer)
        response = self.http.get(issuer + "/.well-known/openid-configuration")
        response.raise_for_status()
        discovery = response.json()
        if discovery.get("issuer", "").rstrip("/") != issuer:
            raise ValueError("OIDC 签发方不匹配。")
        endpoint = secure_url(discovery["device_authorization_endpoint"])
        token_endpoint = secure_url(discovery["token_endpoint"])
        response = self.http.post(endpoint, data={"client_id": client_id, "scope": "openid profile", "audience": audience})
        response.raise_for_status()
        value = response.json()
        verification = secure_url(value["verification_uri"])
        pending = {"device_code": value["device_code"], "client_id": client_id, "endpoint": token_endpoint,
                   "expires": time.time() + min(int(value["expires_in"]), 1800),
                   "interval": max(int(value.get("interval", 5)), 5), "last_poll": 0}
        _PENDING_LOGIN[self.server] = pending
        webbrowser.open(verification)
        return {"state": "awaiting_login", "verification_uri": verification, "user_code": value["user_code"],
                "interval": pending["interval"], "note": "在系统浏览器完成授权，然后点击检查登录；不影响离线功能。"}

    def poll_login(self) -> dict:
        pending = _PENDING_LOGIN.get(self.server)
        if not pending or pending["expires"] <= time.time():
            _PENDING_LOGIN.pop(self.server, None)
            raise ValueError("登录已取消或过期，请重新发起。")
        if time.time() - pending["last_poll"] < pending["interval"]:
            return {"state": "awaiting_login", "interval": pending["interval"]}
        pending["last_poll"] = time.time()
        response = self.http.post(pending["endpoint"], data={"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": pending["device_code"], "client_id": pending["client_id"]})
        value = response.json()
        if value.get("error") in {"authorization_pending", "slow_down"}:
            if value["error"] == "slow_down":
                pending["interval"] += 5
            return {"state": "awaiting_login", "interval": pending["interval"]}
        if value.get("error") or not value.get("access_token") or value.get("token_type", "").casefold() != "bearer":
            _PENDING_LOGIN.pop(self.server, None)
            raise ValueError("授权未完成或被拒绝。")
        login = {"access_token": value["access_token"], "expires": time.time() + int(value.get("expires_in", 300))}
        previous = self.vault.get(self.server)
        self.vault.put(self.server, login)
        try:
            me = self._request("GET", "/v1/me").json()
            login["user_id"] = me["user_id"]
            if previous.get("user_id") == me["user_id"] and previous.get("device_id"):
                login.update(device_id=previous["device_id"], device_token=previous["device_token"])
            else:
                device = self._request("POST", "/v1/devices", json={"name": "AI Config desktop"}).json()
                login.update(device_id=device["device_id"], device_token=device["device_token"])
            self.vault.put(self.server, login)
        except Exception:
            self.vault.delete(self.server)
            raise
        finally:
            _PENDING_LOGIN.pop(self.server, None)
        return {"state": "logged_in", "user_id": login["user_id"], "device_id": login["device_id"]}

    def logout(self) -> dict:
        _PENDING_LOGIN.pop(self.server, None)
        self.vault.delete(self.server)
        return {"state": "logged_out", "note": "登录令牌已移除；恢复密钥保留在对应账号安全存储。"}

    def account(self) -> str:
        login = self.vault.get(self.server)
        if not login.get("user_id"):
            raise ValueError("请先登录。")
        return login["user_id"]

    def key_scope(self, space: str) -> str:
        if not __import__("re").fullmatch(r"[a-f0-9]{32}", space):
            raise ValueError("请选择有效配置空间。")
        return self.account() + ":" + space

    def get_key(self, space: str) -> bytes:
        value = self.vault.get(self.server, self.key_scope(space))
        if "key" not in value:
            raise ValueError("当前账号与空间尚未解锁；请输入对应恢复材料。")
        return base64.b64decode(value["key"], validate=True)

    def generate_key(self, space: str) -> dict:
        account = self.key_scope(space)
        if self.vault.get(self.server, account):
            raise ValueError("该空间已有密钥；请使用恢复材料，不能覆盖历史解密能力。")
        if self._request("GET", f"/v1/spaces/{space}/versions").json():
            raise ValueError("该空间已有云端版本；新设备应输入原恢复材料，不生成替代密钥。")
        key = new_key()
        self.vault.put(self.server, {"key": base64.b64encode(key).decode()}, account)
        return {"state": "unlocked", "key_id": key_id(key), "recovery_material": recovery_text(key),
                "note": "请保存这份恢复材料；所有密钥丢失后，账号登录无法解密旧包。"}

    def unlock(self, space: str, material: str) -> dict:
        key = recover_key(material)
        account = self.key_scope(space)
        existing = self.vault.get(self.server, account)
        if existing and existing.get("key") != base64.b64encode(key).decode():
            raise ValueError("安全存储已有不同密钥；禁止覆盖，请检查所选空间。")
        self.vault.put(self.server, {"key": base64.b64encode(key).decode()}, account)
        return {"state": "unlocked", "key_id": key_id(key)}

    def versions(self, space: str) -> dict:
        self.key_scope(space)
        return {"state": "listed", "head": self._request("GET", f"/v1/spaces/{space}/head").json()["head"],
                "versions": self._request("GET", f"/v1/spaces/{space}/versions").json(),
                "receipts": self._request("GET", f"/v1/spaces/{space}/receipts").json()}

    def upload(self, space: str, path: Path, expected_head: str | None) -> dict:
        checked, plaintext = read_upload_package(path)
        key = self.get_key(space)
        identity = hashlib.sha256(json.dumps([self.server, self.account(), space, expected_head, hashlib.sha256(plaintext).hexdigest(), key_id(key)]).encode()).hexdigest()
        cached = self.state / identity / "upload.enc"
        for parent in (cached, *cached.parents):
            if parent.exists() or parent.is_symlink():
                _reject_reparse(parent)
        if cached.exists():
            ciphertext = _read_regular_file(cached, limit=MAX_BYTES)
            if decrypt(ciphertext, key) != plaintext:
                raise ValueError("续传缓存与本机包不一致，请重新生成导出。")
        else:
            ciphertext = encrypt(plaintext, key)
            atomic_write(cached, ciphertext)
        uploaded = self._request("POST", f"/v1/spaces/{space}/uploads", json={"idempotency_key": identity, "expected_head": expected_head,
                                "size": len(ciphertext), "sha256": hashlib.sha256(ciphertext).hexdigest()}).json()
        upload = uploaded["upload_id"]
        progress = self._request("GET", f"/v1/uploads/{upload}").json()
        if not progress["version_id"]:
            received = set(progress["parts"])
            for number, offset in enumerate(range(0, len(ciphertext), CHUNK)):
                if number not in received:
                    self._request("PUT", f"/v1/uploads/{upload}/parts/{number}", content=ciphertext[offset:offset + CHUNK])
        result = self._request("POST", f"/v1/uploads/{upload}/complete").json()
        return {"state": "cloud_saved", **result, "content_id": checked.validation["content_id"],
                "note": "云端已保存密文；分叉版本不会覆盖当前版本，本机应用和 Agent 加载状态独立。"}

    def download(self, space: str, version: str, destination: Path) -> dict:
        versions = self.versions(space)["versions"]
        selected = next((row for row in versions if row["version_id"] == version), None)
        if selected is None:
            raise ValueError("所选版本不属于当前空间。")
        key = self.get_key(space)
        login = self.vault.get(self.server)
        headers = {"Authorization": "Bearer " + login["access_token"], "X-AI-Device": login["device_id"], "X-AI-Device-Token": login["device_token"]}
        cipher = bytearray()
        with self.http.stream("GET", self.server + f"/v1/versions/{version}/content", headers=headers) as response:
            if response.status_code != 200:
                raise ValueError("下载未完成，请重新登录或稍后重试。")
            for chunk in response.iter_bytes(CHUNK):
                cipher.extend(chunk)
                if len(cipher) > min(selected["size"], MAX_BYTES):
                    raise ValueError("下载包超出声明体积。")
        if len(cipher) != selected["size"] or hashlib.sha256(cipher).hexdigest() != selected["sha256"]:
            raise ValueError("下载包密文完整性校验失败。")
        plaintext = decrypt(bytes(cipher), key)
        target = destination.expanduser().absolute()
        if target.suffix.casefold() != ".aiconfig" or target.exists() or not target.parent.is_dir():
            raise ValueError("请选择新的 .aiconfig 文件名；既有文件保留。")
        for parent in target.parents:
            _reject_reparse(parent)
        fd, filename = tempfile.mkstemp(dir=target.parent, suffix=".aiconfig")
        stage = Path(filename)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(plaintext)
                stream.flush()
                os.fsync(stream.fileno())
            checked = check_package(stage, supported_adapters=SUPPORTED_ADAPTERS)
            if not checked.importable:
                raise ValueError("明文包的适配器不受支持。")
            os.link(stage, target)
        finally:
            stage.unlink(missing_ok=True)
        return {"state": "downloaded", "package_path": str(target), "content_id": checked.validation["content_id"],
                "note": "解密与包检查通过；请进入迁移页面预览，尚未写入 Agent。"}

    def execute(self, action: str, params: dict) -> dict:
        if action == "login":
            return self.begin_login(params["issuer"], params["client_id"], params["audience"])
        if action == "poll_login":
            return self.poll_login()
        if action == "logout":
            return self.logout()
        if action == "spaces":
            return {"state": "listed", "spaces": self._request("GET", "/v1/spaces").json()}
        if action == "create_space":
            return {"state": "space_created", **self._request("POST", "/v1/spaces", json={"name": params["name"]}).json()}
        if action == "generate_key":
            return self.generate_key(params["space"])
        if action == "unlock":
            return self.unlock(params["space"], params["material"])
        if action == "versions":
            return self.versions(params["space"])
        if action == "upload":
            return self.upload(params["space"], Path(params["package_path"]), None if params.get("expected_head") == "none" else params.get("expected_head"))
        if action == "download":
            return self.download(params["space"], params["version"], Path(params["destination"]))
        if action == "devices":
            return {"state": "listed", "devices": self._request("GET", "/v1/devices").json()}
        if action == "revoke":
            return self._request("POST", f"/v1/devices/{params['device']}/revoke").json()
        if action == "receipt":
            login = self.vault.get(self.server)
            return self._request("POST", f"/v1/devices/{login['device_id']}/receipts", json=params["summary"]).json()
        raise ValueError("未知云端操作。")
