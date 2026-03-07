"""
ReconMind — ai-model/inference/inference_engine.py
Local AI inference engine. Loaded and used in Phase 6.

This module provides a clean interface for the backend to
request AI analysis of scan results without knowing the
underlying model implementation.

Usage (Phase 6 integration):
    engine = InferenceEngine()
    await engine.load()

    # Analyze a single finding
    result = await engine.analyze_finding(finding)

    # Summarize a full scan
    summary = await engine.summarize_scan(scan_data)
"""

import json
import os
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "model", "reconmind-v1", "final"
)

SYSTEM_PROMPT = """You are ReconMind AI, a specialized security analysis assistant.
Your role is to analyze web reconnaissance findings, classify risk levels,
explain vulnerabilities, and provide actionable remediation steps.
Be precise, factual, and security-focused."""


# ─────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────
@dataclass
class FindingInput:
    url: str
    category: str
    http_status: Optional[int] = None
    title: Optional[str] = None
    snippet: Optional[str] = None
    dork_used: Optional[str] = None


@dataclass
class FindingAnalysis:
    risk_level: str          # critical | high | medium | low | info
    title: str
    explanation: str
    impact: str
    remediation: List[str]
    confidence: float        # 0.0 - 1.0


@dataclass
class ScanSummary:
    overall_risk: str
    summary: str
    key_concerns: List[str]
    immediate_actions: List[str]
    risk_score: float        # 0.0 - 10.0


