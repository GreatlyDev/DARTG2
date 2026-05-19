"""Curate the best dialect-rewrite records from the matrix.

Reads data/generated/*__*__*.jsonl, applies a quality filter, and writes a curated
winners JSONL — by default, one record per anchor (the highest quality_score across
all 9 cells of the matrix).

Quality formula: quality_score = composite_change_score × hf_cosine
Records that pass the filter are also tagged with `usable=true` and `quality_score`.

Usage:
    python scripts/curate.py                            # default: 80 records, one per anchor
    python scripts/curate.py --top-n 3                  # 3 best variants per anchor
    python scripts/curate.py --include-all-usable       # everything that passes the filter
    python scripts/curate.py --strategies base,naive    # restrict source pool
    python scripts/curate.py --min-change 0.4 --min-cosine 0.9   # stricter thresholds
    python scripts/curate.py --dry-run                  # print stats only
"""

from __future__ import annotations

import argparse
import glob
import json
from collections import defaultdict
from pathlib import Path

DEFAULT_INPUT_GLOB = "data/generated/*__*__*.jsonl"
DEFAULT_OUTPUT = Path("data/generated/winners.jsonl")


def hf_cosine(row: dict) -> float:
    s = row.get("similarity_scores") or {}
    cos = (s.get("cosine_embeddings") or {}).get("hf/all-MiniLM-L6-v2")
    return float(cos) if cos is not None else 0.0


def quality_score(row: dict) -> float:
    """composite_change × hf_cosine — single rank-able number, higher = better.

    Penalizes records that are either too unchanged OR have drifted semantically.
    """
    change = float(row.get("composite_change_score") or 0)
    cos = hf_cosine(row)
    base = change * cos
    # Small bonus for dialect strategy when applied_features fired (real, attributed transformation).
    if row.get("strategy") == "dialect":
        n_features = len(row.get("applied_features") or [])
        base *= 1 + 0.1 * min(n_features, 3)
    return round(base, 4)


