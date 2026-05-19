"""Unified dialect-rewrite runner — one CLI, three strategies, any OpenAI model.

Strategies:
    naive    : "Rewrite this in <dialect>" one-liner (prompts/naive.md).
    base     : prompts/base.md with the family's inventory injected.
    dialect  : prompts/dialects/<family>.md license-by-anchor greedy rewrite (JSON output).

All three write the same unified JSONL schema. rewrite_text is always populated
on status=ok records. applied_features / rejected_candidates / model_notes are
only populated by the inventory_greedy strategy.

Usage:
    python scripts/run_dialect_rewrite.py --strategy naive --family aae
    python scripts/run_dialect_rewrite.py --strategy inventory_greedy --family southern --model gpt-4o
    python scripts/run_dialect_rewrite.py --strategy inventory_injected --family aae --limit 5 --print-output
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.generation import (
    extract_output_text,
    load_env_file,
    make_client,
    provider_for_model,
    sleep_between_calls,
    utc_now,
)
from dart_pipeline.io_utils import read_records, write_jsonl
from dart_pipeline.pricing import cost_usd
from dart_pipeline.strategies import FAMILY_TITLES, STRATEGIES, load_inventory, prompt_path_for


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--strategy", required=True, choices=sorted(STRATEGIES), help="Which prompt strategy to run.")
    parser.add_argument("--family", required=True, choices=sorted(FAMILY_TITLES), help="Dialect family.")
    parser.add_argument("--model", default="gpt-4o", help="OpenAI model to use (default: gpt-4o).")
    parser.add_argument("--anchors", type=Path, default=Path("data/raw/DART_FINAL_80_ANCHORS.csv"),
                        help="Path to anchor CSV or JSONL.")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output JSONL. Defaults to data/generated/<strategy>__<model>__<family>.jsonl.")
    parser.add_argument("--key-file", type=Path, default=Path(".openaiapi"),
                        help="Path to a file containing the raw OpenAI API key on a single line.")
    parser.add_argument("--anthropic-key-file", type=Path, default=Path(".anthropicapi"),
                        help="Path to a file containing the raw Anthropic API key on a single line.")
    parser.add_argument("--env-file", type=Path, default=Path(".env"),
                        help="Optional .env to load OPENAI_API_KEY / ANTHROPIC_API_KEY from if the raw key files are missing.")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N anchors after filtering.")
    parser.add_argument("--anchor-id", default=None,
                        help="Restrict to exactly this anchor_id (matched against essay_id / anchor_id in the source).")
    parser.add_argument("--resume", action="store_true",
                        help="Skip anchors already present (by anchor_id) in the output file.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Seconds to sleep between API calls.")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP timeout per API call.")
    parser.add_argument("--max-output-tokens", type=int, default=900, help="Max output tokens per response.")
    parser.add_argument("--print-output", action="store_true",
                        help="Print each rewrite + applied_features (when present) to the terminal.")
    parser.add_argument("--run-id", default=None,
                        help="Shared identifier for this run. Defaults to a fresh uuid4 hex per invocation. "
                             "When run by scripts/run.py, all cells of one matrix session receive the same value.")
    return parser.parse_args()


def _read_key_file(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def load_api_keys(openai_key_file: Path, anthropic_key_file: Path, env_file: Path) -> tuple[str, str]:
    """Return (openai_key, anthropic_key). Either may be empty — make_client() will error
    only if a model actually requests the missing provider."""
    load_env_file(env_file)
    openai_key = _read_key_file(openai_key_file) or os.environ.get("OPENAI_API_KEY", "").strip()
    anthropic_key = _read_key_file(anthropic_key_file) or os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return openai_key, anthropic_key


def anchor_fields(row: dict) -> tuple[str, str, dict]:
    anchor_id = str(row.get("essay_id") or row.get("anchor_id") or "").strip()
    anchor_text = str(row.get("text") or row.get("anchor_response") or row.get("essay") or "").strip()
    extras = {
        k: row[k]
        for k in ("dataset", "score", "normalized_score", "score_band", "source_corpus", "prompt", "domain")
        if k in row and row[k] not in (None, "")
    }
    return anchor_id, anchor_text, extras


def safe_filename_token(value: str) -> str:
    """Sanitize a model name for use in a filename (gpt-4o, gpt-5.2, etc. stay readable)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def _duration_seconds(started_iso: str, finished_iso: str) -> float | None:
    try:
        a = datetime.fromisoformat(started_iso)
        b = datetime.fromisoformat(finished_iso)
        return round((b - a).total_seconds(), 3)
    except (ValueError, TypeError):
        return None


def _token_counts(usage: dict | None) -> tuple[int | None, int | None]:
    if not isinstance(usage, dict):
        return None, None
    tin = usage.get("input_tokens") or usage.get("prompt_tokens")
    tout = usage.get("output_tokens") or usage.get("completion_tokens")
    try:
        return (int(tin) if tin is not None else None,
                int(tout) if tout is not None else None)
    except (TypeError, ValueError):
        return None, None


