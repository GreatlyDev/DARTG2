import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.generation import OpenAIResponsesClient, generate_candidate_record, load_env_file, sleep_between_calls
from dart_pipeline.io_utils import read_records, write_jsonl


DEFAULT_REJECTION_REASONS = {
    "anchor_near_duplicate",
    "common_feature_only",
    "student_text_correction",
    "generation_failed",
    "candidate_too_short",
    "length_outside_tolerance",
    "long_anchor_low_feature_count",
    "insufficient_approved_features",
    "insufficient_change",
    "single_detected_feature",
    "surface_change_above_upper_bound",
    "surface_change_below_minimum",
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


def parse_candidate_ids(raw_value: str | None) -> set[str]:
    if not raw_value:
        return set()
    return {candidate_id.strip() for candidate_id in raw_value.split(",") if candidate_id.strip()}


def build_retry_prompt(job: dict, rejected_row: dict) -> str:
    reasons = ", ".join(str(reason) for reason in rejected_row.get("rejection_reasons") or [])
    corrections = rejected_row.get("student_text_corrections") or []
    correction_lines = "\n".join(f"- {correction}" for correction in corrections) or "- none listed"
    previous = str(rejected_row.get("candidate_response") or rejected_row.get("raw_output") or "")
    siblings = rejected_row.get("sibling_candidate_responses") or []
    sibling_lines = "\n".join(
        f"- {item.get('candidate_id')}: {item.get('candidate_response')}"
        for item in siblings
        if isinstance(item, dict)
    ) or "- none listed"
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
    quality_guidance = ""
    row_reasons = set(rejected_row.get("rejection_reasons") or [])
    if "within_anchor_duplicate" in row_reasons:
        quality_guidance += """
The previous output duplicated another candidate for this same anchor. Produce a distinct valid variant for this candidate attempt.
Do not copy the sibling candidate text listed below. Use different approved feature choices or different natural placement of approved features while preserving meaning.
"""
    if "weak_minimal_edit_or_append" in row_reasons:
        quality_guidance += """
The previous output was too close to the anchor or just appended a dialect marker. Do not tack a marker onto the end.
Integrate approved features into existing clauses where they naturally fit. Aim for at least two meaningful, source-backed surface changes when the anchor licenses them.
"""
    if "anchor_near_duplicate" in row_reasons:
        quality_guidance += """
ANCHOR NEAR-DUPLICATE RETRY
The previous output technically used detected features, but it still read like the same anchor with only tiny insertions.
For this retry, make distributed changes across the response using approved target-dialect features already licensed by the anchor.
Do not repeat the same three-token pattern from the rejected output. Prefer different approved feature choices or different natural placements, while preserving meaning and the student's original writing quality.
"""
    if "aae_authenticity_review" in row_reasons:
        quality_guidance += """
The previous AAE output looked inauthentic or over-stacked. Do not combine finna, ain't, gonna, and done in the same short answer.
Avoid "done be" constructions. Prefer one or two natural, documented AAE features that preserve the student's meaning without caricature.
"""
    if "cross_family_tag_right" in row_reasons:
        quality_guidance += """
The previous output used a tag-question "right?" in an inappropriate dialect-family context. Do not use tag-question "right?" for this retry.
Use only approved target-family features from the prompt inventory.
"""
    if row_reasons & {
        "anchor_near_duplicate",
        "insufficient_approved_features",
        "single_detected_feature",
        "common_feature_only",
        "long_anchor_low_feature_count",
        "surface_change_below_minimum",
        "surface_change_above_upper_bound",
    }:
        detected_features = ", ".join(str(feature) for feature in rejected_row.get("detected_features") or []) or "none detected"
        quality_guidance += f"""
FEATURE DIVERSITY RETRY
- Previous detected features: {detected_features}.
- Prefer a rewrite with at least two distinct approved feature placements from the target inventory when the anchor licenses them naturally.
- For longer anchors, prefer 3-5 clear published feature realizations when they fit naturally.
- Keep the rewrite inside the 5%-25% surface-change band when possible: below 5% is usually too minimal, while above 25% risks paraphrase or meaning drift.
- If the previous attempt only used broad/common markers, choose a more context-specific approved lexical, syntactic, or discourse feature instead of repeating only those same markers.
- Distribute feature placements across the response when possible; do not append one marker at the end as the entire transformation.
- Do not force a second feature if doing so would cause semantic drift, add new information, change stance/tone, or clean up student writing.
"""
    if row_reasons & {"anchor_near_duplicate", "within_anchor_duplicate", "weak_minimal_edit_or_append", "targeted_ricky_cleanup"}:
        candidate_index = int(rejected_row.get("candidate_index") or job.get("candidate_index") or 1)
        strategy = {
            1: "Use the strongest natural combination of approved lexical plus syntactic features licensed by the anchor.",
            2: "Use a different approved feature combination and different sentence placement than candidate 1.",
            3: "Use the most natural remaining approved feature combination and avoid matching candidates 1 or 2.",
        }.get(candidate_index, "Use a distinct approved feature combination from the sibling candidates.")
        quality_guidance += f"""
STRICT RICKY QUALITY REQUIREMENTS
- This retry must be meaning-preserving, but it cannot be a near-copy, single-token edit, or phrase appended to the end.
- Do not use only one isolated intensifier or discourse marker as the entire dialect change.
- Use at least two approved target-dialect feature placements if the anchor licenses them naturally.
- If only one approved feature is genuinely possible, integrate it inside an existing sentence and keep this candidate clearly distinct from sibling candidates.
- Preserve original student spelling, grammar, punctuation, capitalization, roughness, and placeholders.
- Candidate-specific diversity strategy: {strategy}
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

Sibling candidate responses for this same anchor:
{sibling_lines}

Start again from the anchor response in the original prompt, not from the rejected candidate.
Do not correct, normalize, smooth, or improve any spelling, grammar, punctuation, capitalization, wording, spacing, sentence boundaries, or placeholders from the anchor response.
Only change text when that exact local change is required to apply a documented target-dialect feature from the approved inventory.
Use as many approved target-dialect features as naturally fit, but never force a feature by changing meaning or cleaning up student writing.
If the anchor/dialect pair only naturally supports one approved feature, one feature is acceptable.
If no approved feature can be applied without changing meaning or cleaning up student writing, output exactly FAIL.
{failed_guidance}
{quality_guidance}
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


def generate_with_retries(
    retry_job: dict,
    client: OpenAIResponsesClient,
    *,
    max_attempts: int,
    retry_wait: float,
) -> dict:
    attempt = 1
    while True:
        try:
            return generate_candidate_record(retry_job, client, generation_status="demo_unvalidated")
        except RuntimeError as exc:
            message = str(exc)
            is_retryable = "429" in message or "rate_limit" in message.lower() or "temporarily" in message.lower()
            if not is_retryable or attempt >= max_attempts:
                raise
            wait = retry_wait * attempt
            print(f"[retryable error] attempt {attempt}/{max_attempts}: {message[:180]}")
            print(f"[wait] sleeping {wait:.1f}s before retrying")
            time.sleep(wait)
            attempt += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate DART candidates rejected by the quality filter.")
    parser.add_argument("--jobs", required=True, type=Path)
    parser.add_argument("--raw-candidates", required=True, type=Path)
    parser.add_argument("--scored-candidates", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--rejection-reasons", default=",".join(sorted(DEFAULT_REJECTION_REASONS)))
    parser.add_argument(
        "--candidate-ids",
        default=None,
        help="Optional comma-separated candidate_id allowlist. When set, only these rejected candidates are retried.",
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=0.0)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-output-tokens", type=int, default=900)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-attempts", type=int, default=4)
    parser.add_argument("--retry-wait", type=float, default=8.0)
    args = parser.parse_args()

    load_env_file(args.env_file)
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set. Put it in your environment or pass --env-file .env.")

    reasons = {reason.strip() for reason in args.rejection_reasons.split(",") if reason.strip()}
    requested_candidate_ids = parse_candidate_ids(args.candidate_ids)
    scored_rows = read_records(args.scored_candidates)
    raw_rows = read_records(args.raw_candidates)
    jobs = {str(job.get("job_id")): job for job in read_records(args.jobs)}
    rejected_by_id = {str(row.get("candidate_id")): row for row in scored_rows}
    targets = sorted(target_candidate_ids(scored_rows, reasons))
    if requested_candidate_ids:
        targets = [candidate_id for candidate_id in targets if candidate_id in requested_candidate_ids]
    if args.limit is not None:
        targets = targets[: args.limit]

    client = OpenAIResponsesClient(
        api_key=api_key,
        model=args.model,
        timeout=args.timeout,
        max_output_tokens=args.max_output_tokens,
        temperature=args.temperature,
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
        replacement = generate_with_retries(
            retry_job,
            client,
            max_attempts=args.max_attempts,
            retry_wait=args.retry_wait,
        )
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
