import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.inventories import flatten_allowed_features, load_feature_inventory
from dart_pipeline.io_utils import read_jsonl, read_records, write_jsonl
from dart_pipeline.scoring import score_candidate_row


def _anchor_text(anchor: dict) -> str:
    return anchor.get("anchor_response") or anchor.get("essay") or anchor.get("text") or ""


def _anchor_lookup(path: Path | None) -> dict[str, str]:
    if not path:
        return {}
    lookup: dict[str, str] = {}
    for row in read_records(path):
        anchor_id = str(row.get("anchor_id") or row.get("essay_id") or "")
        if anchor_id:
            lookup[anchor_id] = _anchor_text(row)
    return lookup


def main() -> None:
    parser = argparse.ArgumentParser(description="Score DART candidate variants with cheap similarity and cleanup checks.")
    parser.add_argument("--anchors", type=Path, help="Optional anchor CSV/JSONL for candidate files that only contain anchor_id.")
    parser.add_argument("--candidates", required=True, type=Path, help="Candidate JSONL to score.")
    parser.add_argument("--features", default=Path("config/features.index.json"), type=Path)
    parser.add_argument("--output", required=True, type=Path, help="Scored output JSONL.")
    parser.add_argument("--min-change", type=float, default=0.10)
    parser.add_argument("--max-length-delta", type=float, default=0.20)
    parser.add_argument("--min-word-count", type=int, default=10)
    args = parser.parse_args()

    inventory = load_feature_inventory(args.features)
    anchors = _anchor_lookup(args.anchors)
    rows = []
    for row in read_jsonl(args.candidates):
        scored_input = dict(row)
        anchor_id = str(scored_input.get("anchor_id") or "")
        if not (scored_input.get("anchor_response") or scored_input.get("anchor_text")) and anchor_id in anchors:
            scored_input["anchor_response"] = anchors[anchor_id]
        feature_config = inventory.get(str(row.get("dialect_family", "")), {})
        rows.append(
            score_candidate_row(
                scored_input,
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