def default_output_path(strategy: str, model: str, family: str) -> Path:
    return Path("data/generated") / f"{strategy}__{safe_filename_token(model)}__{family}.jsonl"


def main() -> None:
    args = parse_args()
    strategy = STRATEGIES[args.strategy]
    family_title = FAMILY_TITLES[args.family]
    inventory = load_inventory(args.family)
    openai_key, anthropic_key = load_api_keys(args.key_file, args.anthropic_key_file, args.env_file)
    output_path = args.output or default_output_path(args.strategy, args.model, args.family)
    provider = provider_for_model(args.model)
    run_id = args.run_id or uuid.uuid4().hex
    print(f"Model {args.model} routed to provider: {provider} · run_id={run_id}")

    anchors = read_records(args.anchors)
    existing_rows = read_records(output_path) if output_path.exists() and args.resume else []
    seen_ids = {str(row.get("anchor_id")) for row in existing_rows if row.get("anchor_id")}

    todo: list[tuple[str, str, dict]] = []
    for row in anchors:
        anchor_id, anchor_text, extras = anchor_fields(row)
        if not anchor_id or not anchor_text:
            continue
        if args.anchor_id is not None and anchor_id != args.anchor_id:
            continue
        if anchor_id in seen_ids:
            continue
        todo.append((anchor_id, anchor_text, extras))
    if args.anchor_id is not None and not todo and args.anchor_id not in seen_ids:
        raise SystemExit(f"No anchor with id {args.anchor_id!r} found in {args.anchors}.")
    if args.limit is not None:
        todo = todo[: args.limit]

    client = make_client(
        model=args.model,
        openai_api_key=openai_key,
        anthropic_api_key=anthropic_key,
        timeout=args.timeout,
        max_output_tokens=args.max_output_tokens,
    )

    output_rows: list[dict] = list(existing_rows)
    total = len(todo)

    for index, (anchor_id, anchor_text, extras) in enumerate(todo, start=1):
        print(f"[{index}/{total}] {args.strategy}/{args.family}@{args.model} :: {anchor_id}")
        prompt_input = strategy.build_input(anchor_text, args.family, family_title, inventory)
        started = utc_now()
        response: dict = {}
        raw = ""
        parsed = None
        status = "ok"
        parse_error: str | None = None
        try:
            response = client.create(prompt_input)
            raw = extract_output_text(response)
            parsed = strategy.parse_output(raw)
            status = parsed.generation_status
            parse_error = parsed.parse_error
        except RuntimeError as exc:
            status = "api_error"
            parse_error = str(exc)[:1000]
        finished = utc_now()

        usage = response.get("usage") if isinstance(response, dict) else None
        tokens_in, tokens_out = _token_counts(usage)
        duration = _duration_seconds(started, finished)

        record = {
            "record_id": f"{args.strategy}__{safe_filename_token(args.model)}__{args.family}__{anchor_id}",
            "run_id": run_id,
            "timestamp": utc_now(),
            "anchor_id": anchor_id,
            "anchor_text": anchor_text,
            "dialect_family": args.family,
            "dialect_title": family_title,
            "strategy": args.strategy,
            "prompt_version": strategy.prompt_version,
            "prompt_path": prompt_path_for(args.strategy, args.family),
            "prompt_name": Path(prompt_path_for(args.strategy, args.family)).stem,
            "model": args.model,
            "provider": provider,
            "generation_status": status,
            "rewrite_text": parsed.rewrite_text if parsed else "",
            "applied_features": parsed.applied_features if parsed else None,
            "rejected_candidates": parsed.rejected_candidates if parsed else None,
            "model_notes": parsed.model_notes if parsed else None,
            "raw_output": raw,
            "parse_error": parse_error,
            "openai_response_id": response.get("id") if isinstance(response, dict) else None,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_usd": cost_usd(args.model, tokens_in, tokens_out),
            "duration_seconds": duration,
            "usage": usage,
            "started_at": started,
            "finished_at": finished,
            "anchor_extras": extras,
        }
        output_rows.append(record)
        write_jsonl(output_path, output_rows)

        if args.print_output:
            print(f"  status : {status}")
            if parsed and parsed.rewrite_text:
                preview = parsed.rewrite_text if len(parsed.rewrite_text) < 220 else parsed.rewrite_text[:220] + "…"
                print(f"  rewrite: {preview}")
            if parsed and parsed.applied_features:
                ids = [f.get("id") for f in parsed.applied_features if isinstance(f, dict)]
                print(f"  applied: {ids}")
            if parse_error:
                print(f"  error  : {parse_error[:200]}")
            print("-" * 80)

        sleep_between_calls(args.sleep)

    print(f"Wrote {len(output_rows)} records to {output_path}")


if __name__ == "__main__":
    main()
