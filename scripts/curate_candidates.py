import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.io_utils import read_jsonl, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Curate scored DART candidates for review.")
    parser.add_argument("--candidates", required=True, type=Path, help="Scored candidate JSONL.")
    parser.add_argument("--output", required=True, type=Path, help="Curated passing candidate JSONL.")
    parser.add_argument("--rejections-output", type=Path, help="Optional rejected candidate JSONL.")
    parser.add_argument("--top-n", type=int, default=None, help="Keep top N passing candidates per anchor.")
    args = parser.parse_args()

    rows = read_jsonl(args.candidates)
    passing = [row for row in rows if row.get("passed_quality_filter")]
    rejected = [row for row in rows if not row.get("passed_quality_filter")]

    if args.top_n is not None:
        by_anchor: dict[str, list[dict]] = defaultdict(list)
        for row in passing:
            by_anchor[str(row.get("anchor_id", ""))].append(row)
        selected: list[dict] = []
        for anchor_id, candidates in by_anchor.items():
            candidates.sort(key=lambda row: float(row.get("quality_score") or 0), reverse=True)
            for rank, row in enumerate(candidates[: args.top_n], start=1):
                picked = dict(row)
                picked["selected_reason"] = f"rank {rank}/{len(candidates)} for anchor {anchor_id}"
                selected.append(picked)
        passing = sorted(selected, key=lambda row: (str(row.get("anchor_id", "")), int(row.get("candidate_index") or 0)))

    write_jsonl(args.output, passing)
    if args.rejections_output:
        write_jsonl(args.rejections_output, rejected)

    reason_counts = Counter(reason for row in rejected for reason in row.get("rejection_reasons", []))
    print(f"Input records: {len(rows)}")
    print(f"Curated passing records: {len(passing)}")
    print(f"Rejected records: {len(rejected)}")
    for reason, count in reason_counts.most_common(8):
        print(f"  {reason}: {count}")
    print(f"Wrote curated records to {args.output}")
    if args.rejections_output:
        print(f"Wrote rejected records to {args.rejections_output}")


if __name__ == "__main__":
    main()
