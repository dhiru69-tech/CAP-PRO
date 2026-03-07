"""
ReconMind — training/pipeline/03_build_dataset.py
Step 3: Build training dataset in model-ready format.

Converts cleaned data into instruction-following JSONL format
compatible with standard fine-tuning frameworks:
  - HuggingFace TRL (SFTTrainer)
  - Axolotl
  - LLaMA-Factory
  - OpenAI fine-tuning format (optional)

Output format (ChatML / conversation format):
  {
    "messages": [
      {"role": "system",   "content": "..."},
      {"role": "user",     "content": "..."},
      {"role": "assistant","content": "..."}
    ]
  }

Outputs:
  - data/datasets/train.jsonl       (80%)
  - data/datasets/validation.jsonl  (15%)
  - data/datasets/test.jsonl        (5%)
  - data/datasets/dataset_info.json (metadata)
"""

import json
import os
import random
import sys
from datetime import datetime
from typing import List, Dict, Any, Tuple

# ─────────────────────────────────────────
# Paths
# ─────────────────────────────────────────
BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEANED_DIR  = os.path.join(BASE_DIR, "data", "cleaned")
DATASET_DIR  = os.path.join(BASE_DIR, "data", "datasets")
INPUT_FILE   = os.path.join(CLEANED_DIR, "cleaned.json")

os.makedirs(DATASET_DIR, exist_ok=True)

# ─────────────────────────────────────────
# System prompt
# ─────────────────────────────────────────
SYSTEM_PROMPT = """You are ReconMind AI, a specialized security analysis assistant.

Your role is to:
1. Analyze URLs and files discovered during web reconnaissance
2. Classify security findings by risk level (critical/high/medium/low/info)
3. Explain why each finding is dangerous in clear, technical terms
4. Provide specific, actionable remediation steps
5. Generate scan summary reports with prioritized recommendations

You have deep knowledge of:
- Google dork queries and what they expose
- Common web application vulnerabilities
- Credential and data exposure patterns
- Security misconfigurations
- Compliance implications (GDPR, PCI-DSS, HIPAA)

Always be precise, factual, and security-focused. Never speculate beyond what the evidence shows."""


# ─────────────────────────────────────────
# Format converters
# ─────────────────────────────────────────
def format_output(output: dict) -> str:
    """Convert an output dict to clean markdown-formatted text."""
    parts = []

    # Risk level
    if "risk_level" in output:
        risk = output["risk_level"].upper()
        emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢", "INFO": "ℹ️"}.get(risk, "")
        parts.append(f"**Risk Level:** {emoji} {risk}")

    # Title
    if "title" in output:
        parts.append(f"\n**Finding:** {output['title']}")

    # Overall risk for summaries
    if "overall_risk" in output:
        parts.append(f"**Overall Risk:** {output['overall_risk'].upper()}")

    # Explanation / Summary
    for key in ("explanation", "summary", "what_it_finds"):
        if key in output:
            label = "Summary" if key == "summary" else "Analysis"
            parts.append(f"\n**{label}:**\n{output[key]}")
            break

    # Key concerns
    if "key_concerns" in output:
        parts.append("\n**Key Concerns:**")
        for concern in output["key_concerns"]:
            parts.append(f"- {concern}")

    # Impact
    if "impact" in output:
        parts.append(f"\n**Impact:** {output['impact']}")

    # Remediation / Immediate Actions
    for key in ("remediation", "immediate_actions"):
        if key in output:
            label = "Immediate Actions" if key == "immediate_actions" else "Remediation Steps"
            parts.append(f"\n**{label}:**")
            val = output[key]
            if isinstance(val, list):
                for i, step in enumerate(val, 1):
                    parts.append(f"{i}. {step}")
            elif isinstance(val, str):
                # Split on period or newline into steps
                sentences = [s.strip() for s in val.replace("\n", " ").split(". ") if s.strip()]
                for i, step in enumerate(sentences, 1):
                    parts.append(f"{i}. {step}")
            break

    # Priority
    if "priority" in output:
        parts.append(f"\n**Priority:** {output['priority'].upper()}")

    # Risk score
    if "risk_score" in output:
        parts.append(f"\n**Risk Score:** {output['risk_score']}/10")

    return "\n".join(parts).strip()


def format_input(instruction: str, inp: dict) -> str:
    """Format the user message with instruction + structured input."""
    lines = [instruction, ""]

    if "url" in inp:
        lines.append(f"**URL:** `{inp['url']}`")
    if "dork" in inp:
        lines.append(f"**Dork Query:** `{inp['dork']}`")
    if "category" in inp:
        lines.append(f"**Category:** {inp['category']}")
    if "http_status" in inp:
        lines.append(f"**HTTP Status:** {inp['http_status']}")
    if "title" in inp and inp["title"]:
        lines.append(f"**Page Title:** {inp['title']}")
    if "snippet" in inp and inp["snippet"]:
        lines.append(f"**Content Preview:** {inp['snippet'][:200]}")
    if "redirect_url" in inp and inp["redirect_url"]:
        lines.append(f"**Redirects To:** {inp['redirect_url']}")
    if "target" in inp:
        lines.append(f"**Target:** {inp['target']}")
    if "total_urls_found" in inp:
        lines.append(f"**URLs Found:** {inp['total_urls_found']}")
    if "findings_by_risk" in inp:
        findings = inp["findings_by_risk"]
        lines.append(f"**Findings:** Critical={findings.get('critical',0)} High={findings.get('high',0)} Medium={findings.get('medium',0)} Low={findings.get('low',0)}")

    return "\n".join(lines).strip()


