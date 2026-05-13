import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.assignments import anchor_identifier
from dart_pipeline.io_utils import read_records, write_jsonl


DEMO_PLAN = [
    {
        "essay_id": "11926",
        "dialect_family": "Southern American English",
        "demo_reason": "LOW score band from ASAP-AES",
    },
    {
        "essay_id": "4019",
        "dialect_family": "Midwestern/North Central",
        "demo_reason": "MID score band from ASAP-AES",
    },
    {
        "essay_id": "6291",
        "dialect_family": "Northeastern/New England",
        "demo_reason": "HIGH score band from ASAP++",
    },
    {
        "essay_id": "AAAOPP13416000055599",
        "dialect_family": "Western American English",
        "demo_reason": "LOW score band from ASAP_2.0",
    },
    {
        "essay_id": "16334",
        "dialect_family": "Appalachian English",
        "demo_reason": "MID score band from ASAP++",
    },
    {
        "essay_id": "AAAOPP13416000037047",
        "dialect_family": "African American English (AAE)",
        "demo_reason": "HIGH score band from ASAP_2.0",
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the curated final-80 Stage 1 demo assignment file.")
    parser.add_argument("--anchors", required=True, type=Path, help="Student 1 final anchor CSV/JSONL.")
    parser.add_argument("--output", required=True, type=Path, help="Output assignment JSONL.")
    parser.add_argument("--candidates", type=int, default=3, help="Candidates per demo anchor-dialect pair.")
    args = parser.parse_args()

    anchors = {anchor_identifier(row): row for row in read_records(args.anchors)}
    assignments = []
    for item in DEMO_PLAN:
        anchor = anchors[item["essay_id"]]
        assignments.append(
            {
                "anchor_id": item["essay_id"],
                "dialect_family": item["dialect_family"],
                "target_candidates": args.candidates,
                "assignment_strategy": "curated_demo",
                "source_corpus": anchor.get("source_corpus") or anchor.get("dataset"),
                "score_band": anchor.get("score_band"),
                "domain": anchor.get("domain") or anchor.get("prompt_group") or anchor.get("task"),
                "demo_reason": item["demo_reason"],
            }
        )

    write_jsonl(args.output, assignments)
    print(f"Wrote {len(assignments)} curated demo assignments to {args.output}")


if __name__ == "__main__":
    main()
