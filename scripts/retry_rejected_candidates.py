import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.generation import OpenAIResponsesClient, generate_candidate_record, load_env_file, sleep_between_calls
from dart_pipeline.io_utils import read_records, write_jsonl


DEFAULT_REJECTION_REASONS = {
    "student_text_correction",
    "generation_failed",
    "candidate_too_short",
    "length_outside_tolerance",
    "insufficient_approved_features",
    "insufficient_change",
}


def target_candidate_ids(scored_rows: list[dict], rejection_reasons: set[str]) -> set[str]:
    targets: set[str] = set()
    for row in scored_rows:
        if row.get("passed_quality_filter"):
            continue
        row_reasons = set(row.get("rejection_reasons") or [])
        if row.get("candidate_id") and row_reasons & rejection_reasons:
            targets.add(str(row["candidate_id"]))
    return targets


def build_retry_prompt(job: dict, rejected_row: dict) -> str:
    reasons = ", ".join(str(reason) for reason in rejected_row.get("rejection_reasons") or [])
    corrections = rejected_row.get("student_text_corrections") or []
    correction_lines = "\n".join(f"- {correction}" for correction in corrections) or "- none listed"
    previous = str(rejected_row.get("candidate_response") or rejected_row.get("raw_output") or "")
    failed_guidance = ""
    if "generation_failed" in (rejected_row.get("rejection_reasons") or []):
        failed_guidance = """
The previous output was FAIL. For this retry, first try the smallest safe variant before deciding the pair is impossible.
Prefer high-precision, meaning-preserving features already licensed by the prompt inventory:
- replace an existing "I think" / "in my opinion" stance phrase with an approved stance marker such as "I reckon" only when the inventory licenses it for this dialect
- replace an existing intensifier such as "very" with an approved regional intensifier only when the inventory licenses it for this dialect
- add an approved discourse marker only when it does not change the claim, evidence, tone, or addressee
Do not add a second-person form such as y'all unless the anchor already addresses multiple readers.
"""
    return f"""{job['generation_prompt']}

RETRY NOTE
The previous candidate for this exact job was rejected by the automated DART prefilter.

Rejected candidate:
{previous}

Rejection reasons:
{reasons}

Student-text cleanup violations detected:
{correction_lines}

Start again from the anchor response in the original prompt, not from the rejected candidate.
Do not correct, normalize, smooth, or improve any spelling, grammar, punctuation, capitalization, wording, spacing, sentence boundaries, or placeholders from the anchor response.
Only change text when that exact local change is required to apply a documented target-dialect feature from the approved inventory.
Use as many approved target-dialect features as naturally fit, but never force a feature by changing meaning or cleaning up student writing.
If the anchor/dialect pair only naturally supports one approved feature, one feature is acceptable.
If no approved feature can be applied without changing meaning or cleaning up student writing, output exactly FAIL.
{failed_guidance}
"""


def replace_records(existing_rows: list[dict], replacements: dict[str, dict]) -> list[dict]:
    output: list[dict] = []
    seen: set[str] = set()
    for row in existing_rows:
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id in replacements:
            output.append(replacements[candidate_id])
            seen.add(candidate_id)
        else:
            output.append(row)
    for candidate_id, row in replacements.items():
        if candidate_id not in seen:
            output.append(row)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate DART candidates rejected by the quality filter.")
    parser.add_argument("--jobs", required=True, type=Path)
    parser.add_argument("--raw-candidates", required=True, type=Path)
    parser.add_argument("--scored-candidates", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--rejection-reasons", default=",".join(sorted(DEFAULT_REJECTION_REASONS)))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-output-tokens", type=int, default=900)
    args = parser.parse_args()

    load_env_file(args.env_file)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set. Put it in your environment or pass --env-file .env.")

    reasons = {reason.strip() for reason in args.rejection_reasons.split(",") if reason.strip()}
    scored_rows = read_records(args.scored_candidates)
    raw_rows = read_records(args.raw_candidates)
    jobs = {str(job.get("job_id")): job for job in read_records(args.jobs)}
    rejected_by_id = {str(row.get("candidate_id")): row for row in scored_rows}
    targets = sorted(target_candidate_ids(scored_rows, reasons))
    if args.limit is not None:
        targets = targets[: args.limit]

    client = OpenAIResponsesClient(
        api_key=api_key,
        model=args.model,
        timeout=args.timeout,
        max_output_tokens=args.max_output_tokens,
    )

    replacements: dict[str, dict] = {}
    total = len(targets)
    for index, candidate_id in enumerate(targets, start=1):
        job = jobs.get(candidate_id)
        rejected = rejected_by_id[candidate_id]
        if not job:
            print(f"[skip] no prompt job found for {candidate_id}")
            continue
        retry_job = dict(job)
        retry_job["generation_prompt"] = build_retry_prompt(job, rejected)
        print(f"[{index}/{total}] Retrying {candidate_id}")
        replacement = generate_candidate_record(retry_job, client, generation_status="demo_unvalidated")
        replacement["retry_of_candidate_id"] = candidate_id
        replacement["retry_rejection_reasons"] = rejected.get("rejection_reasons") or []
        replacement["retry_student_text_corrections"] = rejected.get("student_text_corrections") or []
        replacements[candidate_id] = replacement
        sleep_between_calls(args.sleep)

    output_rows = replace_records(raw_rows, replacements)
    write_jsonl(args.output, output_rows)
    print(f"Retried {len(replacements)} candidate(s).")
    print(f"Wrote {len(output_rows)} candidate records to {args.output}")


if __name__ == "__main__":
    main()