def example_to_chatml(example: dict) -> dict:
    """Convert a training example to ChatML conversation format."""
    user_content    = format_input(example["instruction"], example["input"])
    assistant_content = format_output(example["output"])

    return {
        "messages": [
            {"role": "system",    "content": SYSTEM_PROMPT},
            {"role": "user",      "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ]
    }


# ─────────────────────────────────────────
# Split dataset
# ─────────────────────────────────────────
def split_dataset(
    examples: List[dict],
    train_ratio: float = 0.80,
    val_ratio:   float = 0.15,
    seed: int = 42,
) -> Tuple[List, List, List]:
    """Shuffle and split into train / validation / test sets."""
    rng = random.Random(seed)
    shuffled = examples.copy()
    rng.shuffle(shuffled)

    n      = len(shuffled)
    n_train = int(n * train_ratio)
    n_val   = int(n * val_ratio)

    train = shuffled[:n_train]
    val   = shuffled[n_train : n_train + n_val]
    test  = shuffled[n_train + n_val:]

    return train, val, test


# ─────────────────────────────────────────
# JSONL writer
# ─────────────────────────────────────────
def write_jsonl(records: List[dict], filepath: str):
    with open(filepath, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ─────────────────────────────────────────
# Main
# ─────────────────────────────────────────
def main():
    print("=" * 55)
    print("  ReconMind Training — Step 3: Build Dataset")
    print("=" * 55)

    if not os.path.exists(INPUT_FILE):
        print(f"\n  ERROR: Input not found: {INPUT_FILE}")
        print("  Run Step 2 first: python pipeline/02_clean.py")
        sys.exit(1)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    examples = data.get("training_examples", [])
    print(f"\n  Loaded {len(examples)} training examples")

    # ── Convert to ChatML ──────────────────────────────
    print("  Converting to ChatML format...")
    chatml_records = []
    failed = 0
    for ex in examples:
        try:
            record = example_to_chatml(ex)
            chatml_records.append(record)
        except Exception as e:
            failed += 1
            print(f"  [WARN] Failed to convert {ex.get('id', '?')}: {e}")

    print(f"  Converted: {len(chatml_records)} | Failed: {failed}")

    # ── Split ──────────────────────────────────────────
    train, val, test = split_dataset(chatml_records)
    print(f"\n  Dataset split:")
    print(f"    Train      : {len(train)} examples (80%)")
    print(f"    Validation : {len(val)} examples (15%)")
    print(f"    Test       : {len(test)} examples (5%)")

    # ── Token estimate ────────────────────────────────
    sample_chars = sum(
        len(json.dumps(r)) for r in chatml_records[:10]
    ) / max(len(chatml_records[:10]), 1)
    avg_tokens = int(sample_chars / 4)   # rough: 4 chars per token
    total_tokens = avg_tokens * len(chatml_records)
    print(f"\n  Token estimate:")
    print(f"    Avg per example  : ~{avg_tokens:,} tokens")
    print(f"    Total (all sets) : ~{total_tokens:,} tokens")

    # ── Write JSONL files ──────────────────────────────
    train_file = os.path.join(DATASET_DIR, "train.jsonl")
    val_file   = os.path.join(DATASET_DIR, "validation.jsonl")
    test_file  = os.path.join(DATASET_DIR, "test.jsonl")
    info_file  = os.path.join(DATASET_DIR, "dataset_info.json")

    write_jsonl(train, train_file)
    write_jsonl(val, val_file)
    write_jsonl(test, test_file)

    dataset_info = {
        "name": "ReconMind Security Analysis Dataset",
        "version": "1.0.0",
        "created_at": datetime.utcnow().isoformat(),
        "format": "ChatML (system/user/assistant)",
        "base_model_recommended": "mistralai/Mistral-7B-Instruct-v0.2",
        "splits": {
            "train": len(train),
            "validation": len(val),
            "test": len(test),
            "total": len(chatml_records),
        },
        "estimated_tokens": {
            "per_example_avg": avg_tokens,
            "total": total_tokens,
        },
        "files": {
            "train": "train.jsonl",
            "validation": "validation.jsonl",
            "test": "test.jsonl",
        },
        "task_types": [
            "finding_classification",
            "risk_assessment",
            "remediation_generation",
            "dork_explanation",
            "scan_summary_generation",
        ]
    }

    with open(info_file, "w", encoding="utf-8") as f:
        json.dump(dataset_info, f, indent=2)

    print(f"\n  ✅ Dataset files written:")
    print(f"    {train_file}")
    print(f"    {val_file}")
    print(f"    {test_file}")
    print(f"    {info_file}")
    print("\n  Next step: python pipeline/04_finetune.py")
    print("=" * 55)


if __name__ == "__main__":
    main()
