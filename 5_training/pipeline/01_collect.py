"""
ReconMind — training/pipeline/01_collect.py
Step 1: Collect and validate raw training data.

Sources:
  - data/raw/dork_knowledge_base.json   → dork definitions + risks
  - data/raw/training_examples.json     → instruction-following pairs

What this script does:
  - Loads all raw data files
  - Validates schema of each entry
  - Reports counts and any issues
  - Outputs a combined raw collection to data/cleaned/collected.json
"""

import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Any

# ─────────────────────────────────────────
# Paths
# ─────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR     = os.path.join(BASE_DIR, "data", "raw")
CLEANED_DIR = os.path.join(BASE_DIR, "data", "cleaned")
os.makedirs(CLEANED_DIR, exist_ok=True)

OUTPUT_FILE = os.path.join(CLEANED_DIR, "collected.json")


# ─────────────────────────────────────────
# Schema validators
# ─────────────────────────────────────────
REQUIRED_KNOWLEDGE_FIELDS = [
    "dork", "category", "risk", "what_it_finds",
    "why_dangerous", "remediation"
]

REQUIRED_EXAMPLE_FIELDS = [
    "id", "instruction", "input", "output"
]

VALID_RISK_LEVELS = {"critical", "high", "medium", "low", "info"}
VALID_CATEGORIES  = {
    "file_exposure", "admin_panels", "credential_leaks",
    "config_files", "database_dumps", "log_files",
    "api_keys", "backup_files"
}


def validate_knowledge_entry(entry: dict, idx: int) -> List[str]:
    """Validate a dork knowledge base entry. Returns list of errors."""
    errors = []
    for field in REQUIRED_KNOWLEDGE_FIELDS:
        if field not in entry:
            errors.append(f"  [knowledge #{idx}] Missing field: '{field}'")
    if entry.get("risk") not in VALID_RISK_LEVELS:
        errors.append(f"  [knowledge #{idx}] Invalid risk: '{entry.get('risk')}'")
    if entry.get("category") not in VALID_CATEGORIES:
        errors.append(f"  [knowledge #{idx}] Unknown category: '{entry.get('category')}'")
    return errors


def validate_example_entry(entry: dict, idx: int) -> List[str]:
    """Validate a training example entry. Returns list of errors."""
    errors = []
    for field in REQUIRED_EXAMPLE_FIELDS:
        if field not in entry:
            errors.append(f"  [example #{idx}] Missing field: '{field}'")
    if not entry.get("instruction", "").strip():
        errors.append(f"  [example #{idx}] Empty instruction")
    if not isinstance(entry.get("input"), dict):
        errors.append(f"  [example #{idx}] 'input' must be a dict")
    if not isinstance(entry.get("output"), dict):
        errors.append(f"  [example #{idx}] 'output' must be a dict")
    return errors


# ─────────────────────────────────────────
# Loaders
# ─────────────────────────────────────────
def load_json(filepath: str) -> List[dict]:
    if not os.path.exists(filepath):
        print(f"  [SKIP] File not found: {filepath}")
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        print(f"  [ERROR] Expected a list in {filepath}")
        return []
    return data


# ─────────────────────────────────────────
# Main
# ─────────────────────────────────────────
def main():
    print("=" * 55)
    print("  ReconMind Training — Step 1: Data Collection")
    print("=" * 55)

    all_errors = []
    collection = {
        "collected_at": datetime.utcnow().isoformat(),
        "knowledge_base": [],
        "training_examples": [],
    }

    # ── Load knowledge base ────────────────────────────
    kb_path = os.path.join(RAW_DIR, "dork_knowledge_base.json")
    kb_entries = load_json(kb_path)
    print(f"\n[1/2] Knowledge base: {len(kb_entries)} entries loaded")

    for i, entry in enumerate(kb_entries):
        errors = validate_knowledge_entry(entry, i + 1)
        all_errors.extend(errors)
        if not errors:
            collection["knowledge_base"].append(entry)

    print(f"      Valid: {len(collection['knowledge_base'])} / {len(kb_entries)}")

    # ── Load training examples ─────────────────────────
    ex_path = os.path.join(RAW_DIR, "training_examples.json")
    ex_entries = load_json(ex_path)
    print(f"\n[2/2] Training examples: {len(ex_entries)} entries loaded")

    for i, entry in enumerate(ex_entries):
        errors = validate_example_entry(entry, i + 1)
        all_errors.extend(errors)
        if not errors:
            collection["training_examples"].append(entry)

    print(f"      Valid: {len(collection['training_examples'])} / {len(ex_entries)}")

    # ── Category distribution ──────────────────────────
    print("\n  Category breakdown (knowledge base):")
    cat_counts: Dict[str, int] = {}
    for entry in collection["knowledge_base"]:
        cat = entry.get("category", "unknown")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    for cat, count in sorted(cat_counts.items()):
        print(f"    {cat:<25} {count} entries")

    # ── Risk distribution ──────────────────────────────
    print("\n  Risk distribution (knowledge base):")
    risk_counts: Dict[str, int] = {}
    for entry in collection["knowledge_base"]:
        risk = entry.get("risk", "unknown")
        risk_counts[risk] = risk_counts.get(risk, 0) + 1
    for risk in ["critical", "high", "medium", "low", "info"]:
        count = risk_counts.get(risk, 0)
        bar = "█" * count
        print(f"    {risk:<10} {bar} ({count})")

    # ── Errors ────────────────────────────────────────
    if all_errors:
        print(f"\n  ⚠  {len(all_errors)} validation issues found:")
        for err in all_errors:
            print(err)
    else:
        print(f"\n  ✅ All entries passed validation")

    # ── Save output ───────────────────────────────────
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(collection, f, indent=2, ensure_ascii=False)

    total = len(collection["knowledge_base"]) + len(collection["training_examples"])
    print(f"\n  Output: {OUTPUT_FILE}")
    print(f"  Total entries collected: {total}")
    print("\n  Next step: python pipeline/02_clean.py")
    print("=" * 55)

    return len(all_errors) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
