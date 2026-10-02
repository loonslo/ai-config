"""Schema v1. Owner IDs derive exclusively from verified issuer / subject."""
from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    quota: Mapped[int] = mapped_column(BigInteger)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    credential_hash: Mapped[str] = mapped_column(String(64))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Space(Base):
    __tablename__ = "spaces"
    __table_args__ = (UniqueConstraint("owner", "name"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    head: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Upload(Base):
    __tablename__ = "uploads"
    __table_args__ = (UniqueConstraint("owner", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    device: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    space: Mapped[str] = mapped_column(ForeignKey("spaces.id"))
    idempotency_key: Mapped[str] = mapped_column(String(64))
    expected_head: Mapped[str | None] = mapped_column(String(32), nullable=True)
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    created: Mapped[int] = mapped_column(Integer)
    version: Mapped[str | None] = mapped_column(String(32), nullable=True)


class Part(Base):
    __tablename__ = "parts"
    upload: Mapped[str] = mapped_column(ForeignKey("uploads.id"), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))


class Version(Base):
    __tablename__ = "versions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    space: Mapped[str] = mapped_column(ForeignKey("spaces.id"), index=True)
    device: Mapped[str] = mapped_column(ForeignKey("devices.id"))
    parent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    created: Mapped[int] = mapped_column(Integer)
    conflict: Mapped[bool] = mapped_column(Boolean)


class Receipt(Base):
    __tablename__ = "receipts"
    device: Mapped[str] = mapped_column(ForeignKey("devices.id"), primary_key=True)
    space: Mapped[str] = mapped_column(ForeignKey("spaces.id"), primary_key=True)
    owner: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    summary: Mapped[str] = mapped_column(Text)
    created: Mapped[int] = mapped_column(Integer)


class SchemaVersion(Base):
    __tablename__ = "schema_version"
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
