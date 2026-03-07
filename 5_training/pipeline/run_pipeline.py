"""
ReconMind — training/pipeline/run_pipeline.py
Master pipeline runner. Runs all 5 steps in sequence.

Usage:
  python pipeline/run_pipeline.py           → run all steps
  python pipeline/run_pipeline.py --from 3  → start from step 3
  python pipeline/run_pipeline.py --only 1  → run only step 1
"""

import argparse
import importlib
import os
import sys
import time
from datetime import datetime

STEPS = [
    ("01_collect",      "Step 1: Data Collection"),
    ("02_clean",        "Step 2: Data Cleaning"),
    ("03_build_dataset","Step 3: Build Dataset"),
    ("04_finetune",     "Step 4: Fine-tuning"),
    ("05_evaluate",     "Step 5: Evaluation"),
]


def run_step(module_name: str, label: str) -> bool:
    print(f"\n{'═'*55}")
    print(f"  RUNNING: {label}")
    print(f"{'═'*55}\n")
    start = time.time()
    try:
        mod = importlib.import_module(f"pipeline.{module_name}")
        if hasattr(mod, "main"):
            mod.main()
        elapsed = time.time() - start
        print(f"\n  ✅ {label} completed in {elapsed:.1f}s")
        return True
    except SystemExit as e:
        if e.code == 0:
            return True
        print(f"\n  ❌ {label} exited with code {e.code}")
        return False
    except Exception as e:
        print(f"\n  ❌ {label} failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="ReconMind Training Pipeline")
    parser.add_argument("--from",  dest="from_step", type=int, default=1,
                        help="Start from step N (1-5)")
    parser.add_argument("--only",  dest="only_step", type=int, default=None,
                        help="Run only step N")
    parser.add_argument("--skip-finetune", action="store_true",
                        help="Skip step 4 (fine-tuning) — useful for dataset prep only")
    args = parser.parse_args()

    print("\n" + "█"*55)
    print("  ReconMind AI Training Pipeline")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("█"*55)

    # Determine which steps to run
    if args.only_step:
        steps_to_run = [STEPS[args.only_step - 1]]
    else:
        steps_to_run = [
            (name, label) for i, (name, label) in enumerate(STEPS, 1)
            if i >= args.from_step
        ]

    if args.skip_finetune:
        steps_to_run = [(n, l) for n, l in steps_to_run if "finetune" not in n]

    print(f"\n  Steps to run: {len(steps_to_run)}")
    for i, (_, label) in enumerate(steps_to_run, 1):
        print(f"    {i}. {label}")

    # Run steps
    total_start = time.time()
    results = {}

    for name, label in steps_to_run:
        success = run_step(name, label)
        results[label] = success
        if not success:
            print(f"\n  Pipeline stopped at: {label}")
            break

    # Summary
    total_elapsed = time.time() - total_start
    print(f"\n\n{'═'*55}")
    print("  PIPELINE SUMMARY")
    print(f"{'═'*55}")
    for label, success in results.items():
        status = "✅" if success else "❌"
        print(f"  {status} {label}")
    print(f"\n  Total time: {total_elapsed:.1f}s")

    all_passed = all(results.values())
    if all_passed:
        print("\n  🎉 Pipeline complete! Proceed to Phase 6: AI Integration.")
    else:
        print("\n  ⚠️  Pipeline had failures. Check output above.")
    print("═"*55)


if __name__ == "__main__":
    main()
