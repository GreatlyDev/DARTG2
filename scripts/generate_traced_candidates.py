import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.assignments import anchor_identifier
from dart_pipeline.generation import OpenAIResponsesClient, extract_output_text, load_env_file, sleep_between_calls, utc_now
from dart_pipeline.inventories import load_feature_inventory
from dart_pipeline.io_utils import read_records, write_jsonl
from dart_pipeline.trace_generation import (
    build_trace_generation_input,
    detect_student_text_corrections,
    family_output_key,
    parse_model_json,
    traced_candidate_response,
)


def anchor_text(anchor: dict) -> str:
    return anchor.get("anchor_response") or anchor.get("essay") or anchor.get("text") or ""


def index_by_anchor_id(rows: list[dict]) -> dict[str, dict]:
    return {anchor_identifier(row): row for row in rows}


def load_known_forms(raw: str) -> set[str]:
    return {part.strip() for part in raw.split(",") if part.strip()}


def load_api_key(env_file: Path) -> str:
    load_env_file(env_file)
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise SystemExit(f"OPENAI_API_KEY is not set. Add it to {env_file} or the current environment.")
    return key


def assignment_rows(args: argparse.Namespace, anchors: list[dict]) -> list[dict]:
    if args.assignments:
        return read_records(args.assignments)
    if not args.family:
        raise SystemExit("Either --family or --assignments is required.")
    return [
        {
            "anchor_id": anchor_identifier(anchor),
            "dialect_family": args.family,
            "target_candidates": 1,
        }
        for anchor in anchors
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate trace-style DART candidates with applied/rejected feature metadata.")
    parser.add_argument("--anchors", required=True, type=Path, help="Anchor CSV/JSONL file.")
    parser.add_argument("--features", default=Path("config/features.index.json"), type=Path)
    parser.add_argument("--template", default=Path("prompts/inventory_trace_v1.txt"), type=Path)
    parser.add_argument("--assignments", type=Path, help="Optional assignment JSONL. If omitted, --family is applied to each anchor.")
    parser.add_argument("--family", help="Dialect family to apply to each anchor when --assignments is omitted.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="gpt-5.2")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-output-tokens", type=int, default=900)
    parser.add_argument(
        "--known-student-forms",
        default="",
        help="Comma-separated student spellings/word forms that must not be silently corrected.",
    )
    parser.add_argument("--env-file", default=Path(".env"), type=Path)
    parser.add_argument("--print-output", action="store_true")
    args = parser.parse_args()

    anchors = read_records(args.anchors)
    anchors_by_id = index_by_anchor_id(anchors)
    inventory = load_feature_inventory(args.features)
    assignments = assignment_rows(args, anchors)
    if args.limit is not None:
        assignments = assignments[: args.limit]

    existing_rows = read_records(args.output) if args.output.exists() and args.resume else []
    seen = {str(row.get("trace_id")) for row in existing_rows if row.get("trace_id")}
    known_forms = load_known_forms(args.known_student_forms)
    client = OpenAIResponsesClient(
        api_key=load_api_key(args.env_file),
        model=args.model,
        timeout=args.timeout,
        max_output_tokens=args.max_output_tokens,
    )

    rows = list(existing_rows)
    total = len(assignments)
    for index, assignment in enumerate(assignments, start=1):
        anchor_id = str(assignment["anchor_id"])
        dialect_family = str(assignment["dialect_family"])
        trace_id = f"{anchor_id}_{dialect_family.replace(' ', '_').replace('/', '_')}_trace"
        if trace_id in seen:
            continue

        anchor = anchors_by_id[anchor_id]
        anchor_response = anchor_text(anchor)
        feature_config = inventory[dialect_family]
        prompt = build_trace_generation_input(args.template, dialect_family, anchor_response, feature_config)

        print(f"[{index}/{total}] Generating trace {trace_id}")
        started_at = utc_now()
        response = client.create(prompt)
        finished_at = utc_now()
        raw_output = extract_output_text(response)
        parsed_output, parse_error = parse_model_json(raw_output)
        status = "ok" if parsed_output is not None else "parse_error"
        candidate_response = ""
        corrections: list[str] = []

        record = {
            "trace_id": trace_id,
            "anchor_id": anchor_id,
            "dialect_family": dialect_family,
            "output_key": family_output_key(dialect_family),
            "prompt_version": args.template.stem,
            "model": args.model,
            "generation_status": status,
            "anchor_text": anchor_response,
            "candidate_response": candidate_response,
            "parsed_output": parsed_output,
            "raw_output": raw_output,
            "parse_error": parse_error,
            "detected_student_corrections": corrections,
            "openai_response_id": response.get("id"),
            "usage": response.get("usage", {}),
            "started_at": started_at,
            "finished_at": finished_at,
        }
        record["candidate_response"] = traced_candidate_response(record)
        if parsed_output:
            applied = parsed_output.get("applied_features", [])
            corrections = detect_student_text_corrections(
                anchor_response,
                record["candidate_response"],
                applied_features=applied if isinstance(applied, list) else [],
                known_student_forms=known_forms,
            )
            record["detected_student_corrections"] = corrections
            if corrections:
                record["generation_status"] = "needs_review_student_text_correction"

        rows.append(record)
        write_jsonl(args.output, rows)

        if args.print_output:
            print(record["candidate_response"])
            if record["detected_student_corrections"]:
                print("Possible corrections: " + "; ".join(record["detected_student_corrections"]))
            print("-" * 80)

        sleep_between_calls(args.sleep)

    print(f"Wrote {len(rows)} trace records to {args.output}")


if __name__ == "__main__":
    main()
