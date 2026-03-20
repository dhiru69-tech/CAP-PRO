"""
ReconMind — scanner/utils/db_models.py
Lightweight SQLAlchemy ORM models used by the scanner to read/write DB.
These mirror the backend models but are standalone — no FastAPI dependency.
"""

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ScanORM(Base):
    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    target: Mapped[str] = mapped_column(String(512))
    depth: Mapped[str] = mapped_column(String(50), default="standard")
    status: Mapped[str] = mapped_column(String(50), default="pending")
    dork_categories: Mapped[str] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    total_dorks: Mapped[int] = mapped_column(Integer, default=0)
    total_urls_found: Mapped[int] = mapped_column(Integer, default=0)
    total_findings: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[str] = mapped_column(Text, nullable=True)


class DorkORM(Base):
    __tablename__ = "dorks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scans.id"))
    category: Mapped[str] = mapped_column(String(100))
    query: Mapped[str] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ResultORM(Base):
    __tablename__ = "results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("scans.id"))
    dork_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True)

    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=True)
    snippet: Mapped[str] = mapped_column(Text, nullable=True)
    http_status: Mapped[int] = mapped_column(Integer, nullable=True)
    is_alive: Mapped[bool] = mapped_column(Boolean, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(50), nullable=True)
    ai_explanation: Mapped[str] = mapped_column(Text, nullable=True)
    found_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
