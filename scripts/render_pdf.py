"""Render PDFs from the unified-schema JSONL outputs in data/generated/.

Discovers data/generated/<strategy>__<model>__<family>.jsonl files and renders
readable PDFs of every record (anchor, rewrite, applied features, similarity scores).

Default grouping: one PDF per (strategy, model) — 9 PDFs for the standard 3×3 matrix —
with each family on its own page-break inside the PDF.

Other modes:
  --per-cell    : one PDF per JSONL file (54 PDFs for the full matrix)
  --combined    : a single PDF containing every record across the whole matrix

PDFs land in docs/examples/. The intermediate .html is removed unless --keep-html.

Usage:
    python scripts/render_pdf.py                              # default: 9 PDFs
    python scripts/render_pdf.py --strategies dialect         # only dialect runs
    python scripts/render_pdf.py --models gpt-4o              # only gpt-4o cells
    python scripts/render_pdf.py --per-cell                   # 54 small PDFs
    python scripts/render_pdf.py --combined                   # one giant PDF
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

FAMILY_TITLES = {
    "aae":          "African American English (AAE)",
    "southern":     "Southern American English",
    "appalachian":  "Appalachian English",
    "midwestern":   "Midwestern / North Central",
    "northeastern": "Northeastern / New England",
    "western":      "Western American English",
}

CSS = """
@page { size: Letter; margin: 0.75in; }
body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1a1a1a; }
h1 { font-size: 20pt; margin: 0 0 4pt 0; }
h2 { font-size: 14pt; margin: 16pt 0 4pt 0; padding-bottom: 4pt; border-bottom: 2px solid #2a6dba; color: #2a6dba; }
h2.family-break { page-break-before: always; padding-top: 4pt; }
.subtitle { color: #555; font-size: 10pt; margin-bottom: 12pt; }
.anchor-block { page-break-inside: avoid; margin-bottom: 14pt; padding: 8pt 10pt; border: 1px solid #e0e0e0; border-radius: 4px; background: #fafafa; }
.anchor-block.refused { border-color: #c08a30; background: #fffaf0; }
.anchor-block.parse-error { border-color: #c04040; background: #fff5f5; }
.meta { font-size: 9pt; color: #666; margin-bottom: 6pt; }
.label { font-weight: 600; color: #444; font-size: 9pt; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 8pt; }
.anchor-text { background: #fff; padding: 6pt 8pt; border-left: 3px solid #888; white-space: pre-wrap; font-family: "Times New Roman", Georgia, serif; font-size: 10.5pt; }
.rewrite-text { background: #f0f7ff; padding: 6pt 8pt; border-left: 3px solid #2a6dba; white-space: pre-wrap; font-family: "Times New Roman", Georgia, serif; font-size: 10.5pt; }
.rewrite-text.unchanged { background: #fff7e6; border-left-color: #c08a30; }
.rewrite-text.empty { background: #ffeded; border-left-color: #c04040; font-style: italic; }
.chip { display: inline-block; padding: 2pt 6pt; margin: 2pt 4pt 2pt 0; background: #eef; color: #2a6dba; border-radius: 3px; font-size: 8.5pt; font-family: ui-monospace, "SF Mono", Menlo, monospace; }
.chip.feature { background: #e6f0d6; color: #3e5e2a; }
.chip.refused { background: #fde6c8; color: #8c5a14; }
.chip.parse-error { background: #ffd6d6; color: #8c2020; }
.chip.none { background: #f0f0f0; color: #888; }
.notes { font-size: 9pt; color: #555; font-style: italic; margin-top: 6pt; }
.parse-error-text { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 9pt; color: #8c2020; background: #fff5f5; padding: 4pt 8pt; border-radius: 3px; margin-top: 6pt; }
.summary-bar { display: flex; gap: 18pt; flex-wrap: wrap; padding: 8pt 0; border-top: 1px solid #ddd; border-bottom: 1px solid #ddd; font-size: 9.5pt; margin-bottom: 16pt; }
.summary-bar > div { min-width: 90pt; }
.summary-bar .stat-num { font-size: 15pt; font-weight: 600; color: #2a6dba; }
.summary-bar .stat-label { color: #777; font-size: 8.5pt; text-transform: uppercase; letter-spacing: 0.4px; }
"""


def safe(s) -> str:
    return html.escape(str(s if s is not None else ""))


def chip(text: str, klass: str = "") -> str:
    cls = f"chip {klass}".strip()
    return f"<span class='{cls}'>{html.escape(text)}</span>"


def render_anchor(row: dict) -> str:
    status = row.get("generation_status", "?")
    refused = bool(row.get("refused"))
    is_parse_error = status in {"parse_error", "model_fail", "api_error"}

    block_classes = ["anchor-block"]
    if is_parse_error:
        block_classes.append("parse-error")
    elif refused:
        block_classes.append("refused")

    rewrite = row.get("rewrite_text") or ""
    anchor_text = row.get("anchor_text") or ""

    rewrite_classes = ["rewrite-text"]
    if not rewrite.strip():
        rewrite_classes.append("empty")
    elif rewrite.strip() == anchor_text.strip():
        rewrite_classes.append("unchanged")

    parts: list[str] = [f"<div class='{' '.join(block_classes)}'>"]

    # Meta line.
    extras = row.get("anchor_extras") or {}
    meta_bits = [
        f"anchor={row.get('anchor_id','?')}",
        f"status={status}",
    ]
    for k in ("dataset", "score", "score_band"):
        if k in extras and extras[k] not in (None, ""):
            meta_bits.append(f"{k}={extras[k]}")
    parts.append(f"<div class='meta'>{safe(' · '.join(meta_bits))}</div>")

    # Scoring chips row.
    sim = row.get("similarity_scores") or {}
    cos = (sim.get("cosine_embeddings") or {})
    chips: list[str] = []
    if refused:
        chips.append(chip("refused", "refused"))
    if is_parse_error:
        chips.append(chip(status.replace("_", " "), "parse-error"))
    if "composite_change_score" in row:
        chips.append(chip(f"change={row['composite_change_score']}"))
    if "levenshtein_normalized" in sim:
        chips.append(chip(f"lev={sim['levenshtein_normalized']:.2f}"))
    if "token_jaccard" in sim:
        chips.append(chip(f"jacc={sim['token_jaccard']:.2f}"))
    if "hf/all-MiniLM-L6-v2" in cos:
        chips.append(chip(f"hf_cos={cos['hf/all-MiniLM-L6-v2']:.2f}"))
    if "openai/text-embedding-3-small" in cos:
        chips.append(chip(f"oai_cos={cos['openai/text-embedding-3-small']:.2f}"))
    awc, rwc = row.get("anchor_word_count"), row.get("rewrite_word_count")
    if awc is not None and rwc is not None:
        chips.append(chip(f"words {awc}→{rwc}"))
    tin, tout, cost = row.get("tokens_in"), row.get("tokens_out"), row.get("cost_usd")
    if tin is not None and tout is not None:
        chips.append(chip(f"tok {tin}→{tout}"))
    if cost is not None:
        chips.append(chip(f"${cost:.4f}"))
    if chips:
        parts.append("<div>" + "".join(chips) + "</div>")

    # Anchor text.
    parts.append("<div class='label'>Anchor</div>")
    parts.append(f"<div class='anchor-text'>{safe(anchor_text)}</div>")

    # Rewrite text.
    parts.append("<div class='label'>Rewrite</div>")
    parts.append(f"<div class='{' '.join(rewrite_classes)}'>{safe(rewrite) or '(empty)'}</div>")

    # Applied features (dialect strategy only).
    applied = row.get("applied_features") or []
    if isinstance(applied, list):
        parts.append("<div class='label'>Applied features</div>")
        if applied:
            feat_chips = []
            for f in applied:
                if isinstance(f, dict):
                    fid = f.get("id", "?")
                    before = f.get("span_before", "")
                    after = f.get("span_after", "")
                    feat_chips.append(chip(f"{fid}: '{before}' → '{after}'", "feature"))
                else:
                    feat_chips.append(chip(str(f), "feature"))
            parts.append("<div>" + "".join(feat_chips) + "</div>")
        else:
            parts.append("<div>" + chip("no features applied", "none") + "</div>")

    notes = row.get("model_notes")
    if notes:
        parts.append(f"<div class='notes'>Notes: {safe(notes)}</div>")

    parse_err = row.get("parse_error")
    if parse_err and is_parse_error:
        parts.append(f"<div class='parse-error-text'>parse_error: {safe(parse_err[:400])}</div>")

    parts.append("</div>")
    return "\n".join(parts)


def render_summary_bar(rows: list[dict]) -> str:
    """One summary bar showing aggregate stats over a list of rows."""
    n = len(rows)
    ok = sum(1 for r in rows if r.get("generation_status") == "ok")
    refused = sum(1 for r in rows if r.get("refused"))
    ok_rows = [r for r in rows if r.get("generation_status") == "ok"]
    composites = [r.get("composite_change_score") for r in ok_rows if r.get("composite_change_score") is not None]
    avg_comp = sum(composites) / max(1, len(composites)) if composites else 0
    cosines = [
        (r.get("similarity_scores") or {}).get("cosine_embeddings", {}).get("hf/all-MiniLM-L6-v2")
        for r in ok_rows
    ]
    cosines = [c for c in cosines if c is not None]
    avg_cos = sum(cosines) / max(1, len(cosines)) if cosines else 0
    total_cost = sum(r.get("cost_usd") or 0 for r in rows)

    def stat(value, label):
        return f"<div><div class='stat-num'>{value}</div><div class='stat-label'>{label}</div></div>"

    parts = [
        "<div class='summary-bar'>",
        stat(n, "records"),
        stat(f"{100 * ok / max(1, n):.0f}%", "ok"),
        stat(f"{100 * refused / max(1, n):.0f}%", "refused"),
        stat(f"{avg_comp:.2f}", "avg change"),
        stat(f"{avg_cos:.3f}", "avg hf cosine"),
        stat(f"${total_cost:.2f}", "total cost"),
        "</div>",
    ]
    return "\n".join(parts)


def render_html(title: str, subtitle: str, groups: list[tuple[str, list[dict]]]) -> str:
    """Build a single HTML page with a top summary + sections per family group."""
    all_rows = [r for _, rows in groups for r in rows]
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>{safe(title)}</title>",
        f"<style>{CSS}</style></head><body>",
        f"<h1>{safe(title)}</h1>",
        f"<div class='subtitle'>{safe(subtitle)}</div>",
        render_summary_bar(all_rows),
    ]
    for i, (group_label, rows) in enumerate(groups):
        cls = "family-break" if i > 0 else ""
        parts.append(f"<h2 class='{cls}'>{safe(group_label)}  ·  {len(rows)} records</h2>")
        parts.append(render_summary_bar(rows))
        for row in rows:
            parts.append(render_anchor(row))
    parts.append("</body></html>")
    return "\n".join(parts)


def html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            CHROME_BIN, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path.resolve()}", f"file://{html_path.resolve()}",
        ],
        capture_output=True, timeout=300, check=False,
    )
    if proc.returncode != 0 or not pdf_path.exists():
        raise RuntimeError(f"Chrome PDF render failed ({proc.returncode}): {proc.stderr.decode(errors='replace')[:300]}")


def discover_cells(source: Path) -> list[tuple[str, str, str, Path]]:
    """Return (strategy, model, family, path) tuples for every JSONL in source/ matching the schema."""
    cells = []
    for path in sorted(source.glob("*__*__*.jsonl")):
        # Skip the scored / suffix variants.
        if any(x in path.name for x in (".scored.", ".v2.")):
            continue
        parts = path.stem.split("__")
        if len(parts) != 3:
            continue
        strategy, model, family = parts
        cells.append((strategy, model, family, path))
    return cells


def family_sort_key(family: str) -> int:
    order = list(FAMILY_TITLES)
    return order.index(family) if family in order else 99


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=Path("data/generated"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/examples"))
    parser.add_argument("--strategies", default=None,
                        help="Comma-separated. Filter cells to these strategies.")
    parser.add_argument("--models", default=None,
                        help="Comma-separated. Filter cells to these models.")
    parser.add_argument("--families", default=None,
                        help="Comma-separated. Filter cells to these families.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--per-cell", action="store_true",
                      help="One PDF per cell file. Default: one PDF per (strategy, model).")
    mode.add_argument("--combined", action="store_true",
                      help="One PDF for every record in the matrix.")
    parser.add_argument("--keep-html", action="store_true",
                        help="Keep the intermediate HTML alongside each PDF.")
    args = parser.parse_args()

    cells = discover_cells(args.source)
    if not cells:
        raise SystemExit(f"No matching JSONL files in {args.source}")

    if args.strategies:
        wanted = set(s.strip() for s in args.strategies.split(",") if s.strip())
        cells = [c for c in cells if c[0] in wanted]
    if args.models:
        wanted = set(s.strip() for s in args.models.split(",") if s.strip())
        cells = [c for c in cells if c[1] in wanted]
    if args.families:
        wanted = set(s.strip() for s in args.families.split(",") if s.strip())
        cells = [c for c in cells if c[2] in wanted]

    if not cells:
        raise SystemExit("No cells remain after filtering.")

    args.output_dir.mkdir(parents=True, exist_ok=True)

    def load(path: Path) -> list[dict]:
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    if args.combined:
        # One PDF, grouped by (strategy, model) then by family.
        groups_by_sm: dict[tuple[str, str], list[tuple[str, list[dict]]]] = defaultdict(list)
        for strategy, model, family, path in cells:
            rows = load(path)
            groups_by_sm[(strategy, model)].append((family, rows))
        # Flatten into one HTML doc.
        all_groups: list[tuple[str, list[dict]]] = []
        for (strategy, model), family_rows in sorted(groups_by_sm.items()):
            for family, rows in sorted(family_rows, key=lambda x: family_sort_key(x[0])):
                label = f"{strategy} · {model} · {FAMILY_TITLES.get(family, family)}"
                all_groups.append((label, rows))
        html_path = args.output_dir / "report_all.html"
        pdf_path = args.output_dir / "report_all.pdf"
        html_path.write_text(render_html("Full matrix report", "All strategies × models × families", all_groups), encoding="utf-8")
        html_to_pdf(html_path, pdf_path)
        print(f"[ok] wrote combined PDF: {pdf_path} ({pdf_path.stat().st_size / (1024 * 1024):.1f} MB)")
        if not args.keep_html:
            html_path.unlink()
        return

    if args.per_cell:
        # One PDF per (strategy, model, family) cell.
        for strategy, model, family, path in cells:
            rows = load(path)
            label = f"{strategy} · {model} · {FAMILY_TITLES.get(family, family)}"
            stem = path.stem
            html_path = args.output_dir / f"{stem}.html"
            pdf_path = args.output_dir / f"{stem}.pdf"
            html_path.write_text(render_html(label, f"{len(rows)} records", [(family, rows)]), encoding="utf-8")
            html_to_pdf(html_path, pdf_path)
            print(f"[ok] {stem}.pdf  ({pdf_path.stat().st_size / 1024:.0f} KB)")
            if not args.keep_html:
                html_path.unlink()
        return

    # Default: one PDF per (strategy, model) — families grouped inside.
    groups_by_sm = defaultdict(list)
    for strategy, model, family, path in cells:
        groups_by_sm[(strategy, model)].append((family, path))
    for (strategy, model), family_paths in sorted(groups_by_sm.items()):
        family_paths.sort(key=lambda fp: family_sort_key(fp[0]))
        groups = [(FAMILY_TITLES.get(f, f), load(p)) for f, p in family_paths]
        all_rows_in_sm = sum(len(rows) for _, rows in groups)
        title = f"{strategy} · {model}"
        subtitle = f"{all_rows_in_sm} records across {len(groups)} dialect families"
        stem = f"{strategy}__{model}"
        html_path = args.output_dir / f"{stem}.html"
        pdf_path = args.output_dir / f"{stem}.pdf"
        html_path.write_text(render_html(title, subtitle, groups), encoding="utf-8")
        html_to_pdf(html_path, pdf_path)
        print(f"[ok] {stem}.pdf  ({pdf_path.stat().st_size / (1024 * 1024):.1f} MB, {all_rows_in_sm} records)")
        if not args.keep_html:
            html_path.unlink()


if __name__ == "__main__":
    main()
