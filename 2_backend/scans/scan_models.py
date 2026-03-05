"""
ReconMind Backend — scans/scan_models.py
Pydantic schemas for scan request/response validation.
"""

from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, field_validator
import re


# ─────────────────────────────────────────
# Request Schemas (incoming)
# ─────────────────────────────────────────
class CreateScanRequest(BaseModel):
    """Body for POST /api/scans — create a new scan."""

    target: str
    depth: str = "standard"              # surface | standard | deep
    dork_categories: List[str] = [       # Which dork types to run
        "file_exposure",
        "admin_panels",
        "credential_leaks",
        "config_files",
    ]

    @field_validator("target")
    @classmethod
    def validate_target(cls, v: str) -> str:
        v = v.strip().lower()
        # Remove protocol if provided
        v = re.sub(r"^https?://", "", v)
        # Remove trailing slashes
        v = v.rstrip("/")
        # Basic domain validation
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}$", v):
            raise ValueError("Invalid domain format. Example: example.com")
        return v

    @field_validator("depth")
    @classmethod
    def validate_depth(cls, v: str) -> str:
        valid = {"surface", "standard", "deep"}
        if v not in valid:
            raise ValueError(f"depth must be one of: {valid}")
        return v

    @field_validator("dork_categories")
    @classmethod
    def validate_categories(cls, v: List[str]) -> List[str]:
        valid = {
            "file_exposure", "admin_panels", "credential_leaks",
            "config_files", "database_dumps", "log_files",
            "api_keys", "backup_files"
        }
        invalid = [c for c in v if c not in valid]
        if invalid:
            raise ValueError(f"Invalid categories: {invalid}")
        if not v:
            raise ValueError("At least one dork category must be selected.")
        return v


# ─────────────────────────────────────────
# Response Schemas (outgoing)
# ─────────────────────────────────────────
class ScanSummary(BaseModel):
    """Compact scan info — used in list responses."""
    id: str
    target: str
    status: str
    depth: str
    created_at: str
    total_dorks: int
    total_urls_found: int
    total_findings: int

    class Config:
        from_attributes = True


class ScanDetail(BaseModel):
    """Full scan detail — used in single scan GET response."""
    id: str
    target: str
    status: str
    depth: str
    dork_categories: Optional[str]
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    total_dorks: int
    total_urls_found: int
    total_findings: int
    error_message: Optional[str]
    ai_summary: Optional[str]

    class Config:
        from_attributes = True


class DorkInfo(BaseModel):
    id: str
    category: str
    query: str
    generated_at: str

    class Config:
        from_attributes = True


class ResultInfo(BaseModel):
    id: str
    url: str
    title: Optional[str]
    snippet: Optional[str]
    http_status: Optional[int]
    is_alive: Optional[bool]
    risk_level: Optional[str]
    ai_explanation: Optional[str]
    found_at: str
    dork_category: Optional[str] = None

    class Config:
        from_attributes = True


class ScanWithResults(ScanDetail):
    """Scan detail with dorks and results included."""
    dorks: List[DorkInfo] = []
    results: List[ResultInfo] = []
