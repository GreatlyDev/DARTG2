import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.assignments import make_balanced_assignments, make_greedy_assignments
from dart_pipeline.inventories import load_feature_inventory
from dart_pipeline.io_utils import read_records, write_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Build DART anchor-to-dialect assignment files.")
    parser.add_argument("--anchors", required=True, type=Path, help="Input anchor JSONL file.")
    parser.add_argument("--features", default=Path("config/features.index.json"), type=Path, help="Dialect feature inventory JSON.")
    parser.add_argument("--strategy", choices=("greedy", "balanced"), required=True)
    parser.add_argument("--output", required=True, type=Path, help="Output assignment JSONL file.")
    parser.add_argument("--limit", type=int, default=None, help="Optional max anchors to assign.")
    parser.add_argument("--candidates", type=int, default=3, help="Candidates per anchor-dialect pair.")
    args = parser.parse_args()

    anchors = read_records(args.anchors)
    dialects = list(load_feature_inventory(args.features).keys())
    if args.strategy == "greedy":
        assignments = make_greedy_assignments(anchors, dialects, args.candidates, args.limit)
    else:
        assignments = make_balanced_assignments(anchors, dialects, args.candidates, args.limit)
    write_jsonl(args.output, assignments)
    print(f"Wrote {len(assignments)} {args.strategy} assignments to {args.output}")


if __name__ == "__main__":
    main()


