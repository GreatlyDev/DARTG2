import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.inventories import flatten_allowed_features, load_feature_inventory
from dart_pipeline.io_utils import read_jsonl, write_jsonl
from dart_pipeline.scoring import score_candidate_row


def main() -> None:
    parser = argparse.ArgumentParser(description="Score DART candidate variants with cheap similarity and cleanup checks.")
    parser.add_argument("--candidates", required=True, type=Path, help="Candidate JSONL to score.")
    parser.add_argument("--features", default=Path("config/features.index.json"), type=Path)
    parser.add_argument("--output", required=True, type=Path, help="Scored output JSONL.")
    parser.add_argument("--min-change", type=float, default=0.10)
    parser.add_argument("--max-length-delta", type=float, default=0.20)
    parser.add_argument("--min-word-count", type=int, default=10)
    args = parser.parse_args()

    inventory = load_feature_inventory(args.features)
    rows = []
    for row in read_jsonl(args.candidates):
        feature_config = inventory.get(str(row.get("dialect_family", "")), {})
        rows.append(
            score_candidate_row(
                row,
                min_change=args.min_change,
                max_length_delta=args.max_length_delta,
                min_word_count=args.min_word_count,
                allowed_feature_markers=set(flatten_allowed_features(feature_config)),
            )
        )

    write_jsonl(args.output, rows)
    passing = sum(1 for row in rows if row.get("passed_quality_filter"))
    rejected_cleanup = sum(1 for row in rows if "student_text_correction" in (row.get("rejection_reasons") or []))
    print(f"Wrote {len(rows)} scored records to {args.output}")
    print(f"Passed quality filter: {passing}")
    print(f"Rejected for student text correction: {rejected_cleanup}")


if __name__ == "__main__":
    main()
