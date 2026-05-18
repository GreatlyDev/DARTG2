import argparse
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.inventories import load_feature_inventory
from dart_pipeline.io_utils import read_jsonl, read_records, write_jsonl
from dart_pipeline.prefilter import prefilter_candidate
from dart_pipeline.trace_generation import traced_candidate_response


def _anchor_text(anchor: dict) -> str:
    return anchor.get("anchor_response") or anchor.get("essay") or anchor.get("text") or ""


def _anchor_lookup(path: Path | None) -> dict[str, str]:
    if not path:
        return {}
    rows = read_records(path)
    lookup: dict[str, str] = {}
    for row in rows:
        anchor_id = str(row.get("anchor_id") or row.get("essay_id") or "")
        if anchor_id:
            lookup[anchor_id] = _anchor_text(row)
    return lookup


def _candidate_text(row: dict) -> str:
    return row.get("candidate_text") or row.get("candidate_response") or traced_candidate_response(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run lightweight DART candidate pre-filter checks.")
    parser.add_argument("--anchors", type=Path, help="Optional anchor CSV/JSONL for candidate files that only contain anchor_id.")
    parser.add_argument("--candidates", required=True, type=Path, help="Candidate JSONL with candidate_response or candidate_text.")
    parser.add_argument("--features", default=Path("config/features.index.json"), type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--length-tolerance", type=float, default=0.20)
    parser.add_argument("--min-features", type=int, default=2)
    args = parser.parse_args()

    inventory = load_feature_inventory(args.features)
    anchors = _anchor_lookup(args.anchors)
    results: list[dict] = []
    for row in read_jsonl(args.candidates):
        dialect_family = row["dialect_family"]
        anchor_id = str(row.get("anchor_id") or "")
        anchor_response = row.get("anchor_response") or row.get("anchor_text") or anchors.get(anchor_id, "")
        result = prefilter_candidate(
            anchor_response,
            _candidate_text(row),
            inventory[dialect_family],
            length_tolerance=args.length_tolerance,
            min_detected_features=args.min_features,
        )
        merged = dict(row)
        merged.update(asdict(result))
        results.append(merged)

    write_jsonl(args.output, results)
    print(f"Wrote {len(results)} pre-filter results to {args.output}")


if __name__ == "__main__":
    main()