# ─────────────────────────────────────────
# Inference Engine
# ─────────────────────────────────────────
class InferenceEngine:
    """
    Wraps the fine-tuned ReconMind AI model for inference.
    Handles model loading, prompt formatting, and response parsing.
    """

    def __init__(self, model_path: str = MODEL_DIR):
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self.loaded = False

    async def load(self):
        """
        Load the fine-tuned model into memory.
        Call once at application startup.
        """
        import asyncio
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._load_sync)

    def _load_sync(self):
        """Synchronous model loading (run in thread pool)."""
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            print(f"[AI] Loading ReconMind model from: {self.model_path}")

            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                device_map="auto",
            )
            self.model.eval()
            self.loaded = True
            print("[AI] Model loaded successfully.")

        except Exception as e:
            print(f"[AI] WARNING: Could not load model: {e}")
            print("[AI] Running in fallback (heuristic) mode.")
            self.loaded = False

    def _generate(self, user_message: str, max_tokens: int = 512) -> str:
        """Generate a response from the model."""
        if not self.loaded:
            return ""

        import torch

        prompt = (
            f"<|system|>\n{SYSTEM_PROMPT}</s>\n"
            f"<|user|>\n{user_message}</s>\n"
            f"<|assistant|>\n"
        )

        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=0.1,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        input_len = inputs["input_ids"].shape[1]
        response_ids = outputs[0][input_len:]
        return self.tokenizer.decode(response_ids, skip_special_tokens=True)

    def _parse_risk_level(self, text: str) -> str:
        """Extract risk level from response text."""
        import re
        text_lower = text.lower()
        for level in ["critical", "high", "medium", "low", "info"]:
            if re.search(rf"\b{level}\b", text_lower):
                return level
        return "info"

    def _parse_list_items(self, text: str, header: str) -> List[str]:
        """Extract numbered list items after a header."""
        import re
        lines = text.split("\n")
        in_section = False
        items = []
        for line in lines:
            if header.lower() in line.lower():
                in_section = True
                continue
            if in_section:
                # Stop at next header
                if line.strip().startswith("**") and line.strip().endswith("**"):
                    break
                # Numbered or bulleted item
                match = re.match(r"^\s*[\d\-\*\.]+\.?\s+(.+)", line)
                if match:
                    items.append(match.group(1).strip())
        return items

    # ─────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────
    async def analyze_finding(self, finding: FindingInput) -> FindingAnalysis:
        """
        Analyze a single scan finding using the AI model.
        Falls back to heuristic analysis if model is not loaded.
        """
        user_message = (
            f"Analyze this scan finding and explain the security risk.\n\n"
            f"**URL:** `{finding.url}`\n"
            f"**Category:** {finding.category}\n"
        )
        if finding.http_status:
            user_message += f"**HTTP Status:** {finding.http_status}\n"
        if finding.title:
            user_message += f"**Page Title:** {finding.title}\n"
        if finding.snippet:
            user_message += f"**Content Preview:** {finding.snippet[:200]}\n"
        if finding.dork_used:
            user_message += f"**Dork Used:** `{finding.dork_used}`\n"

        if self.loaded:
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, self._generate, user_message, 400
            )
        else:
            # Fallback: return placeholder
            response = self._heuristic_analysis(finding)

        return FindingAnalysis(
            risk_level=self._parse_risk_level(response),
            title=f"Security Finding: {finding.category.replace('_', ' ').title()}",
            explanation=response[:500] if response else "Analysis unavailable.",
            impact="See explanation for details.",
            remediation=self._parse_list_items(response, "Remediation") or [
                "Review and restrict access to this resource."
            ],
            confidence=0.9 if self.loaded else 0.5,
        )

    async def summarize_scan(self, scan_data: Dict[str, Any]) -> ScanSummary:
        """
        Generate an AI summary for a completed scan.
        """
        findings_by_risk = scan_data.get("findings_by_risk", {})
        target = scan_data.get("target", "unknown")

        user_message = (
            f"Generate an AI analysis summary for the following completed scan.\n\n"
            f"**Target:** {target}\n"
            f"**URLs Found:** {scan_data.get('total_urls_found', 0)}\n"
            f"**Alive URLs:** {scan_data.get('total_alive', 0)}\n"
            f"**Findings:** "
            f"Critical={findings_by_risk.get('critical', 0)} "
            f"High={findings_by_risk.get('high', 0)} "
            f"Medium={findings_by_risk.get('medium', 0)} "
            f"Low={findings_by_risk.get('low', 0)}\n"
        )

        top = scan_data.get("top_findings", [])[:3]
        if top:
            user_message += "\n**Top Findings:**\n"
            for f in top:
                user_message += f"- [{f.get('risk','?').upper()}] {f.get('url','?')} ({f.get('category','?')})\n"

        if self.loaded:
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, self._generate, user_message, 600
            )
        else:
            response = self._heuristic_summary(scan_data)

        # Compute overall risk
        if findings_by_risk.get("critical", 0) > 0:
            overall = "critical"
        elif findings_by_risk.get("high", 0) > 0:
            overall = "high"
        elif findings_by_risk.get("medium", 0) > 0:
            overall = "medium"
        else:
            overall = "low"

        # Simple risk score calculation
        risk_score = min(10.0, round(
            findings_by_risk.get("critical", 0) * 3.0 +
            findings_by_risk.get("high", 0) * 2.0 +
            findings_by_risk.get("medium", 0) * 1.0 +
            findings_by_risk.get("low", 0) * 0.5,
            1
        ))

        return ScanSummary(
            overall_risk=overall,
            summary=response[:600] if response else "Summary unavailable.",
            key_concerns=self._parse_list_items(response, "Key Concerns") or [
                f"{findings_by_risk.get('critical', 0)} critical findings require immediate attention."
            ],
            immediate_actions=self._parse_list_items(response, "Immediate Actions") or [
                "Review and address all critical findings immediately."
            ],
            risk_score=risk_score,
        )

    # ─────────────────────────────────────────
    # Heuristic fallback (before model is loaded)
    # ─────────────────────────────────────────
    def _heuristic_analysis(self, finding: FindingInput) -> str:
        category = finding.category
        status   = finding.http_status or 0

        risk_map = {
            "credential_leaks":  "CRITICAL",
            "database_dumps":    "CRITICAL",
            "api_keys":          "CRITICAL",
            "admin_panels":      "HIGH" if status == 200 else "MEDIUM",
            "config_files":      "HIGH",
            "file_exposure":     "HIGH",
            "log_files":         "MEDIUM",
            "backup_files":      "MEDIUM",
        }
        risk = risk_map.get(category, "MEDIUM")
        return (
            f"**Risk Level:** {risk}\n\n"
            f"**Analysis:** This finding ({category}) requires security review. "
            f"HTTP status {status} indicates the resource is accessible.\n\n"
            f"**Remediation Steps:**\n"
            f"1. Restrict public access to this resource immediately.\n"
            f"2. Review the exposed content for sensitive information.\n"
            f"3. Implement proper access controls.\n"
            f"(Note: AI model not loaded. Using heuristic analysis.)"
        )

    def _heuristic_summary(self, scan_data: Dict) -> str:
        total = scan_data.get("total_urls_found", 0)
        critical = scan_data.get("findings_by_risk", {}).get("critical", 0)
        return (
            f"**Summary:** Scan of {scan_data.get('target', 'target')} found {total} URLs. "
            f"{critical} critical findings require immediate attention.\n\n"
            f"**Immediate Actions:**\n"
            f"1. Address all critical findings immediately.\n"
            f"2. Review high-severity findings within 24 hours.\n"
            f"(Note: AI model not loaded. Using heuristic analysis.)"
        )
