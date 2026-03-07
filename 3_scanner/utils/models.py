"""
ReconMind — scanner/utils/models.py
Shared dataclass models used across the scanner pipeline.
Pure Python — no DB dependency.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime


# ─────────────────────────────────────────
# Enums
# ─────────────────────────────────────────
class ScanStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"


class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH     = "high"
    MEDIUM   = "medium"
    LOW      = "low"
    INFO     = "info"


# ─────────────────────────────────────────
# Input: Scan Task
# ─────────────────────────────────────────
@dataclass
class ScanTask:
    """
    Passed to ScanRunner to describe what to scan.
    Built by the worker from DB data.
    """
    scan_id: str
    target: str
    depth: str                          # surface | standard | deep
    dork_categories: List[str]
    dorks: List[Dict[str, str]] = field(default_factory=list)
    # Each dork: {"category": "...", "query": "...", "dork_id": "..."}


# ─────────────────────────────────────────
# Intermediate: Dork Result
# ─────────────────────────────────────────
@dataclass
class DorkResult:
    """
    Raw output of running a single dork query.
    Before URL validation.
    """
    dork_id: Optional[str]
    category: str
    query: str
    raw_urls: List[str] = field(default_factory=list)
    error: Optional[str] = None


# ─────────────────────────────────────────
# Intermediate: Discovery Result
# ─────────────────────────────────────────
@dataclass
class DiscoveryResult:
    """
    A single URL discovered during the discovery phase.
    Not yet validated.
    """
    url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    source_query: Optional[str] = None
    category: Optional[str] = None
    dork_id: Optional[str] = None


# ─────────────────────────────────────────
# Output: Validated URL
# ─────────────────────────────────────────
@dataclass
class ValidatedURL:
    """
    A URL that has been HTTP-checked.
    Ready to be stored as a Result in the DB.
    """
    url: str
    is_alive: bool
    http_status: Optional[int] = None
    content_type: Optional[str] = None
    title: Optional[str] = None
    snippet: Optional[str] = None
    category: Optional[str] = None
    dork_id: Optional[str] = None
    response_time_ms: Optional[int] = None
    redirect_url: Optional[str] = None
    error: Optional[str] = None

    # Risk classification — set by AI in Phase 6
    # For now: inferred by heuristic rules
    risk_level: Optional[RiskLevel] = None
