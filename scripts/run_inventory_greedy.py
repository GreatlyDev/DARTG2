"""Run inventory-driven greedy dialect rewriting for a chosen dialect family.

Loads prompts/dialects/<family>.md as the system prompt, the matching config/features/<family>.json
as the inventory, and walks an anchor CSV/JSONL, calling the OpenAI Responses API once per
anchor. Writes one JSONL record per anchor with the parsed JSON output the prompt asks for.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.generation import (
    OpenAIResponsesClient,
    extract_output_text,
    load_env_file,
    sleep_between_calls,
    utc_now,
)
from dart_pipeline.io_utils import read_records, write_jsonl


REPO_ROOT = Path(__file__).resolve().parents[1]

FAMILY_MAP: dict[str, tuple[str, str]] = {
    "aae":          ("dialects/aae.md",          "aae.json"),
    "southern":     ("dialects/southern.md",     "southern.json"),
    "appalachian":  ("dialects/appalachian.md",  "appalachian.json"),
    "midwestern":   ("dialects/midwestern.md",   "midwestern_north_central.json"),
    "northeastern": ("dialects/northeastern.md", "northeastern_new_england.json"),
    "western":      ("dialects/western.md",     "western.json"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", required=True, choices=sorted(FAMILY_MAP), help="Dialect family to run.")
    parser.add_argument("--anchors", type=Path, default=Path("data/raw/DART_FINAL_80_ANCHORS.csv"),
                        help="Path to the anchor CSV or JSONL (must contain essay_id/anchor_id and text/anchor_response).")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output JSONL. Defaults to data/generated/inventory_greedy_<family>.jsonl.")
    parser.add_argument("--model", default="gpt-4o", help="OpenAI model to use (default: gpt-4o).")
    parser.add_argument("--key-file", type=Path, default=Path(".openaiapi"),
                        help="Path to a file containing the raw OpenAI API key on a single line.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"),
                        help="Optional .env to load OPENAI_API_KEY from if --key-file is missing.")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N anchors after filtering.")
    parser.add_argument("--resume", action="store_true",
                        help="Skip anchors already present (by anchor_id) in the output file.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between API calls.")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP timeout per API call in seconds.")
    parser.add_argument("--max-output-tokens", type=int, default=900, help="Maximum output tokens per response.")
    parser.add_argument("--print-output", action="store_true",
                        help="Print each parsed rewrite + applied_features to the terminal as it streams.")
    return parser.parse_args()


def load_api_key(key_file: Path, env_file: Path) -> str:
    if key_file.exists():
        key = key_file.read_text(encoding="utf-8").strip()
        if key:
            return key
    load_env_file(env_file)
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            f"No API key found. Tried --key-file {key_file} (missing or empty) "
            f"and OPENAI_API_KEY via --env-file {env_file}."
        )
    return key


def anchor_fields(row: dict) -> tuple[str, str, dict]:
    """Extract (anchor_id, anchor_text, extras) from a row, supporting both final-80 and legacy schemas."""
    anchor_id = str(row.get("essay_id") or row.get("anchor_id") or "").strip()
    anchor_text = str(row.get("text") or row.get("anchor_response") or row.get("essay") or "").strip()
    extras = {
        k: row[k]
        for k in ("dataset", "score", "normalized_score", "score_band", "source_corpus", "prompt", "domain")
        if k in row and row[k] not in (None, "")
    }
    return anchor_id, anchor_text, extras


def build_input(system_prompt: str, anchor_text: str, inventory: dict) -> str:
    """Concatenate system prompt + user input into a single Responses-API input string.

    The existing OpenAIResponsesClient passes a single string as `input`. We mark the boundary
    so the model can clearly separate instructions from the per-anchor inputs.
    """
    user_block = f"ANCHOR: {anchor_text}\n\nINVENTORY: {json.dumps(inventory, ensure_ascii=False)}"
    return f"{system_prompt}\n\n---\n\n{user_block}"


def parse_model_json(raw: str) -> tuple[dict | None, str | None]:
    """Try to parse the model's text as the JSON object the prompt requires.

    Handles bare JSON and JSON wrapped in ```json fences. Returns (parsed, error_or_none).
    """
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                return json.loads(match.group(0)), None
            except json.JSONDecodeError as exc2:
                return None, f"json_decode_error after substring extraction: {exc2}"
        return None, f"json_decode_error: {exc}"


def main() -> None:
    args = parse_args()
    prompt_filename, inventory_filename = FAMILY_MAP[args.family]
    system_prompt = (REPO_ROOT / "prompts" / prompt_filename).read_text(encoding="utf-8")
    inventory = json.loads((REPO_ROOT / "config" / "features" / inventory_filename).read_text(encoding="utf-8"))

    output_path = args.output or Path(f"data/generated/inventory_greedy_{args.family}.jsonl")
    api_key = load_api_key(args.key_file, args.env_file)

    anchors = read_records(args.anchors)
    existing_rows = read_records(output_path) if output_path.exists() and args.resume else []
    seen_ids = {str(row.get("anchor_id")) for row in existing_rows if row.get("anchor_id")}

    todo: list[tuple[str, str, dict]] = []
    for row in anchors:
        anchor_id, anchor_text, extras = anchor_fields(row)
        if not anchor_id or not anchor_text:
            continue
        if anchor_id in seen_ids:
            continue
        todo.append((anchor_id, anchor_text, extras))
    if args.limit is not None:
        todo = todo[: args.limit]

    client = OpenAIResponsesClient(
        api_key=api_key,
        model=args.model,
        timeout=args.timeout,
        max_output_tokens=args.max_output_tokens,
    )

    output_rows: list[dict] = list(existing_rows)
    total = len(todo)
    output_key = f"{args.family}_output"

    for index, (anchor_id, anchor_text, extras) in enumerate(todo, start=1):
        print(f"[{index}/{total}] {args.family} :: {anchor_id}")
        prompt_input = build_input(system_prompt, anchor_text, inventory)
        started = utc_now()
        response: dict = {}
        raw = ""
        parsed: dict | None = None
        parse_err: str | None = None
        status = "ok"
        try:
            response = client.create(prompt_input)
            raw = extract_output_text(response)
            if raw.strip() == "FAIL":
                status = "model_fail"
            else:
                parsed, parse_err = parse_model_json(raw)
                if parsed is None:
                    status = "parse_error"
        except RuntimeError as exc:
            status = "api_error"
            parse_err = str(exc)[:1000]
        finished = utc_now()

        record = {
            "anchor_id": anchor_id,
            "anchor_text": anchor_text,
            "dialect_family": args.family,
            "prompt_version": f"{args.family}_inventory_greedy_v1",
            "model": args.model,
            "generation_status": status,
            "parsed_output": parsed,
            "raw_output": raw,
            "parse_error": parse_err,
            "openai_response_id": response.get("id") if isinstance(response, dict) else None,
            "usage": response.get("usage") if isinstance(response, dict) else None,
            "started_at": started,
            "finished_at": finished,
            "anchor_extras": extras,
        }
        output_rows.append(record)
        write_jsonl(output_path, output_rows)

        if args.print_output:
            if parsed:
                rewrite = parsed.get(output_key, "(missing key)")
                applied = [f.get("id") for f in parsed.get("applied_features", []) if isinstance(f, dict)]
                print(f"  output : {rewrite}")
                print(f"  applied: {applied}")
            else:
                print(f"  status : {status}")
                if parse_err:
                    print(f"  error  : {parse_err[:200]}")
            print("-" * 80)

        sleep_between_calls(args.sleep)

    print(f"Wrote {len(output_rows)} records to {output_path}")


if __name__ == "__main__":
    main()
