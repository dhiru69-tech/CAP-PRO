"""
ReconMind — training/pipeline/02_clean.py
Step 2: Clean and normalize collected training data.

What this script does:
  - Loads data/cleaned/collected.json (from Step 1)
  - Normalizes text (whitespace, unicode, encoding issues)
  - Deduplicates entries by dork query or example ID
  - Expands knowledge base entries into instruction pairs
  - Filters out low-quality examples
  - Outputs cleaned data to data/cleaned/cleaned.json
"""

import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from typing import List, Dict, Any, Optional

# ─────────────────────────────────────────
# Paths
# ─────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEANED_DIR = os.path.join(BASE_DIR, "data", "cleaned")
INPUT_FILE  = os.path.join(CLEANED_DIR, "collected.json")
OUTPUT_FILE = os.path.join(CLEANED_DIR, "cleaned.json")


# ─────────────────────────────────────────
# Text normalization
# ─────────────────────────────────────────
def normalize_text(text: Optional[str]) -> Optional[str]:
    """Normalize unicode, fix whitespace, strip edge spaces."""
    if not text:
        return text
    # Normalize unicode
    text = unicodedata.normalize("NFKC", text)
    # Collapse multiple spaces/newlines to single
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_entry(entry: dict) -> dict:
    """Recursively normalize all string fields in a dict."""
    result = {}
    for key, value in entry.items():
        if isinstance(value, str):
            result[key] = normalize_text(value)
        elif isinstance(value, dict):
            result[key] = normalize_entry(value)
        elif isinstance(value, list):
            result[key] = [
                normalize_text(v) if isinstance(v, str)
                else normalize_entry(v) if isinstance(v, dict)
                else v
                for v in value
            ]
        else:
            result[key] = value
    return result


# ─────────────────────────────────────────
# Deduplication
# ─────────────────────────────────────────
def deduplicate_knowledge(entries: List[dict]) -> List[dict]:
    """Remove duplicate dork entries based on normalized query."""
    seen = set()
    unique = []
    for entry in entries:
        key = normalize_text(entry.get("dork", "")).lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(entry)
    return unique


def deduplicate_examples(entries: List[dict]) -> List[dict]:
    """Remove duplicate examples based on ID."""
    seen = set()
    unique = []
    for entry in entries:
        eid = entry.get("id", "")
        if eid and eid not in seen:
            seen.add(eid)
            unique.append(entry)
    return unique


# ─────────────────────────────────────────
# Quality filter
# ─────────────────────────────────────────
MIN_EXPLANATION_LENGTH = 50   # characters
MIN_REMEDIATION_STEPS  = 2    # minimum fix suggestions


def is_quality_knowledge(entry: dict) -> bool:
    """Check if a knowledge entry meets quality bar."""
    if len(entry.get("why_dangerous", "")) < MIN_EXPLANATION_LENGTH:
        return False
    if len(entry.get("remediation", [])) < MIN_REMEDIATION_STEPS:
        return False
    return True


def is_quality_example(entry: dict) -> bool:
    """Check if a training example meets quality bar."""
    output = entry.get("output", {})
    if not output.get("explanation") and not output.get("summary"):
        return False
    if len(str(output)) < 100:
        return False
    return True


# ─────────────────────────────────────────
# Expand knowledge base → additional instruction pairs
# ─────────────────────────────────────────
def expand_knowledge_to_examples(kb_entries: List[dict]) -> List[dict]:
    """
    Convert knowledge base entries into additional instruction-following
    training examples. Each KB entry spawns 2 training pairs:
      1. "What does this dork find?" → explanation
      2. "How do I fix this vulnerability?" → remediation
    """
    examples = []
    for i, entry in enumerate(kb_entries):
        dork     = entry["dork"]
        category = entry["category"]
        risk     = entry["risk"]

        # Pair 1: Dork explanation
        examples.append({
            "id": f"kb_explain_{i:04d}",
            "instruction": "Explain what this dork query targets and what security risks it reveals.",
            "input": {"dork": dork, "category": category},
            "output": {
                "risk_level": risk,
                "what_it_finds": entry["what_it_finds"],
                "explanation": entry["why_dangerous"],
            }
        })

        # Pair 2: Remediation guidance
        examples.append({
            "id": f"kb_fix_{i:04d}",
            "instruction": "Provide remediation steps for this security finding.",
            "input": {
                "category": category,
                "dork": dork,
                "risk_level": risk,
                "finding": entry["what_it_finds"],
            },
            "output": {
                "remediation": entry["remediation"],
                "priority": "immediate" if risk == "critical" else "high" if risk == "high" else "normal",
            }
        })

    return examples


# ─────────────────────────────────────────
# Main
# ─────────────────────────────────────────
def main():
    print("=" * 55)
    print("  ReconMind Training — Step 2: Data Cleaning")
    print("=" * 55)

    # Load collected data
    if not os.path.exists(INPUT_FILE):
        print(f"\n  ERROR: Input file not found: {INPUT_FILE}")
        print("  Run Step 1 first: python pipeline/01_collect.py")
        sys.exit(1)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    kb_raw = data.get("knowledge_base", [])
    ex_raw = data.get("training_examples", [])
    print(f"\n  Loaded: {len(kb_raw)} knowledge entries, {len(ex_raw)} examples")

    # ── Normalize ─────────────────────────────────────
    print("\n  Normalizing text fields...")
    kb_normalized = [normalize_entry(e) for e in kb_raw]
    ex_normalized = [normalize_entry(e) for e in ex_raw]

    # ── Deduplicate ───────────────────────────────────
    kb_deduped = deduplicate_knowledge(kb_normalized)
    ex_deduped = deduplicate_examples(ex_normalized)
    print(f"  After deduplication:")
    print(f"    Knowledge: {len(kb_normalized)} → {len(kb_deduped)}")
    print(f"    Examples:  {len(ex_normalized)} → {len(ex_deduped)}")

    # ── Quality filter ────────────────────────────────
    kb_clean = [e for e in kb_deduped if is_quality_knowledge(e)]
    ex_clean = [e for e in ex_deduped if is_quality_example(e)]
    print(f"  After quality filter:")
    print(f"    Knowledge: {len(kb_deduped)} → {len(kb_clean)}")
    print(f"    Examples:  {len(ex_deduped)} → {len(ex_clean)}")

    # ── Expand KB into more training pairs ────────────
    kb_expanded = expand_knowledge_to_examples(kb_clean)
    print(f"\n  Knowledge → Training pairs expanded: {len(kb_expanded)} new examples")

    # ── Combine all examples ──────────────────────────
    all_examples = ex_clean + kb_expanded
    print(f"  Total training examples: {len(all_examples)}")

    # ── Save cleaned output ───────────────────────────
    output = {
        "cleaned_at": datetime.utcnow().isoformat(),
        "stats": {
            "knowledge_entries": len(kb_clean),
            "training_examples": len(all_examples),
            "kb_expanded_pairs": len(kb_expanded),
        },
        "knowledge_base": kb_clean,
        "training_examples": all_examples,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n  ✅ Output saved: {OUTPUT_FILE}")
    print(f"  Total examples ready for dataset creation: {len(all_examples)}")
    print("\n  Next step: python pipeline/03_build_dataset.py")
    print("=" * 55)


if __name__ == "__main__":
    main()
