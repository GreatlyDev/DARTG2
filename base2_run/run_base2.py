"""base2 regeneration sweep — self-contained runner.

Implements docs/base2_plan.md. Runs every dialect family in parallel against the
base2 prompt + claude-sonnet-4-6 (by default), writes a JSONL per family, then
scores each record with cheap similarity metrics + an HF cosine.

Usage (from this directory):
    python3 run_base2.py --all                # all 80 anchors per family
    python3 run_base2.py --sample 10          # first 10 anchors per family
    python3 run_base2.py --smoketest          # 5 random anchors per family

Outputs land in output/base2__<model>__<family>.jsonl.
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

from lib.generation import (
    extract_output_text,
    load_env_file,
    make_client,
    provider_for_model,
    utc_now,
)
from lib.io_utils import read_records, write_jsonl
from lib.pricing import cost_usd
from lib.similarity import cheap_scores, cosine_from_vectors
from lib.strategies import (
    FAMILY_TITLES,
    PROMPT_PATH,
    PROMPT_VERSION,
    build_input,
    load_inventory,
    parse_output,
)
from lib.dialect_scoring import (
    build_inventory_patterns,
    dialect_pass,
    feature_realization_grounding,
    scan_inventory_hits,
)


DEFAULT_MODEL = "claude-sonnet-4-6"
KNOWN_MODELS = (
    "claude-sonnet-4-6",   # default
    "claude-haiku-4-5",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-5.2",             # OpenAI responses API; supports --reasoning-effort
)
REASONING_EFFORT_CHOICES = ("minimal", "low", "medium", "high")
DEFAULT_ANCHORS = THIS_DIR / "data" / "DART_FINAL_80_ANCHORS.csv"
DEFAULT_OUTPUT_DIR = THIS_DIR / "output"
DEFAULT_HF_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--all", action="store_true", help="Run every anchor in the source CSV for each family.")
    scope.add_argument("--sample", type=int, metavar="N",
                       help="Run the first N anchors (in CSV order) for each family.")
    scope.add_argument("--smoketest", action="store_true",
                       help="Pick 5 random anchors (same set for every family) and run those.")

    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=(f"Model id (default: {DEFAULT_MODEL}). "
                              f"Curated: {', '.join(KNOWN_MODELS)}. "
                              "Any other string is also accepted and dispatched "
                              "by id prefix (claude-* → Anthropic, else OpenAI)."))
    parser.add_argument("--reasoning-effort", choices=REASONING_EFFORT_CHOICES, default=None,
                        help=("Reasoning effort for gpt-5 / o-series models on the "
                              "OpenAI responses API. Ignored for gpt-4o and "
                              "Anthropic models. Default: unset (provider default)."))
    parser.add_argument("--families", default=",".join(FAMILY_TITLES),
                        help="Comma-separated subset of families to run (default: all six).")
    parser.add_argument("--anchors", type=Path, default=DEFAULT_ANCHORS,
                        help="Path to anchor CSV/JSONL (default: data/DART_FINAL_80_ANCHORS.csv).")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="Where to write JSONL files.")
    parser.add_argument("--output-split", action="store_true",
                        help="Write one JSONL per family instead of a single combined file.")
    parser.add_argument("--output-file", type=Path, default=None,
                        help="Combined-output filename (default: output/base2__<model>__all.jsonl). "
                             "Ignored when --output-split is set.")
    parser.add_argument("--family-workers", type=int, default=6,
                        help="Number of families to run concurrently (default: 6 — one per family).")
    parser.add_argument("--anchor-workers", type=int, default=4,
                        help="Concurrent API calls within a single family (default: 4).")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP timeout per API call.")
    parser.add_argument("--max-output-tokens", type=int, default=1200, help="Max output tokens per response.")
    parser.add_argument("--max-attempts", type=int, default=2,
                        help="Per-record attempts before giving up on parse_error/model_fail/api_error "
                             "(default: 2). The HTTP client itself retries transient API errors "
                             "(429/529/5xx) up to 8 times with backoff before each attempt counts as a "
                             "failure.")
    parser.add_argument("--seed", type=int, default=7, help="RNG seed for --smoketest anchor selection.")
    parser.add_argument("--run-id", default=None,
                        help="Shared identifier for this sweep. Defaults to a fresh uuid4 hex.")
    parser.add_argument("--openai-key-file", type=Path, default=THIS_DIR.parent / ".openaiapi")
    parser.add_argument("--anthropic-key-file", type=Path, default=THIS_DIR.parent / ".anthropicapi")
    parser.add_argument("--env-file", type=Path, default=THIS_DIR.parent / ".env")
    parser.add_argument("--no-embed", action="store_true",
                        help="Skip the HF cosine embedding pass. Cheap-tier scores still run.")
    parser.add_argument("--hf-model", default=DEFAULT_HF_MODEL,
                        help=f"sentence-transformers model id (default: {DEFAULT_HF_MODEL}).")
    return parser.parse_args()


def _read_key_file(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def load_api_keys(args: argparse.Namespace) -> tuple[str, str]:
    load_env_file(args.env_file)
    openai_key = _read_key_file(args.openai_key_file) or os.environ.get("OPENAI_API_KEY", "").strip()
    anthropic_key = _read_key_file(args.anthropic_key_file) or os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return openai_key, anthropic_key


def safe_filename_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value)


def anchor_fields(row: dict) -> tuple[str, str, dict]:
    anchor_id = str(row.get("essay_id") or row.get("anchor_id") or "").strip()
    anchor_text = str(row.get("text") or row.get("anchor_response") or row.get("essay") or "").strip()
    extras = {
        k: row[k]
        for k in ("dataset", "score", "normalized_score", "score_band", "source_corpus", "prompt", "domain")
        if k in row and row[k] not in (None, "")
    }
    return anchor_id, anchor_text, extras


def select_anchors(anchors: list[dict], *, take_all: bool, sample_n: int | None, smoketest: bool,
                   seed: int) -> list[tuple[str, str, dict]]:
    cleaned: list[tuple[str, str, dict]] = []
    for row in anchors:
        anchor_id, anchor_text, extras = anchor_fields(row)
        if anchor_id and anchor_text:
            cleaned.append((anchor_id, anchor_text, extras))

    if take_all:
        return cleaned
    if sample_n is not None:
        return cleaned[: sample_n]
    if smoketest:
        rng = random.Random(seed)
        n = min(5, len(cleaned))
        return rng.sample(cleaned, n)
    return cleaned


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


def _is_refused(row: dict) -> bool:
    if row.get("similarity_scores", {}).get("exact_match"):
        return True
    if row.get("generation_status") in {"model_fail", "parse_error", "api_error"}:
        return True
    applied = row.get("applied_features")
    if isinstance(applied, list) and len(applied) == 0:
        return True
    return False


def _attempt_once(client, *, prompt_input: str) -> tuple[dict, str, object, str, str | None]:
    """One generation attempt. Returns (response, raw, parsed_or_None, status, parse_error)."""
    response: dict = {}
    raw = ""
    parsed = None
    status = "ok"
    parse_error: str | None = None
    try:
        response = client.create(prompt_input)
        raw = extract_output_text(response)
        parsed = parse_output(raw)
        status = parsed.generation_status
        parse_error = parsed.parse_error
    except RuntimeError as exc:
        status = "api_error"
        parse_error = str(exc)[:1000]
    return response, raw, parsed, status, parse_error


def generate_one(client, *, family: str, family_title: str, inventory: dict,
                 anchor_id: str, anchor_text: str, extras: dict, model: str,
                 provider: str, run_id: str, max_attempts: int = 2,
                 reasoning_effort: str | None = None) -> dict:
    """Generate one rewrite. The HTTP client already retries transient API
    errors (429/529/5xx). This wrapper retries the *whole* call if the result
    is a parse_error / model_fail / api_error, so an unlucky JSON or a
    fully-exhausted API retry still gets a fresh shot."""
    prompt_input = build_input(anchor_text, family_title, inventory)
    started = utc_now()
    response: dict = {}
    raw = ""
    parsed = None
    status = "ok"
    parse_error: str | None = None
    attempts_made = 0
    for attempt in range(1, max_attempts + 1):
        attempts_made = attempt
        response, raw, parsed, status, parse_error = _attempt_once(client, prompt_input=prompt_input)
        if status == "ok":
            break
        if attempt < max_attempts:
            sys.stderr.write(
                f"[retry] {family}/{anchor_id} status={status} on attempt {attempt}/{max_attempts} "
                f"— retrying. reason: {(parse_error or '')[:160]}\n"
            )
            sys.stderr.flush()
    finished = utc_now()

    usage = response.get("usage") if isinstance(response, dict) else None
    tokens_in, tokens_out = _token_counts(usage)
    declared = parsed.declared_feature_count if parsed else None
    applied_list = parsed.applied_features if parsed else None
    actual_feature_count = len(applied_list) if isinstance(applied_list, list) else 0

    return {
        "record_id": f"base2__{safe_filename_token(model)}__{family}__{anchor_id}",
        "run_id": run_id,
        "timestamp": utc_now(),
        "anchor_id": anchor_id,
        "anchor_text": anchor_text,
        "dialect_family": family,
        "dialect_title": family_title,
        "strategy": "base2",
        "prompt_version": PROMPT_VERSION,
        "prompt_path": PROMPT_PATH,
        "prompt_name": Path(PROMPT_PATH).stem,
        "model": model,
        "provider": provider,
        "reasoning_effort": reasoning_effort,
        "generation_status": status,
        "attempts": attempts_made,
        "rewrite_text": parsed.rewrite_text if parsed else "",
        "applied_features": applied_list,
        "applied_feature_count": actual_feature_count,
        "declared_feature_count": declared,
        "model_notes": parsed.model_notes if parsed else None,
        "raw_output": raw,
        "parse_error": parse_error,
        "openai_response_id": response.get("id") if isinstance(response, dict) else None,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd(model, tokens_in, tokens_out),
        "duration_seconds": _duration_seconds(started, finished),
        "usage": usage,
        "started_at": started,
        "finished_at": finished,
        "anchor_extras": extras,
    }


def run_family(*, family: str, anchors: list[tuple[str, str, dict]], model: str,
               openai_key: str, anthropic_key: str, timeout: int, max_output_tokens: int,
               anchor_workers: int, run_id: str, max_attempts: int = 2,
               reasoning_effort: str | None = None) -> tuple[str, list[dict]]:
    family_title = FAMILY_TITLES[family]
    inventory = load_inventory(family)
    provider = provider_for_model(model)

    effort_label = f" · effort={reasoning_effort}" if reasoning_effort else ""
    print(f"[{family}] starting · {len(anchors)} anchors · model={model} · provider={provider}{effort_label}", flush=True)

    client = make_client(
        model=model,
        openai_api_key=openai_key,
        anthropic_api_key=anthropic_key,
        timeout=timeout,
        max_output_tokens=max_output_tokens,
        reasoning_effort=reasoning_effort,
    )

    records: list[dict] = [None] * len(anchors)  # type: ignore[list-item]
    started = time.time()

    with ThreadPoolExecutor(max_workers=max(1, anchor_workers)) as pool:
        futures = {
            pool.submit(
                generate_one,
                client,
                family=family,
                family_title=family_title,
                inventory=inventory,
                anchor_id=aid,
                anchor_text=atext,
                extras=extras,
                model=model,
                provider=provider,
                run_id=run_id,
                max_attempts=max_attempts,
                reasoning_effort=reasoning_effort,
            ): idx
            for idx, (aid, atext, extras) in enumerate(anchors)
        }
        done = 0
        for fut in as_completed(futures):
            idx = futures[fut]
            records[idx] = fut.result()
            done += 1
            if done % 5 == 0 or done == len(anchors):
                print(f"[{family}] {done}/{len(anchors)} complete", flush=True)

    elapsed = time.time() - started
    ok = sum(1 for r in records if r["generation_status"] == "ok")
    print(f"[{family}] done · {ok}/{len(records)} ok · {elapsed:.1f}s", flush=True)
    return family, records


def _apply_dialect_scorers(records_by_family: dict[str, list[dict]]) -> None:
    """Realization grounding, inventory pattern hits, dual-criterion dialect_pass.
    Runs after cheap + cosine scoring so it can read the final cosine value."""
    # Build per-family pattern lists once.
    patterns_by_family: dict[str, list[dict]] = {}
    for family in records_by_family:
        try:
            patterns_by_family[family] = build_inventory_patterns(load_inventory(family))
        except KeyError:
            patterns_by_family[family] = []

    for family, rows in records_by_family.items():
        patterns = patterns_by_family.get(family, [])
        for row in rows:
            anchor = str(row.get("anchor_text", "") or "")
            rewrite = str(row.get("rewrite_text", "") or "")

            grounding = feature_realization_grounding(row.get("applied_features"), rewrite)
            row["feature_realization"] = grounding

            hits = scan_inventory_hits(anchor, rewrite, patterns)
            row["inventory_pattern_hits"] = hits

            cos = row.get("cosine_similarity")
            feat_count = row.get("applied_feature_count")
            new_hits = hits.get("count_new")
            row["dialect_pass"] = dialect_pass(
                cos,
                feature_count=feat_count,
                new_inv_hits=new_hits,
            )


def score_records(records_by_family: dict[str, list[dict]], *, use_hf: bool, hf_model: str) -> None:
    """Add cheap-tier similarity scores + (optional) HF cosine + dialect scorers in-place."""
    # Cheap-tier scores per record.
    for rows in records_by_family.values():
        for row in rows:
            anchor = str(row.get("anchor_text", "") or "")
            rewrite = str(row.get("rewrite_text", "") or "")
            scores = cheap_scores(anchor, rewrite)
            existing = row.get("similarity_scores") or {}
            existing.update(scores)
            row["similarity_scores"] = existing
            row["anchor_word_count"] = len(anchor.split())
            row["rewrite_word_count"] = len(rewrite.split())
            row["composite_change_score"] = round(1 - scores["difflib_ratio"], 4)

    def _finalize_no_cosine() -> None:
        # -1 is the sentinel for "cosine not computed".
        for rows in records_by_family.values():
            for row in rows:
                row["cosine_similarity"] = -1
                row["refused"] = _is_refused(row)

    if not use_hf:
        _finalize_no_cosine()
        _apply_dialect_scorers(records_by_family)
        return

    # HF cosine — batch all eligible (non-empty) pairs through a single model load.
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("[score] sentence-transformers not installed — skipping HF cosine. "
              "Run `pip install sentence-transformers` or pass --no-embed.", flush=True)
        _finalize_no_cosine()
        _apply_dialect_scorers(records_by_family)
        return

    print(f"[score] loading HF model {hf_model}…", flush=True)
    model = SentenceTransformer(hf_model)

    flat_texts: list[str] = []
    index_map: list[tuple[str, int]] = []  # (family, row_index)
    for family, rows in records_by_family.items():
        for idx, row in enumerate(rows):
            a = str(row.get("anchor_text", "") or "")
            r = str(row.get("rewrite_text", "") or "")
            if not a.strip() or not r.strip():
                continue
            flat_texts.append(a)
            flat_texts.append(r)
            index_map.append((family, idx))

    # Default every row to the sentinel; eligible rows below overwrite with the real value.
    for rows in records_by_family.values():
        for row in rows:
            row["cosine_similarity"] = -1

    if flat_texts:
        print(f"[score] encoding {len(flat_texts)} texts on HF…", flush=True)
        vectors = model.encode(flat_texts, convert_to_numpy=False, show_progress_bar=False)
        key = f"hf/{hf_model.split('/')[-1]}"
        for k, (family, idx) in enumerate(index_map):
            a_vec = list(vectors[2 * k])
            r_vec = list(vectors[2 * k + 1])
            cos = cosine_from_vectors(a_vec, r_vec)
            row = records_by_family[family][idx]
            bucket = row["similarity_scores"].setdefault("cosine_embeddings", {})
            bucket[key] = cos
            row["cosine_similarity"] = cos  # top-level convenience field

    for rows in records_by_family.values():
        for row in rows:
            row["refused"] = _is_refused(row)

    _apply_dialect_scorers(records_by_family)


def aggregate_stats(records_by_family: dict[str, list[dict]]) -> dict:
    """Summary numbers for the console at the end of the run."""
    stats: dict[str, dict] = {}
    for family, rows in records_by_family.items():
        n = len(rows)
        ok = [r for r in rows if r.get("generation_status") == "ok"]
        feature_counts = [r.get("applied_feature_count") or 0 for r in ok]
        token_change = [r.get("similarity_scores", {}).get("token_change_ratio") for r in ok
                        if r.get("similarity_scores")]
        # -1 means "cosine not computed" — exclude it from the median.
        cosines = [r.get("cosine_similarity") for r in ok
                   if r.get("cosine_similarity") is not None and r.get("cosine_similarity") != -1]
        # Dialect-pass / grounding / inventory-hit aggregates over ok rows.
        passes = [r.get("dialect_pass") for r in ok if r.get("dialect_pass") is not None]
        pass_rate = (round(sum(1 for p in passes if p) / len(passes), 4)
                     if passes else None)
        grounding_rates = [r.get("feature_realization", {}).get("rate") for r in ok
                           if r.get("feature_realization", {}).get("rate") is not None]
        new_hit_counts = [r.get("inventory_pattern_hits", {}).get("count_new") or 0 for r in ok]
        tokens_in_total = sum(int(r.get("tokens_in") or 0) for r in rows)
        tokens_out_total = sum(int(r.get("tokens_out") or 0) for r in rows)
        cost_total = sum(float(r.get("cost_usd") or 0) for r in rows)
        stats[family] = {
            "records": n,
            "ok": len(ok),
            "median_feature_count": _median(feature_counts),
            "median_token_change_pct": (round(100 * _median(token_change), 2)
                                        if token_change else None),
            "median_cosine": (round(_median(cosines), 4) if cosines else -1),
            "dialect_pass_rate": pass_rate if pass_rate is not None else -1,
            "median_grounding_rate": (round(_median(grounding_rates), 4)
                                       if grounding_rates else -1),
            "median_new_inventory_hits": _median(new_hit_counts),
            "tokens_in_total": tokens_in_total,
            "tokens_out_total": tokens_out_total,
            "cost_usd_total": round(cost_total, 4),
        }
    return stats


def _median(values: list) -> float:
    nums = sorted(float(v) for v in values if v is not None)
    if not nums:
        return 0.0
    mid = len(nums) // 2
    if len(nums) % 2 == 1:
        return nums[mid]
    return (nums[mid - 1] + nums[mid]) / 2


def main() -> None:
    args = parse_args()
    requested_families = [f.strip() for f in args.families.split(",") if f.strip()]
    for f in requested_families:
        if f not in FAMILY_TITLES:
            raise SystemExit(f"Unknown family {f!r}. Valid: {sorted(FAMILY_TITLES)}.")

    openai_key, anthropic_key = load_api_keys(args)
    run_id = args.run_id or uuid.uuid4().hex
    args.output_dir.mkdir(parents=True, exist_ok=True)

    anchors = read_records(args.anchors)
    selected = select_anchors(anchors, take_all=args.all, sample_n=args.sample,
                              smoketest=args.smoketest, seed=args.seed)
    if not selected:
        raise SystemExit("No anchors selected — check --anchors path or selection flags.")

    scope = ("all" if args.all else
             f"sample={args.sample}" if args.sample is not None else
             f"smoketest({len(selected)} random anchors, seed={args.seed})")
    print(f"=== base2 sweep · run_id={run_id} · model={args.model} · scope={scope} ===")
    print(f"Families: {requested_families}")
    print(f"Anchors per family: {len(selected)}")
    print(f"Family workers: {args.family_workers} · Anchor workers (per family): {args.anchor_workers}")

    records_by_family: dict[str, list[dict]] = {}
    sweep_started = time.time()

    with ThreadPoolExecutor(max_workers=max(1, args.family_workers)) as pool:
        futures = {
            pool.submit(
                run_family,
                family=family,
                anchors=selected,
                model=args.model,
                openai_key=openai_key,
                anthropic_key=anthropic_key,
                timeout=args.timeout,
                max_output_tokens=args.max_output_tokens,
                anchor_workers=args.anchor_workers,
                run_id=run_id,
                max_attempts=args.max_attempts,
                reasoning_effort=args.reasoning_effort,
            ): family
            for family in requested_families
        }
        for fut in as_completed(futures):
            family, records = fut.result()
            records_by_family[family] = records

    print(f"Generation finished in {time.time() - sweep_started:.1f}s. Scoring…")
    score_records(records_by_family, use_hf=not args.no_embed, hf_model=args.hf_model)

    # Write outputs: split-per-family OR a single combined JSONL.
    output_paths: dict[str, Path] = {}
    if args.output_split:
        for family in requested_families:
            if family not in records_by_family:
                continue
            path = args.output_dir / f"base2__{safe_filename_token(args.model)}__{family}.jsonl"
            write_jsonl(path, records_by_family[family])
            output_paths[family] = path
    else:
        combined_path = args.output_file or (
            args.output_dir / f"base2__{safe_filename_token(args.model)}__all.jsonl"
        )
        combined: list[dict] = []
        for family in requested_families:
            combined.extend(records_by_family.get(family, []))
        write_jsonl(combined_path, combined)
        output_paths["__combined__"] = combined_path

    stats = aggregate_stats(records_by_family)

    print("\n=== Summary ===")
    header = (f"{'family':14}{'n':>4}{'ok':>4}{'feat':>6}{'tok_chg%':>10}{'cos':>8}"
              f"{'pass':>7}{'ground':>8}{'inv_new':>9}{'tok_in':>10}{'tok_out':>10}{'cost$':>9}")
    print(header)
    print("-" * len(header))
    total_in = total_out = 0
    total_cost = 0.0
    for family, s in stats.items():
        print(f"{family:14}{s['records']:>4}{s['ok']:>4}{s['median_feature_count']:>6.1f}"
              f"{(s['median_token_change_pct'] if s['median_token_change_pct'] is not None else 0):>10.2f}"
              f"{s['median_cosine']:>8.4f}"
              f"{s['dialect_pass_rate']:>7.2f}"
              f"{s['median_grounding_rate']:>8.2f}"
              f"{s['median_new_inventory_hits']:>9.1f}"
              f"{s['tokens_in_total']:>10}{s['tokens_out_total']:>10}{s['cost_usd_total']:>9.4f}")
        total_in += s["tokens_in_total"]
        total_out += s["tokens_out_total"]
        total_cost += s["cost_usd_total"]
    print("-" * len(header))
    print(f"{'TOTAL':14}{sum(s['records'] for s in stats.values()):>4}"
          f"{sum(s['ok'] for s in stats.values()):>4}"
          f"{'':>6}{'':>10}{'':>8}{'':>7}{'':>8}{'':>9}"
          f"{total_in:>10}{total_out:>10}{total_cost:>9.4f}")

    print("\nOutputs:")
    if args.output_split:
        for family in requested_families:
            if family in output_paths:
                print(f"  {family:14} → {output_paths[family]}")
    else:
        path = output_paths["__combined__"]
        total = sum(len(r) for r in records_by_family.values())
        print(f"  combined ({total} records) → {path}")


if __name__ == "__main__":
    main()
