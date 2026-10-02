from __future__ import annotations
import hashlib

import pytest
pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")
pytest.importorskip("httpx")
pytest.importorskip("jwt")
pytest.importorskip("cryptography")
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from server.app import Settings, create_app
from server.models import User
from sync_core.cloud.crypto import decrypt, encrypt, new_key, recover_key, recovery_text


def test_encryption_recovery_and_tamper_rejection():
    key = new_key()
    cipher = encrypt(b"portable configuration", key)
    assert decrypt(cipher, recover_key(recovery_text(key))) == b"portable configuration"
    assert cipher != encrypt(b"portable configuration", key)
    for damaged, wrong_key in ((cipher[:-1] + bytes([cipher[-1] ^ 1]), key), (cipher, new_key()), (cipher.replace(b'AES-256-GCM', b'AES-128-GCM'), key)):
        with pytest.raises(ValueError):
            decrypt(damaged, wrong_key)


def fixture(tmp_path):
    def verifier(token):
        if token not in {"isolated-user-a", "isolated-user-b"}:
            raise ValueError("invalid")
        return token
    settings = Settings("sqlite:///" + str(tmp_path / "server.sqlite"), tmp_path / "storage", "https://issuer.example.invalid", "ai-config", "https://issuer.example.invalid/jwks")
    app = create_app(settings, identity_verifier=verifier)
    client = TestClient(app)
    def enroll(token):
        header = {"Authorization": "Bearer " + token}
        device = client.post("/v1/devices", json={"name": "Test Device"}, headers=header).json()
        return {**header, "X-AI-Device": device["device_id"], "X-AI-Device-Token": device["device_token"]}
    return app, client, enroll("isolated-user-a"), enroll("isolated-user-b")


