"""Live progress for the Sonnet 4.6 recovery run kicked off after the main matrix.

Reads data/generated/.last_recovery_run_id + recovery.log and counts rows in the
8 target cells (2 base + 6 dialect for Sonnet).

Usage:
    python scripts/recovery_progress.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

GEN = Path("data/generated")
LOG = GEN / "recovery.log"
RUN_ID_FILE = GEN / ".last_recovery_run_id"

PHASE1 = [("base", "aae", 80), ("base", "midwestern", 80)]
PHASE2 = [("dialect", f, 80) for f in (
    "aae", "southern", "appalachian", "midwestern", "northeastern", "western"
)]
# Rows the file had at recovery start (so we can compute true "new this recovery").
PRE_EXISTING = {("base", "aae"): 64, ("base", "midwestern"): 16}


def count_rows(path: Path, run_id):
    if not path.exists():
        return 0, 0
    total = new = 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        total += 1
        if run_id and r.get("run_id") == run_id:
            new += 1
    return total, new


def main() -> None:
    run_id = RUN_ID_FILE.read_text().strip() if RUN_ID_FILE.exists() else None
    print(f"run_id : {run_id}")

    print("\n=== Phase 1 (base, --resume) ===")
    p1_done = p1_total = 0
    for strat, fam, target in PHASE1:
        p = GEN / f"{strat}__claude-sonnet-4-6__{fam}.jsonl"
        total, new = count_rows(p, run_id)
        p1_done += total
        p1_total += target
        print(f"  {strat:<8}/{fam:<13} {total:>3}/{target} rows  ({new} new this recovery)")

    print("\n=== Phase 2 (dialect, fresh, max_tokens=2500) ===")
    p2_done = p2_total = 0
    for strat, fam, target in PHASE2:
        p = GEN / f"{strat}__claude-sonnet-4-6__{fam}.jsonl"
        total, new = count_rows(p, run_id)
        p2_done += total
        p2_total += target
        state = "exists" if p.exists() else "not yet"
        print(f"  {strat:<8}/{fam:<13} {total:>3}/{target} rows  ({state})")

    elapsed = 0.0
    if LOG.exists():
        try:
            start = LOG.stat().st_birthtime
        except AttributeError:
            start = LOG.stat().st_mtime
        elapsed = (time.time() - start) / 60

    target_total = p1_total + p2_total
    done = p1_done + p2_done
    pre = sum(PRE_EXISTING.values())
    new_records = max(0, done - pre)
    print(f"\noverall : {done}/{target_total} ({100 * done / target_total:.1f}%)  ·  elapsed {elapsed:.1f} min")
    if elapsed > 0 and new_records > 0:
        rate = new_records / elapsed
        remaining = target_total - done
        print(f"new this recovery: {new_records}  ·  rate {rate:.1f} rec/min  ·  ~remaining {remaining / rate:.0f} min")

    print("\n=== tail of recovery.log ===")
    if LOG.exists():
        for line in LOG.read_text().splitlines()[-6:]:
            print(f"  {line}")


if __name__ == "__main__":
    main()