def is_usable(
    row: dict,
    *,
    min_change: float,
    min_cosine: float,
    min_length_ratio: float,
    max_length_ratio: float,
    min_word_ratio: float,
    max_word_ratio: float,
) -> tuple[bool, str]:
    """Returns (usable, reason_if_not)."""
    if row.get("generation_status") != "ok":
        return False, f"status={row.get('generation_status')}"
    if row.get("refused"):
        return False, "refused"

    awc = row.get("anchor_word_count") or 0
    rwc = row.get("rewrite_word_count") or 0
    if awc > 0:
        ratio = rwc / awc
        if ratio < min_word_ratio:
            return False, f"word_ratio={ratio:.2f} < {min_word_ratio}"
        if ratio > max_word_ratio:
            return False, f"word_ratio={ratio:.2f} > {max_word_ratio}"

    s = row.get("similarity_scores") or {}
    lr = s.get("length_ratio", 0)
    if lr < min_length_ratio:
        return False, f"length_ratio={lr:.2f} < {min_length_ratio}"
    if lr > max_length_ratio:
        return False, f"length_ratio={lr:.2f} > {max_length_ratio}"

    cos = hf_cosine(row)
    if cos < min_cosine:
        return False, f"hf_cosine={cos:.2f} < {min_cosine}"

    change = float(row.get("composite_change_score") or 0)
    if change < min_change:
        return False, f"composite_change={change:.2f} < {min_change}"

    return True, ""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", default=DEFAULT_INPUT_GLOB, help=f"Input glob (default: {DEFAULT_INPUT_GLOB}).")
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"Output JSONL (default: {DEFAULT_OUTPUT}).")
    p.add_argument("--top-n", type=int, default=1, help="Top N variants per anchor (default: 1).")
    p.add_argument("--include-all-usable", action="store_true",
                   help="Skip per-anchor ranking; keep every record that passes the filter.")
    p.add_argument("--strategies", default=None, help="Comma-separated. Only consider these strategies.")
    p.add_argument("--models", default=None, help="Comma-separated. Only consider these models.")
    p.add_argument("--families", default=None, help="Comma-separated. Only consider these families.")
    # Filter thresholds
    p.add_argument("--min-change", type=float, default=0.20)
    p.add_argument("--min-cosine", type=float, default=0.80)
    p.add_argument("--min-length-ratio", type=float, default=0.30,
                   help="Drop records where rewrite_chars / anchor_chars is below this (catches content-mod refusals).")
    p.add_argument("--max-length-ratio", type=float, default=3.0)
    p.add_argument("--min-word-ratio", type=float, default=0.50)
    p.add_argument("--max-word-ratio", type=float, default=2.50)
    p.add_argument("--dry-run", action="store_true", help="Print stats but don't write the output file.")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    rows: list[dict] = []
    for f in sorted(glob.glob(args.input)):
        for line in Path(f).read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))

    if args.strategies:
        wanted = set(s.strip() for s in args.strategies.split(",") if s.strip())
        rows = [r for r in rows if r.get("strategy") in wanted]
    if args.models:
        wanted = set(s.strip() for s in args.models.split(",") if s.strip())
        rows = [r for r in rows if r.get("model") in wanted]
    if args.families:
        wanted = set(s.strip() for s in args.families.split(",") if s.strip())
        rows = [r for r in rows if r.get("dialect_family") in wanted]

    filter_kwargs = dict(
        min_change=args.min_change,
        min_cosine=args.min_cosine,
        min_length_ratio=args.min_length_ratio,
        max_length_ratio=args.max_length_ratio,
        min_word_ratio=args.min_word_ratio,
        max_word_ratio=args.max_word_ratio,
    )

    # Annotate every row with usable + quality_score.
    rejection_reasons: dict[str, int] = defaultdict(int)
    usable: list[dict] = []
    for r in rows:
        ok, reason = is_usable(r, **filter_kwargs)
        r["usable"] = ok
        r["quality_score"] = quality_score(r)
        if not ok:
            rejection_reasons[reason.split("=")[0] or reason] += 1
        else:
            usable.append(r)

    print(f"Input pool          : {len(rows)} record(s)")
    print(f"Pass filter (usable): {len(usable)}  ({100 * len(usable) / max(1, len(rows)):.1f}%)")
    print()
    print("Top rejection reasons:")
    for reason, count in sorted(rejection_reasons.items(), key=lambda x: -x[1])[:8]:
        print(f"  {reason:<30} {count:>5}")

    if args.include_all_usable:
        selected = sorted(usable, key=lambda r: (r["anchor_id"], -r["quality_score"]))
        print(f"\n--include-all-usable: keeping all {len(selected)} usable records")
    else:
        # Per-anchor top-N by quality_score.
        by_anchor: dict[str, list[dict]] = defaultdict(list)
        for r in usable:
            by_anchor[r["anchor_id"]].append(r)
        selected = []
        for anchor_id, candidates in by_anchor.items():
            candidates.sort(key=lambda r: -r["quality_score"])
            picked = candidates[: args.top_n]
            for rank, p in enumerate(picked, start=1):
                p["selected_reason"] = f"rank {rank}/{len(candidates)} for anchor {anchor_id}"
                selected.append(p)
        selected.sort(key=lambda r: (r["anchor_id"], -r["quality_score"]))
        print(f"\nTop-{args.top_n} per anchor: {len(selected)} records across {len(by_anchor)} anchors")

    # Source attribution.
    print("\nSelected records by source cell:")
    by_sm = defaultdict(int)
    for r in selected:
        by_sm[(r["strategy"], r["model"])] += 1
    for key in sorted(by_sm, key=lambda k: -by_sm[k]):
        s, m = key
        print(f"  {s:<10} {m:<22} {by_sm[key]:>4}")

    if not args.dry_run:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w", encoding="utf-8") as out:
            for r in selected:
                out.write(json.dumps(r, ensure_ascii=True, sort_keys=True) + "\n")
        print(f"\n[ok] wrote {len(selected)} record(s) to {args.output}")


if __name__ == "__main__":
    main()