def upload(client, headers, space, data, parent=None, key=None):
    body = {"idempotency_key": key or hashlib.sha256(data + str(parent).encode()).hexdigest(), "expected_head": parent, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    response = client.post(f"/v1/spaces/{space}/uploads", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["upload_id"], body


def test_server_ownership_partial_upload_idempotence_and_device_revocation(tmp_path):
    app, client, a, b = fixture(tmp_path)
    space = client.post("/v1/spaces", json={"name": "personal"}, headers=a).json()["space_id"]
    assert client.get(f"/v1/spaces/{space}/versions", headers=b).status_code == 404
    assert client.get("/v1/me", headers={"Authorization": "Bearer invalid"}).status_code == 401
    data = encrypt(b"package", new_key())
    upload_id, body = upload(client, a, space, data)
    assert client.get(f"/v1/uploads/{upload_id}", headers=b).status_code == 404
    assert client.post(f"/v1/uploads/{upload_id}/complete", headers=a).status_code == 409
    assert client.get(f"/v1/spaces/{space}/versions", headers=a).json() == []
    assert client.put(f"/v1/uploads/{upload_id}/parts/0", content=data, headers=a).status_code == 200
    assert client.put(f"/v1/uploads/{upload_id}/parts/0", content=data, headers=a).status_code == 200
    assert client.put(f"/v1/uploads/{upload_id}/parts/0", content=b"x" * len(data), headers=a).status_code == 409
    result = client.post(f"/v1/uploads/{upload_id}/complete", headers=a).json()
    assert result["saved"] and not result["conflict"]
    assert client.post(f"/v1/uploads/{upload_id}/complete", headers=a).json() == result
    version = result["version_id"]
    assert client.get(f"/v1/versions/{version}/content", headers=b).status_code == 404
    assert client.get(f"/v1/versions/{version}/content", headers=a).content == data
    fake = {**a, "X-AI-Device-Token": "incorrect"}
    assert client.get(f"/v1/versions/{version}/content", headers=fake).status_code == 403
    assert client.post(f"/v1/devices/{a['X-AI-Device']}/revoke", headers=a).status_code == 200
    assert client.get(f"/v1/versions/{version}/content", headers=a).status_code == 403


def test_two_versions_from_same_parent_are_both_retained(tmp_path):
    app, client, a, b = fixture(tmp_path)
    space = client.post("/v1/spaces", json={"name": "personal"}, headers=a).json()["space_id"]
    first, _ = upload(client, a, space, b"branch-one")
    second, _ = upload(client, a, space, b"branch-two")
    for upload_id, data in ((first, b"branch-one"), (second, b"branch-two")):
        assert client.put(f"/v1/uploads/{upload_id}/parts/0", content=data, headers=a).status_code == 200
    one = client.post(f"/v1/uploads/{first}/complete", headers=a).json()
    two = client.post(f"/v1/uploads/{second}/complete", headers=a).json()
    assert one["saved"] and two["saved"] and two["conflict"]
    assert client.get(f"/v1/spaces/{space}/head", headers=a).json()["head"] == one["version_id"]
    assert len(client.get(f"/v1/spaces/{space}/versions", headers=a).json()) == 2


def test_server_rejects_quota_overallocation_and_false_integrity(tmp_path):
    app, client, a, b = fixture(tmp_path)
    identity = client.get("/v1/me", headers=a).json()["user_id"]
    with Session(app.state.engine) as session, session.begin():
        session.get(User, identity).quota = 16
    space = client.post("/v1/spaces", json={"name": "personal"}, headers=a).json()["space_id"]
    bad = {"idempotency_key": "a" * 64, "expected_head": None, "size": 8, "sha256": "b" * 64}
    result = client.post(f"/v1/spaces/{space}/uploads", json=bad, headers=a)
    upload_id = result.json()["upload_id"]
    assert client.put(f"/v1/uploads/{upload_id}/parts/0", content=b"abcdefgh", headers=a).status_code == 200
    assert client.post(f"/v1/uploads/{upload_id}/complete", headers=a).status_code == 409
    oversized = {**bad, "idempotency_key": "c" * 64, "size": 9}
    assert client.post(f"/v1/spaces/{space}/uploads", json=oversized, headers=a).status_code == 413
    assert client.get(f"/v1/spaces/{space}/versions", headers=a).json() == []


def test_cloud_client_encrypted_upload_retry_download_and_plaintext_check(tmp_path):
    import httpx
    import json
    import zipfile
    from sync_core.cloud.client import CloudClient
    from sync_core.package.policy import PortableEntry, CollectionReport
    from sync_core.package.export import build_package_manifest
    app, server, a, b = fixture(tmp_path)
    space = server.post("/v1/spaces", json={"name": "personal"}, headers=a).json()["space_id"]
    identity = server.get("/v1/me", headers=a).json()["user_id"]
    class Vault:
        def __init__(self):
            self.values = {}
        def get(self, address, account="login"):
            return self.values.get((address, account), {})
        def put(self, address, value, account="login"):
            self.values[address, account] = value
        def delete(self, address, account="login"):
            self.values.pop((address, account), None)
    vault = Vault()
    import time
    address = "https://sync.example.invalid"
    vault.put(address, {"access_token": "isolated-user-a", "user_id": identity, "device_id": a["X-AI-Device"], "device_token": a["X-AI-Device-Token"], "expires": time.time() + 60})
    def handle(request):
        response = server.request(request.method, request.url.path, headers=dict(request.headers), content=request.content)
        return httpx.Response(response.status_code, headers=response.headers, content=response.content)
    client = CloudClient(address, tmp_path / "state", vault=vault, transport=httpx.MockTransport(handle))
    try:
        recovery = client.generate_key(space)["recovery_material"]
        assert recovery.startswith("AIK1-")
        report = CollectionReport((PortableEntry("agent://shared/common/instructions.md", "rule_file", "shared_rules", 1, b"# Portable rules\n"),), (), (), (), 0)
        manifest, payloads = build_package_manifest(report)
        package = tmp_path / "source.aiconfig"
        with zipfile.ZipFile(package, "w") as zipped:
            zipped.writestr("manifest.json", json.dumps(manifest))
            for name, data in payloads.items():
                zipped.writestr(name, data)
        original = package.read_bytes()
        from sync_core.application.service import ApplicationService
        preview = ApplicationService(tmp_path / "unused-device.json").cloud(server=address, action="upload", options={"space": space, "package_path": str(package), "expected_head": "none"})
        assert preview.data["can_apply"] and preview.detail["sha256"] == hashlib.sha256(original).hexdigest()
        original_get_key = client.get_key
        def change_source_after_validation(selected_space):
            package.write_bytes(b"changed after validation; never upload this")
            return original_get_key(selected_space)
        client.get_key = change_source_after_validation
        uploaded = client.upload(space, package, None)
        package.write_bytes(original)
        client.get_key = original_get_key
        repeated = client.upload(space, package, None)
        assert repeated["version_id"] == uploaded["version_id"]
        downloaded = client.download(space, uploaded["version_id"], tmp_path / "downloaded.aiconfig")
        assert downloaded["content_id"] == manifest["content_id"]
        assert (tmp_path / "downloaded.aiconfig").read_bytes() == package.read_bytes()
        assert not (tmp_path / "agent").exists()
        assert b"Portable rules" not in next((tmp_path / "state/cloud").rglob("upload.enc")).read_bytes()
        client.logout()
        with pytest.raises(ValueError):
            client.versions(space)
    finally:
        client.close()
