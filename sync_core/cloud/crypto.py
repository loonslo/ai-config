"""AICLOUD1: AES-256-GCM with authenticated canonical header and random nonce."""
from __future__ import annotations

import base64
import hashlib
import json
import os

MAGIC = b"AICLOUD1\n"
MAX_BYTES = 256 * 1024 * 1024


def new_key() -> bytes:
    return os.urandom(32)


def key_id(key: bytes) -> str:
    if len(key) != 32:
        raise ValueError("加密密钥必须为 32 字节。")
    return hashlib.sha256(key).hexdigest()[:32]


def recovery_text(key: bytes) -> str:
    key_id(key)
    return "AIK1-" + base64.urlsafe_b64encode(key).decode().rstrip("=")


def recover_key(text: str) -> bytes:
    if not text.startswith("AIK1-") or len(text) != 48:
        raise ValueError("恢复材料格式无效。")
    try:
        key = base64.b64decode(text[5:] + "=", altchars=b"-_", validate=True)
    except ValueError as error:
        raise ValueError("恢复材料格式无效。") from error
    key_id(key)
    if recovery_text(key) != text:
        raise ValueError("恢复材料编码无效。")
    return key


def encrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if len(data) > MAX_BYTES - 4096:
        raise ValueError("加密包过大。")
    nonce = os.urandom(12)
    header = json.dumps({"version": 1, "alg": "AES-256-GCM", "key_id": key_id(key),
                         "nonce": base64.b64encode(nonce).decode(), "size": len(data)}, sort_keys=True, separators=(",", ":")).encode()
    aad = MAGIC + header + b"\n"
    return aad + AESGCM(key).encrypt(nonce, data, aad)


def decrypt(data: bytes, key: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.exceptions import InvalidTag
    if not data.startswith(MAGIC) or len(data) > MAX_BYTES:
        raise ValueError("未知或超限的加密包。")
    try:
        header, cipher = data[len(MAGIC):].split(b"\n", 1)
        if len(header) > 1024:
            raise ValueError("Header too large")
        def pairs(items):
            result = {}
            for name, value in items:
                if name in result:
                    raise ValueError("Duplicate metadata")
                result[name] = value
            return result
        value = json.loads(header, object_pairs_hook=pairs)
        if set(value) != {"version", "alg", "key_id", "nonce", "size"} or type(value["version"]) is not int or value["version"] != 1 or value["alg"] != "AES-256-GCM" or value["key_id"] != key_id(key):
            raise ValueError("Wrong key or metadata")
        nonce = base64.b64decode(value["nonce"], validate=True)
        if len(nonce) != 12 or type(value["size"]) is not int or value["size"] < 0 or len(cipher) != value["size"] + 16:
            raise ValueError("Invalid ciphertext framing")
        return AESGCM(key).decrypt(nonce, cipher, MAGIC + header + b"\n")
    except (ValueError, TypeError, KeyError, InvalidTag) as error:
        raise ValueError("密钥错误或加密包被篡改；未解密、未导入。") from error
