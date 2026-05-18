import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.assignments import anchor_identifier
from dart_pipeline.inventories import load_feature_inventory
from dart_pipeline.io_utils import read_records, write_jsonl
from dart_pipeline.prompts import render_generation_prompt


def index_by_anchor_id(rows: list[dict]) -> dict[str, dict]:
    return {anchor_identifier(row): row for row in rows}


def anchor_text(anchor: dict) -> str:
    return anchor.get("anchor_response") or anchor.get("essay") or anchor.get("text") or ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Render generation prompt jobs for DART Student 2.")
    parser.add_argument("--anchors", required=True, type=Path, help="Input anchor JSONL file.")
    parser.add_argument("--assignments", required=True, type=Path, help="Anchor-to-dialect assignment JSONL.")
    parser.add_argument("--features", default=Path("config/features.index.json"), type=Path)
    parser.add_argument("--template", default=Path("prompts/base.md"), type=Path)
    parser.add_argument("--output", required=True, type=Path, help="Output prompt jobs JSONL.")
    args = parser.parse_args()

    anchors = index_by_anchor_id(read_records(args.anchors))
    assignments = read_records(args.assignments)
    inventory = load_feature_inventory(args.features)
    jobs: list[dict] = []

    for assignment in assignments:
        anchor_id = str(assignment["anchor_id"])
        anchor = anchors[anchor_id]
        dialect_family = assignment["dialect_family"]
        feature_config = inventory[dialect_family]
        assignment_prompt = anchor.get("prompt", "[PROMPT NOT PROVIDED]")
        anchor_response = anchor_text(anchor)
        rendered = render_generation_prompt(
            args.template,
            assignment_prompt,
            anchor_response,
            dialect_family,
            feature_config,
        )
        for candidate_index in range(1, int(assignment.get("target_candidates", 3)) + 1):
            jobs.append(
                {
                    "job_id": f"{anchor_id}_{dialect_family.replace(' ', '_')}_{candidate_index}",
                    "anchor_id": anchor_id,
                    "dialect_family": dialect_family,
                    "candidate_index": candidate_index,
                    "prompt_version": args.template.stem,
                    "generation_prompt": rendered,
                }
            )

    write_jsonl(args.output, jobs)
    print(f"Wrote {len(jobs)} prompt jobs to {args.output}")


if __name__ == "__main__":
    main()



