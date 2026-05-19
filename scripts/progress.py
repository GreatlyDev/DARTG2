"""Print live progress of an in-flight matrix run.

Reads data/generated/*__*__*.jsonl and data/generated/matrix.log, prints:
  - cells completed and records written
  - elapsed time and current rate (records/min)
  - estimated remaining time
  - the last few lines of matrix.log (which cell + anchor is currently active)

Usage:
    python scripts/progress.py
"""

from __future__ import annotations

import time
from pathlib import Path

GENERATED = Path("data/generated")
LOG = GENERATED / "matrix.log"
TOTAL_RECORDS = 4320  # 54 cells × 80 anchors
TOTAL_CELLS = 54


def main() -> None:
    files = sorted(GENERATED.glob("*__*__*.jsonl"))
    records = sum(1 for f in files for line in f.read_text().splitlines() if line.strip())
    cells_done = sum(1 for f in files if len(f.read_text().splitlines()) >= 80)

    elapsed_min = 0.0
    if LOG.exists():
        try:
            start = LOG.stat().st_birthtime  # macOS
        except AttributeError:
            start = LOG.stat().st_mtime
        elapsed_min = (time.time() - start) / 60

    print(f"files written      : {len(files)}/{TOTAL_CELLS}")
    print(f"cells completed    : {cells_done}/{TOTAL_CELLS}")
    print(f"records written    : {records}/{TOTAL_RECORDS}  ({100 * records / TOTAL_RECORDS:.1f}%)")
    print(f"elapsed            : {elapsed_min:.1f} min  ({elapsed_min/60:.1f} h)")
    if records > 0 and elapsed_min > 0:
        rate = records / elapsed_min
        remaining_min = (TOTAL_RECORDS - records) / rate if rate > 0 else 0
        print(f"rate               : {rate:.1f} records/min")
        print(f"estimated remaining: ~{remaining_min:.0f} min  (~{remaining_min/60:.1f} h)")

    print()
    print("=== latest log lines ===")
    if LOG.exists():
        tail = LOG.read_text().splitlines()[-6:]
        for line in tail:
            print(f"  {line}")
    else:
        print("  (no matrix.log yet)")


if __name__ == "__main__":
    main()
