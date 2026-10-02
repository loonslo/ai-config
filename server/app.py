"""OIDC-authorized resumable ciphertext storage and transactional head updates."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import time
from typing import Annotated, Any, Callable
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.orm import Session

from .models import Base, Device, Part, Receipt, SchemaVersion, Space, Upload, User, Version

CHUNK_BYTES = 4 * 1024 * 1024
MAX_PACKAGE_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True)
class Settings:
    database_url: str
    storage: Path
    issuer: str
    audience: str
    jwks_url: str
    quota_bytes: int = 1024 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(os.environ["AI_SYNC_DATABASE_URL"], Path(os.environ["AI_SYNC_STORAGE"]),
                   os.environ["AI_SYNC_OIDC_ISSUER"], os.environ["AI_SYNC_OIDC_AUDIENCE"],
                   os.environ["AI_SYNC_OIDC_JWKS_URL"], int(os.environ.get("AI_SYNC_QUOTA_BYTES", 1024**3)))


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Named(StrictInput):
    name: str = Field(min_length=1, max_length=80, pattern=r"^[\w .-]+$")


class UploadInput(StrictInput):
    idempotency_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    expected_head: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    size: int = Field(gt=0, le=MAX_PACKAGE_BYTES)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ReceiptInput(StrictInput):
    space_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    version_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    content_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    state: str = Field(pattern=r"^(applied|pending|failed)$")
    load_verified: bool = False


def migrate(engine: Any) -> None:
    """Only bootstrap v1; reject future databases rather than guessing migrations."""
    Base.metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        versions = session.scalars(select(SchemaVersion.version)).all()
        if versions and versions != [1]:
            raise RuntimeError("Unsupported database schema; explicit migration required")
        if not versions:
            session.add(SchemaVersion(version=1))


def _publish(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, filename = tempfile.mkstemp(dir=path.parent)
    stage = Path(filename)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(stage, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise HTTPException(409, "immutable_storage_conflict")
    finally:
        stage.unlink(missing_ok=True)


def create_app(settings: Settings, *, identity_verifier: Callable[[str], str] | None = None) -> FastAPI:
    """The verifier injection is only a Python factory seam for isolated tests.

    Production has no test-token environment flag or unauthenticated fallback.
    """
    if not identity_verifier and (not settings.issuer.startswith("https://") or not settings.jwks_url.startswith("https://")):
        raise ValueError("OIDC issuer and JWKS require HTTPS")
    storage = settings.storage.absolute()
    if any(path.is_symlink() for path in (storage, *storage.parents)):
        raise ValueError("Storage must not traverse links")
    storage.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}, pool_pre_ping=True)
    if settings.database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def foreign_keys(connection: Any, _record: Any) -> None:
            connection.execute("PRAGMA foreign_keys=ON")
    migrate(engine)
    jwks = jwt.PyJWKClient(settings.jwks_url)
    app = FastAPI(title="AI Config encrypted sync", version="1.0.0")
    app.state.engine = engine
    bearer = HTTPBearer()

    def owner(credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer)]) -> str:
        token = credentials.credentials
        try:
            if identity_verifier:
                subject = identity_verifier(token)
            else:
                key = jwks.get_signing_key_from_jwt(token)
                claims = jwt.decode(token, key.key, algorithms=["RS256"], issuer=settings.issuer,
                                    audience=settings.audience, options={"require": ["exp", "iat", "sub", "iss", "aud"]})
                subject = claims["sub"]
            if not isinstance(subject, str) or not subject or len(subject) > 255:
                raise ValueError("Invalid subject")
        except Exception as error:
            raise HTTPException(401, "invalid_identity") from error
        identity = hashlib.sha256((settings.issuer + "\x00" + subject).encode()).hexdigest()
        with Session(engine) as session, session.begin():
            if session.get(User, identity) is None:
                # Serialize first-login creation on the unique primary key.
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                insert = sqlite_insert if engine.dialect.name == "sqlite" else pg_insert
                session.execute(insert(User).values(id=identity, quota=settings.quota_bytes).on_conflict_do_nothing())
        return identity

    Owner = Annotated[str, Depends(owner)]

    def get_owned(session: Session, model: Any, resource_id: str, identity: str, *, lock: bool = False) -> Any:
        if not re.fullmatch(r"[a-f0-9]{32}", resource_id):
            raise HTTPException(404, "resource_not_found")
        statement = select(model).where(model.id == resource_id, model.owner == identity)
        if lock:
            statement = statement.with_for_update()
        row = session.scalar(statement)
        if row is None:
            raise HTTPException(404, "resource_not_found")
        return row

    def device(session: Session, identity: str, device_id: str | None, device_token: str | None = None) -> Device:
        if device_id is None:
            raise HTTPException(403, "device_required")
        row = get_owned(session, Device, device_id, identity)
        if row.revoked:
            raise HTTPException(403, "device_revoked")
        if not device_token or not secrets.compare_digest(row.credential_hash, hashlib.sha256(device_token.encode()).hexdigest()):
            raise HTTPException(403, "device_credential_required")
        return row

    DeviceId = Annotated[str | None, Header(alias="X-AI-Device")]
    DeviceToken = Annotated[str | None, Header(alias="X-AI-Device-Token")]

    @app.get("/health")
    def health() -> dict[str, Any]:
        with Session(engine) as session:
            session.execute(select(SchemaVersion.version))
        if not os.access(storage, os.W_OK) or not (storage.is_dir()):
            raise HTTPException(503, "storage_unavailable")
        return {"status": "ok", "schema": 1}

    @app.get("/v1/me")
    def me(identity: Owner) -> dict[str, Any]:
        return {"user_id": identity, "chunk_bytes": CHUNK_BYTES, "max_package_bytes": MAX_PACKAGE_BYTES}

    @app.post("/v1/devices")
    def add_device(body: Named, identity: Owner) -> dict[str, str]:
        device_id = uuid.uuid4().hex
        credential = secrets.token_urlsafe(32)
        row = Device(id=device_id, owner=identity, name=body.name, credential_hash=hashlib.sha256(credential.encode()).hexdigest())
        with Session(engine) as session, session.begin():
            session.add(row)
        return {"device_id": device_id, "device_token": credential}

    @app.get("/v1/devices")
    def list_devices(identity: Owner, x_ai_device: DeviceId = None, x_ai_device_token: DeviceToken = None) -> list[dict[str, Any]]:
        with Session(engine) as session:
            device(session, identity, x_ai_device, x_ai_device_token)
            return [{"device_id": row.id, "name": row.name, "revoked": row.revoked} for row in session.scalars(select(Device).where(Device.owner == identity))]

    @app.post("/v1/devices/{resource_id}/revoke")
    def revoke(resource_id: str, identity: Owner, x_ai_device: DeviceId = None, x_ai_device_token: DeviceToken = None) -> dict[str, bool]:
        with Session(engine) as session, session.begin():
            device(session, identity, x_ai_device, x_ai_device_token)
            get_owned(session, Device, resource_id, identity).revoked = True
        return {"revoked": True}

    @app.post("/v1/spaces")
    def add_space(body: Named, identity: Owner, x_ai_device: DeviceId = None, x_ai_device_token: DeviceToken = None) -> dict[str, Any]:
        with Session(engine) as session, session.begin():
            device(session, identity, x_ai_device, x_ai_device_token)
            session.execute(update(User).where(User.id == identity).values(quota=User.quota))
            row = session.scalar(select(Space).where(Space.owner == identity, Space.name == body.name))
            if row is None:
                row = Space(id=uuid.uuid4().hex, owner=identity, name=body.name)
                session.add(row)
            result = {"space_id": row.id, "head": row.head}
        return result

    @app.get("/v1/spaces")
    def spaces(identity: Owner, x_ai_device: DeviceId = None, x_ai_device_token: DeviceToken = None) -> list[dict[str, Any]]:
        with Session(engine) as session:
            device(session, identity, x_ai_device, x_ai_device_token)
            return [{"space_id": row.id, "name": row.name, "head": row.head} for row in session.scalars(select(Space).where(Space.owner == identity))]

    @app.post("/v1/spaces/{space_id}/uploads")
    def create_upload(space_id: str, body: UploadInput, identity: Owner, x_ai_device: DeviceId = None, x_ai_device_token: DeviceToken = None) -> dict[str, Any]:
        with Session(engine) as session, session.begin():
            current_device = device(session, identity, x_ai_device, x_ai_device_token)
            get_owned(session, Space, space_id, identity)
            session.execute(update(User).where(User.id == identity).values(quota=User.quota))
            previous = session.scalar(select(Upload).where(Upload.owner == identity, Upload.idempotency_key == body.idempotency_key))
            if previous:
                if (previous.space, previous.size, previous.sha256, previous.expected_head) != (space_id, body.size, body.sha256, body.expected_head):
                    raise HTTPException(409, "idempotency_mismatch")
                return {"upload_id": previous.id, "version_id": previous.version, "chunk_bytes": CHUNK_BYTES}
            if body.expected_head:
                parent = get_owned(session, Version, body.expected_head, identity)
                if parent.space != space_id:
                    raise HTTPException(409, "invalid_parent")
            used = session.scalar(select(func.coalesce(func.sum(Upload.size), 0)).where(Upload.owner == identity))
            user = session.get(User, identity)
            if used + body.size > user.quota:
                raise HTTPException(413, "quota_exceeded")
            row = Upload(id=uuid.uuid4().hex, owner=identity, device=current_device.id, space=space_id,
                         idempotency_key=body.idempotency_key, expected_head=body.expected_head, size=body.size,
                         sha256=body.sha256, created=int(time.time()))
            session.add(row)
            result = {"upload_id": row.id, "version_id": None, "chunk_bytes": CHUNK_BYTES}
        return result

    @app.get("/v1/uploads/{upload_id}")
    def upload_status(upload_id: str, identity: Owner, x_ai_device: DeviceId = None, x_ai_device_token: DeviceToken = None) -> dict[str, Any]:
        with Session(engine) as session:
            device(session, identity, x_ai_device, x_ai_device_token)
            row = get_owned(session, Upload, upload_id, identity)
            return {"upload_id": row.id, "version_id": row.version, "parts": [part.number for part in session.scalars(select(Part).where(Part.upload == upload_id))]}

    @app.put("/v1/uploads/{upload_id}/parts/{number}")
    async def upload_part(upload_id: str, number: int, request: Request, identity: Owner, x_ai_device: DeviceId = None, x_ai_device_token: DeviceToken = None) -> dict[str, int]:
        # Bound the ASGI stream before buffering; no arbitrary request.body().
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > CHUNK_BYTES:
                raise HTTPException(413, "part_too_large")
        with Session(engine) as session, session.begin():
            device(session, identity, x_ai_device, x_ai_device_token)
            row = get_owned(session, Upload, upload_id, identity, lock=True)
            session.execute(update(Upload).where(Upload.id == upload_id).values(created=Upload.created))
            session.refresh(row)
            if row.version:
                raise HTTPException(409, "upload_already_complete")
            count = (row.size + CHUNK_BYTES - 1) // CHUNK_BYTES
            expected_size = min(CHUNK_BYTES, row.size - number * CHUNK_BYTES)
            if number < 0 or number >= count or len(data) != expected_size:
                raise HTTPException(422, "invalid_part")
            sha = hashlib.sha256(data).hexdigest()
            previous = session.get(Part, (upload_id, number))
            if previous and (previous.size != len(data) or previous.sha256 != sha):
                raise HTTPException(409, "part_mismatch")
            path = storage / "staging" / identity / upload_id / f"{number}.part"
            _publish(path, bytes(data))
            if previous is None:
                session.add(Part(upload=upload_id, number=number, size=len(data), sha256=sha))
        return {"part": number, "size": len(data)}

    @app.post("/v1/uploads/{upload_id}/complete")
    def complete(upload_id: str, identity: Owner, x_ai_device: DeviceId = None, x_ai_device_token: DeviceToken = None) -> dict[str, Any]:
        with Session(engine) as session, session.begin():
            device(session, identity, x_ai_device, x_ai_device_token)
            row = get_owned(session, Upload, upload_id, identity, lock=True)
            session.execute(update(Upload).where(Upload.id == upload_id).values(created=Upload.created))
            session.refresh(row)
            if row.version:
                version = session.get(Version, row.version)
                return {"version_id": version.id, "conflict": version.conflict, "saved": True}
            parts = session.scalars(select(Part).where(Part.upload == upload_id).order_by(Part.number)).all()
            count = (row.size + CHUNK_BYTES - 1) // CHUNK_BYTES
            if [part.number for part in parts] != list(range(count)):
                raise HTTPException(409, "upload_incomplete")
            data = bytearray()
            for part in parts:
                path = storage / "staging" / identity / upload_id / f"{part.number}.part"
                fragment = path.read_bytes()
                if len(fragment) != part.size or hashlib.sha256(fragment).hexdigest() != part.sha256:
                    raise HTTPException(409, "part_integrity_failed")
                data.extend(fragment)
            if len(data) != row.size or hashlib.sha256(data).hexdigest() != row.sha256:
                raise HTTPException(409, "ciphertext_integrity_failed")
            version_id = row.id  # Stable across a retry after storage / DB failure.
            _publish(storage / "versions" / identity / f"{version_id}.enc", bytes(data))
            condition = Space.head.is_(None) if row.expected_head is None else Space.head == row.expected_head
            changed = session.execute(update(Space).where(Space.id == row.space, Space.owner == identity, condition).values(head=version_id)).rowcount
            version = Version(id=version_id, owner=identity, space=row.space, device=row.device, parent=row.expected_head,
                              sha256=row.sha256, size=row.size, created=int(time.time()), conflict=changed != 1)
            session.add(version)
            row.version = version_id
            return {"version_id": version_id, "conflict": version.conflict, "saved": True}

    @app.get("/v1/spaces/{space_id}/head")
    def head(space_id: str, identity: Owner, x_ai_device: DeviceId = None, x_ai_device_token: DeviceToken = None) -> dict[str, Any]:
        with Session(engine) as session:
            device(session, identity, x_ai_device, x_ai_device_token)
            row = get_owned(session, Space, space_id, identity)
            return {"head": row.head}

    @app.get("/v1/spaces/{space_id}/versions")
    def versions(space_id: str, identity: Owner, x_ai_device: DeviceId = None, x_ai_device_token: DeviceToken = None) -> list[dict[str, Any]]:
        with Session(engine) as session:
            device(session, identity, x_ai_device, x_ai_device_token)
            get_owned(session, Space, space_id, identity)
            return [{"version_id": row.id, "parent": row.parent, "sha256": row.sha256, "size": row.size, "created": row.created, "conflict": row.conflict}
                    for row in session.scalars(select(Version).where(Version.owner == identity, Version.space == space_id).order_by(Version.created.desc()).limit(1000))]

    @app.get("/v1/versions/{version_id}/content")
    def content(version_id: str, identity: Owner, x_ai_device: DeviceId = None, x_ai_device_token: DeviceToken = None) -> FileResponse:
        with Session(engine) as session:
            device(session, identity, x_ai_device, x_ai_device_token)
            row = get_owned(session, Version, version_id, identity)
            path = storage / "versions" / identity / f"{version_id}.enc"
            if not path.is_file() or path.stat().st_size != row.size:
                raise HTTPException(503, "version_storage_unavailable")
            return FileResponse(path, media_type="application/octet-stream", headers={"X-Content-SHA256": row.sha256})

    @app.post("/v1/devices/{resource_id}/receipts")
    def receipt(resource_id: str, body: ReceiptInput, identity: Owner, x_ai_device: DeviceId = None, x_ai_device_token: DeviceToken = None) -> dict[str, bool]:
        with Session(engine) as session, session.begin():
            current = device(session, identity, x_ai_device, x_ai_device_token)
            if current.id != resource_id:
                raise HTTPException(403, "receipt_device_mismatch")
            get_owned(session, Space, body.space_id, identity)
            version = get_owned(session, Version, body.version_id, identity)
            if version.space != body.space_id:
                raise HTTPException(422, "receipt_space_mismatch")
            row = session.get(Receipt, (resource_id, body.space_id))
            if row is None:
                row = Receipt(device=resource_id, space=body.space_id, owner=identity)
                session.add(row)
            row.summary = body.model_dump_json()
            row.created = int(time.time())
        return {"saved": True}

    @app.get("/v1/spaces/{space_id}/receipts")
    def receipts(space_id: str, identity: Owner, x_ai_device: DeviceId = None, x_ai_device_token: DeviceToken = None) -> list[dict[str, Any]]:
        with Session(engine) as session:
            device(session, identity, x_ai_device, x_ai_device_token)
            get_owned(session, Space, space_id, identity)
            return [{"device_id": row.device, "reported_at": row.created, "summary": json.loads(row.summary)} for row in session.scalars(select(Receipt).where(Receipt.owner == identity, Receipt.space == space_id))]

    return app


def production_app() -> FastAPI:
    return create_app(Settings.from_env())
