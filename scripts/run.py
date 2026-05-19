"""Run dialect rewrites across a matrix of strategies × models × families.

Calls scripts/run_dialect_rewrite.py once per cell. --resume is always on, so
partial progress is preserved across interruptions. Per-cell output goes to
data/generated/<strategy>__<model>__<family>.jsonl (the runner's default).

Usage:
    python scripts/run.py
    python scripts/run.py --strategies naive,inventory_greedy --models gpt-4o,claude-haiku-4-5
    python scripts/run.py --limit 5  --print-output  # quick dev pass
"""

from __future__ import annotations

import argparse
import csv
import random
import subprocess
import sys
import time
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "scripts" / "run_dialect_rewrite.py"

DEFAULT_STRATEGIES = ["naive", "base", "dialect"]
DEFAULT_FAMILIES = ["aae", "southern", "appalachian", "midwestern", "northeastern", "western"]
DEFAULT_MODELS = ["gpt-4o", "claude-haiku-4-5", "claude-sonnet-4-6"]
DEFAULT_ANCHORS_PATH = Path("data/raw/DART_FINAL_80_ANCHORS.csv")


def _load_anchor_ids(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(f"Anchors file not found: {path}")
    if path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            ids = [str(row.get("essay_id") or row.get("anchor_id") or "").strip() for row in reader]
    else:
        import json
        ids = []
        with path.open("r", encoding="utf-8-sig") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                ids.append(str(row.get("essay_id") or row.get("anchor_id") or "").strip())
    return [i for i in ids if i]


def _build_test_cells(strategies, models, families, anchors_path, count, seed):
    """Stratified random sample of (strategy, model, family, anchor_id) tuples.

    Guarantees every (strategy, model) pair appears at least once when count >= S × M.
    Remaining slots are uniformly random across the full S × M × F space.
    Anchor IDs are drawn uniformly from the anchors file.
    """
    rng = random.Random(seed)
    anchor_ids = _load_anchor_ids(anchors_path)
    if not anchor_ids:
        raise SystemExit(f"No anchor IDs in {anchors_path}")

    cells: list[tuple[str, str, str, str]] = []
    sm_pairs = [(s, m) for s in strategies for m in models]
    rng.shuffle(sm_pairs)

    for s, m in sm_pairs:
        if len(cells) >= count:
            break
        cells.append((s, m, rng.choice(families), rng.choice(anchor_ids)))

    while len(cells) < count:
        s = rng.choice(strategies)
        m = rng.choice(models)
        f = rng.choice(families)
        a = rng.choice(anchor_ids)
        cells.append((s, m, f, a))
    return cells


def parse_csv(value: str, valid: list[str] | None = None) -> list[str]:
    items = [x.strip() for x in value.split(",") if x.strip()]
    if valid is not None:
        for item in items:
            if item not in valid:
                raise argparse.ArgumentTypeError(f"{item!r} is not one of {valid}")
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strategies", default=",".join(DEFAULT_STRATEGIES),
                        help="Comma-separated strategies (default: all three).")
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS),
                        help="Comma-separated model IDs (default: gpt-4o, gpt-5.5, claude-haiku-4-5, claude-sonnet-4-6).")
    parser.add_argument("--families", default=",".join(DEFAULT_FAMILIES),
                        help="Comma-separated families (default: all six).")
    parser.add_argument("--anchors", type=Path, default=None,
                        help="Override --anchors passed to the runner.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Pass --limit N to each cell (cap anchors processed).")
    parser.add_argument("--sleep", type=float, default=0.0,
                        help="--sleep value passed to each cell.")
    parser.add_argument("--max-output-tokens", type=int, default=None,
                        help="Pass --max-output-tokens to each cell.")
    parser.add_argument("--print-output", action="store_true",
                        help="Forward --print-output to each cell.")
    parser.add_argument("--continue-on-error", action="store_true",
                        help="Keep going if a cell fails (default: stop on first failure).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the matrix and the commands that would run, but do not execute.")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: sample N random (strategy, model, family, anchor) tuples and "
                             "run just those, with --limit 1 each. Stratified so every (strategy, model) "
                             "combination appears at least once when N >= strategies × models.")
    parser.add_argument("--test-count", type=int, default=10,
                        help="Number of random calls in --test mode (default: 10).")
    parser.add_argument("--seed", type=int, default=None,
                        help="Seed for --test sampling. Default: random per invocation.")
    parser.add_argument("--run-id", default=None,
                        help="Shared run_id passed to every cell. Defaults to a fresh uuid4 hex per matrix invocation, "
                             "so all cells of one matrix session share the same run_id field in their records.")
    args = parser.parse_args()

    strategies = parse_csv(args.strategies)
    models = parse_csv(args.models)
    families = parse_csv(args.families)

    run_id = args.run_id or uuid.uuid4().hex
    print(f"Matrix run_id: {run_id}")

    anchors_path = args.anchors or DEFAULT_ANCHORS_PATH

    if args.test:
        cells_with_anchor = _build_test_cells(
            strategies, models, families,
            anchors_path=anchors_path,
            count=args.test_count,
            seed=args.seed,
        )
        total = len(cells_with_anchor)
        print(f"TEST mode: {total} random calls "
              f"(seed={args.seed if args.seed is not None else 'random'}). "
              f"Each call processes 1 anchor.")
    else:
        cells_with_anchor = [(s, m, f, None) for s in strategies for m in models for f in families]
        total = len(cells_with_anchor)
        print(f"Matrix: {len(strategies)} strategies × {len(models)} models × {len(families)} families = {total} cells")
        if args.limit is not None:
            print(f"Each cell capped at {args.limit} anchors (--limit). Total calls: up to {total * args.limit}.")

    results: list[tuple[str, str, str, str | None, int, float]] = []
    started_at = time.time()

    for index, (strategy, model, family, anchor_id) in enumerate(cells_with_anchor, start=1):
        cmd = [
            sys.executable, str(RUNNER),
            "--strategy", strategy,
            "--family", family,
            "--model", model,
            "--run-id", run_id,
            "--resume",
        ]
        if args.anchors is not None:
            cmd += ["--anchors", str(args.anchors)]
        if anchor_id is not None:
            cmd += ["--anchor-id", anchor_id, "--limit", "1"]
        elif args.limit is not None:
            cmd += ["--limit", str(args.limit)]
        if args.sleep:
            cmd += ["--sleep", str(args.sleep)]
        if args.max_output_tokens is not None:
            cmd += ["--max-output-tokens", str(args.max_output_tokens)]
        if args.print_output:
            cmd += ["--print-output"]

        label = f"{strategy}/{model}/{family}"
        if anchor_id:
            label += f"  anchor={anchor_id}"
        print(f"\n[{index}/{total}] {label}")
        print(f"  $ {' '.join(cmd)}")

        if args.dry_run:
            results.append((strategy, model, family, anchor_id, 0, 0.0))
            continue

        cell_start = time.time()
        proc = subprocess.run(cmd, cwd=str(REPO_ROOT))
        elapsed = time.time() - cell_start
        results.append((strategy, model, family, anchor_id, proc.returncode, elapsed))
        if proc.returncode != 0 and not args.continue_on_error:
            print(f"\n[FAIL] {label} returned {proc.returncode}; stopping. "
                  f"Re-run with --continue-on-error to keep going.")
            break

    total_elapsed = time.time() - started_at
    print(f"\n=== Matrix summary ({total_elapsed:.0f}s total) ===")
    header = f"{'strategy':<20} {'model':<24} {'family':<14} {'anchor':<10} {'rc':>3} {'sec':>7}"
    print(header)
    print("-" * len(header))
    fail = 0
    for strategy, model, family, anchor_id, rc, elapsed in results:
        marker = "" if rc == 0 else "  ← FAIL"
        if rc != 0:
            fail += 1
        anchor_str = anchor_id if anchor_id else "—"
        print(f"{strategy:<20} {model:<24} {family:<14} {anchor_str:<10} {rc:>3} {elapsed:>7.1f}{marker}")
    print("-" * len(header))
    print(f"{len(results) - fail}/{len(results)} cells succeeded.")


if __name__ == "__main__":
    main()
