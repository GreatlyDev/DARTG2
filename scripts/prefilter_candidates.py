import argparse
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.inventories import load_feature_inventory
from dart_pipeline.io_utils import read_jsonl, write_jsonl
from dart_pipeline.prefilter import prefilter_candidate


def main() -> None:
    parser = argparse.ArgumentParser(description="Run lightweight DART candidate pre-filter checks.")
    parser.add_argument("--candidates", required=True, type=Path, help="Candidate JSONL with anchor_response and candidate_text.")
    parser.add_argument("--features", default=Path("config/features.index.json"), type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--length-tolerance", type=float, default=0.20)
    parser.add_argument("--min-features", type=int, default=2)
    args = parser.parse_args()

    inventory = load_feature_inventory(args.features)
    results: list[dict] = []
    for row in read_jsonl(args.candidates):
        dialect_family = row["dialect_family"]
        result = prefilter_candidate(
            row.get("anchor_response", ""),
            row.get("candidate_text", ""),
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

