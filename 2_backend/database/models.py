"""
ReconMind Backend — database/models.py
All SQLAlchemy ORM models for the application.
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    String, Text, Boolean, Integer, DateTime,
    ForeignKey, Enum as SAEnum, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.db import Base


# ─────────────────────────────────────────
# Enums
# ─────────────────────────────────────────
class ScanStatus(PyEnum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"


class ScanDepth(PyEnum):
    SURFACE  = "surface"
    STANDARD = "standard"
    DEEP     = "deep"


class FindingRisk(PyEnum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"
    INFO     = "info"


# ─────────────────────────────────────────
# User Model
# ─────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=True)
    picture: Mapped[str] = mapped_column(Text, nullable=True)
    google_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    scan_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    scans: Mapped[list["Scan"]] = relationship("Scan", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email}>"


# ─────────────────────────────────────────
# Scan Model
# ─────────────────────────────────────────
class Scan(Base):
    __tablename__ = "scans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    target: Mapped[str] = mapped_column(String(512), nullable=False)
    depth: Mapped[ScanDepth] = mapped_column(
        SAEnum(ScanDepth), default=ScanDepth.STANDARD
    )
    status: Mapped[ScanStatus] = mapped_column(
        SAEnum(ScanStatus), default=ScanStatus.PENDING, index=True
    )

    # Dork categories selected (stored as comma-separated string)
    dork_categories: Mapped[str] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    # Summary counts (populated after completion)
    total_dorks: Mapped[int] = mapped_column(Integer, default=0)
    total_urls_found: Mapped[int] = mapped_column(Integer, default=0)
    total_findings: Mapped[int] = mapped_column(Integer, default=0)

    # Error message if failed
    error_message: Mapped[str] = mapped_column(Text, nullable=True)

    # AI analysis result (filled after AI model runs)
    ai_summary: Mapped[str] = mapped_column(Text, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="scans")
    dorks: Mapped[list["Dork"]] = relationship("Dork", back_populates="scan", cascade="all, delete-orphan")
    results: Mapped[list["Result"]] = relationship("Result", back_populates="scan", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Scan {self.target} [{self.status.value}]>"


# ─────────────────────────────────────────
# Dork Model
# ─────────────────────────────────────────
class Dork(Base):
    __tablename__ = "dorks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )

    category: Mapped[str] = mapped_column(String(100), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationship
    scan: Mapped["Scan"] = relationship("Scan", back_populates="dorks")
    results: Mapped[list["Result"]] = relationship("Result", back_populates="dork")

    def __repr__(self):
        return f"<Dork [{self.category}] {self.query[:50]}>"


# ─────────────────────────────────────────
# Result Model (discovered URLs)
# ─────────────────────────────────────────
class Result(Base):
    __tablename__ = "results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dork_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dorks.id", ondelete="SET NULL"), nullable=True
    )

    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=True)
    snippet: Mapped[str] = mapped_column(Text, nullable=True)

    # HTTP validation
    http_status: Mapped[int] = mapped_column(Integer, nullable=True)
    is_alive: Mapped[bool] = mapped_column(Boolean, nullable=True)

    # AI risk classification (filled after AI analysis)
    risk_level: Mapped[FindingRisk] = mapped_column(
        SAEnum(FindingRisk), nullable=True
    )
    ai_explanation: Mapped[str] = mapped_column(Text, nullable=True)

    found_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    scan: Mapped["Scan"] = relationship("Scan", back_populates="results")
    dork: Mapped["Dork"] = relationship("Dork", back_populates="results")

    def __repr__(self):
        return f"<Result {self.url[:60]}>"


# ─────────────────────────────────────────
# Report Model
# ─────────────────────────────────────────
class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    summary: Mapped[str] = mapped_column(Text, nullable=True)
    ai_analysis: Mapped[str] = mapped_column(Text, nullable=True)
    recommendations: Mapped[str] = mapped_column(Text, nullable=True)
    file_path: Mapped[str] = mapped_column(Text, nullable=True)

    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Report for scan {self.scan_id}>"
