"""Interactively step through a dialect-rewrite JSONL one record at a time.

Press Enter to advance. Supports backward navigation, jump-to, and quit.

Usage:
    python scripts/browse.py data/generated/naive__gpt-4o__aae.jsonl
    python scripts/browse.py data/generated/inventory_greedy__claude-sonnet-4-6__southern.jsonl
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import textwrap
from pathlib import Path


def term_width(default: int = 100) -> int:
    try:
        cols = shutil.get_terminal_size().columns
        return min(max(cols, 60), 140)
    except OSError:
        return default


def wrap(text: str, width: int) -> str:
    if not text:
        return "(empty)"
    return "\n".join(
        textwrap.fill(line, width=width, replace_whitespace=False, drop_whitespace=False)
        if line.strip() else line
        for line in text.splitlines()
    )


def render(row: dict, idx: int, total: int, width: int) -> str:
    out: list[str] = []
    bar = "═" * width
    out.append(bar)
    out.append(f" {idx + 1}/{total}   record_id: {row.get('record_id', '?')}")
    out.append(bar)

    # Metadata header.
    meta_pairs = [
        ("anchor_id", row.get("anchor_id", "?")),
        ("strategy",  row.get("strategy", "?")),
        ("model",     row.get("model", "?")),
        ("family",    row.get("dialect_family", "?")),
        ("prompt",    row.get("prompt_path") or row.get("prompt_name") or "?"),
        ("status",    row.get("generation_status", "?")),
    ]
    for label, val in meta_pairs:
        out.append(f"  {label:<10}: {val}")

    # Anchor extras (dataset, score, score_band) — useful for context.
    extras = row.get("anchor_extras") or {}
    if extras:
        bits = [f"{k}={v}" for k, v in extras.items() if v not in (None, "")]
        if bits:
            out.append(f"  {'extras':<10}: {' · '.join(bits)}")

    # API stats.
    tin = row.get("tokens_in")
    tout = row.get("tokens_out")
    cost = row.get("cost_usd")
    dur = row.get("duration_seconds")
    stat_bits = []
    if tin is not None and tout is not None:
        stat_bits.append(f"tokens={tin}→{tout}")
    if cost is not None:
        stat_bits.append(f"${cost:.4f}")
    if dur is not None:
        stat_bits.append(f"{dur:.1f}s")
    if stat_bits:
        out.append(f"  {'api':<10}: {' · '.join(stat_bits)}")

    # Similarity (if scored).
    sim = row.get("similarity_scores") or {}
    refused = row.get("refused")
    composite = row.get("composite_change_score")
    sim_bits = []
    if refused is not None:
        sim_bits.append(f"refused={refused}")
    if composite is not None:
        sim_bits.append(f"change={composite}")
    if "levenshtein_normalized" in sim:
        sim_bits.append(f"lev={sim['levenshtein_normalized']:.3f}")
    if "token_jaccard" in sim:
        sim_bits.append(f"jaccard={sim['token_jaccard']:.3f}")
    cos = (sim.get("cosine_embeddings") or {})
    if "hf/all-MiniLM-L6-v2" in cos:
        sim_bits.append(f"hf_cos={cos['hf/all-MiniLM-L6-v2']:.3f}")
    if "openai/text-embedding-3-small" in cos:
        sim_bits.append(f"oai_cos={cos['openai/text-embedding-3-small']:.3f}")
    if sim_bits:
        out.append(f"  {'similarity':<10}: {' · '.join(sim_bits)}")

    # Anchor text.
    out.append("")
    out.append("─" * width)
    out.append("ANCHOR")
    out.append("─" * width)
    out.append(wrap(row.get("anchor_text", ""), width))

    # Rewrite text.
    out.append("")
    out.append("─" * width)
    out.append("REWRITE")
    out.append("─" * width)
    out.append(wrap(row.get("rewrite_text", ""), width))

    # Applied features (greedy only).
    applied = row.get("applied_features")
    if applied:
        out.append("")
        out.append("APPLIED FEATURES:")
        for f in applied:
            if isinstance(f, dict):
                fid = f.get("id", "?")
                before = f.get("span_before", "")
                after = f.get("span_after", "")
                out.append(f"  • {fid:<28}  '{before}' → '{after}'")
            else:
                out.append(f"  • {f}")

    notes = row.get("model_notes")
    if notes:
        out.append("")
        out.append(f"NOTES: {notes}")

    parse_err = row.get("parse_error")
    if parse_err:
        out.append("")
        out.append(f"PARSE_ERROR: {parse_err[:200]}")

    return "\n".join(out)


def prompt_help() -> str:
    return (
        "\n[Enter] next  ·  p: previous  ·  j N: jump to record N  ·  "
        "n N: skip forward N  ·  q: quit  ·  ?: help\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="Path to a JSONL file produced by run_dialect_rewrite.py.")
    parser.add_argument("--start", type=int, default=1, help="1-based record index to start at (default: 1).")
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"File not found: {args.input}")

    rows = [json.loads(line) for line in args.input.read_text().splitlines() if line.strip()]
    if not rows:
        raise SystemExit(f"No records in {args.input}")

    total = len(rows)
    idx = max(0, min(args.start - 1, total - 1))
    width = term_width()

    print(f"\nOpened {args.input.name} ({total} records). Type ? for help.\n")

    while True:
        print(render(rows[idx], idx, total, width))
        try:
            cmd = input(prompt_help()).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if cmd in {"q", "quit", "exit"}:
            return
        if cmd in {"", "n", "next"}:
            if idx + 1 < total:
                idx += 1
            else:
                print("\n(at last record — q to quit)")
            continue
        if cmd in {"p", "prev", "previous"}:
            idx = max(0, idx - 1)
            continue
        if cmd == "?":
            print(prompt_help())
            continue
        # j N — jump
        if cmd.startswith("j "):
            try:
                target = int(cmd.split()[1]) - 1
                idx = max(0, min(target, total - 1))
            except (ValueError, IndexError):
                print("usage: j <number>")
            continue
        # n N — skip forward N
        if cmd.startswith("n "):
            try:
                step = int(cmd.split()[1])
                idx = max(0, min(idx + step, total - 1))
            except (ValueError, IndexError):
                print("usage: n <number>")
            continue

        print(f"unknown command {cmd!r}. ? for help.")


if __name__ == "__main__":
    main()
