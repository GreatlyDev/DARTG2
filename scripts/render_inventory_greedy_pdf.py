"""Render anchor/response PDFs for each inventory_greedy_<family>.jsonl file.

For each family, builds an HTML document with one section per anchor (anchor text +
rewrite + applied features + optional notes), then shells out to macOS `cupsfilter`
to convert it to PDF. Writes both the .html and .pdf into docs/examples/.

Usage:
    python scripts/render_inventory_greedy_pdf.py
    python scripts/render_inventory_greedy_pdf.py --family aae
    python scripts/render_inventory_greedy_pdf.py --source data/examples
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

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
h2 { font-size: 13pt; margin: 16pt 0 4pt 0; border-bottom: 1px solid #d0d0d0; padding-bottom: 2pt; }
.subtitle { color: #555; font-size: 10pt; margin-bottom: 16pt; }
.anchor-block { page-break-inside: avoid; margin-bottom: 14pt; padding: 8pt 10pt; border: 1px solid #e0e0e0; border-radius: 4px; background: #fafafa; }
.meta { font-size: 9pt; color: #666; margin-bottom: 6pt; }
.label { font-weight: 600; color: #444; font-size: 9pt; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 8pt; }
.anchor-text { background: #fff; padding: 6pt 8pt; border-left: 3px solid #888; white-space: pre-wrap; font-family: "Times New Roman", Georgia, serif; font-size: 10.5pt; }
.rewrite-text { background: #f0f7ff; padding: 6pt 8pt; border-left: 3px solid #2a6dba; white-space: pre-wrap; font-family: "Times New Roman", Georgia, serif; font-size: 10.5pt; }
.rewrite-unchanged { background: #fff7e6; border-left-color: #c08a30; }
.chip { display: inline-block; padding: 2pt 6pt; margin: 2pt 4pt 2pt 0; background: #e6f0d6; color: #3e5e2a; border-radius: 3px; font-size: 9pt; font-family: ui-monospace, "SF Mono", Menlo, monospace; }
.chip.none { background: #f0f0f0; color: #888; }
.notes { font-size: 9pt; color: #555; font-style: italic; margin-top: 6pt; }
.summary-bar { display: flex; gap: 24pt; padding: 8pt 0; border-top: 1px solid #ddd; border-bottom: 1px solid #ddd; font-size: 9.5pt; margin-bottom: 16pt; }
.summary-bar div { flex: 1; }
.summary-bar .stat-num { font-size: 16pt; font-weight: 600; color: #2a6dba; }
"""


def render_html(family: str, rows: list[dict]) -> str:
    family_title = FAMILY_TITLES.get(family, family.title())
    output_key = f"{family}_output"
    total = len(rows)
    ok_rows = [r for r in rows if r.get("generation_status") == "ok" and r.get("parsed_output")]
    with_applied = [r for r in ok_rows if (r.get("parsed_output") or {}).get("applied_features")]
    total_applied = sum(len((r.get("parsed_output") or {}).get("applied_features", [])) for r in ok_rows)
    avg_applied = total_applied / len(ok_rows) if ok_rows else 0
    unchanged = [r for r in ok_rows if not (r.get("parsed_output") or {}).get("applied_features")]
    model = rows[0].get("model", "") if rows else ""

    parts: list[str] = []
    parts.append("<!DOCTYPE html>\n<html><head>")
    parts.append(f"<meta charset='utf-8'><title>{html.escape(family_title)} Rewrites</title>")
    parts.append(f"<style>{CSS}</style></head><body>")
    parts.append(f"<h1>{html.escape(family_title)} — Inventory-Driven Rewrites</h1>")
    parts.append(
        f"<div class='subtitle'>Anchor → dialect rewrite under the {family_title} feature inventory. "
        f"Model: <code>{html.escape(model)}</code>. Prompt: <code>prompts/{family}.md</code>.</div>"
    )
    parts.append(
        f"<div class='summary-bar'>"
        f"<div><div class='stat-num'>{total}</div>anchors</div>"
        f"<div><div class='stat-num'>{len(with_applied)}</div>rewritten</div>"
        f"<div><div class='stat-num'>{len(unchanged)}</div>unchanged</div>"
        f"<div><div class='stat-num'>{avg_applied:.2f}</div>avg features/anchor</div>"
        f"</div>"
    )

    for row in rows:
        anchor_id = html.escape(str(row.get("anchor_id", "")))
        anchor_text = str(row.get("anchor_text", ""))
        extras = row.get("anchor_extras") or {}
        parsed = row.get("parsed_output") or {}
        rewrite = str(parsed.get(output_key, "") or row.get("raw_output", ""))
        applied = parsed.get("applied_features") or []
        notes = parsed.get("notes")

        meta_bits = [f"anchor_id={anchor_id}"]
        for k in ("dataset", "score", "score_band"):
            if k in extras and extras[k] not in (None, ""):
                meta_bits.append(f"{k}={html.escape(str(extras[k]))}")
        meta_bits.append(f"status={html.escape(str(row.get('generation_status','')))}")

        is_unchanged = (rewrite.strip() == anchor_text.strip()) or not applied
        rewrite_class = "rewrite-text rewrite-unchanged" if is_unchanged else "rewrite-text"

        if applied:
            chips = "".join(
                f"<span class='chip'>{html.escape(str(f.get('id','?')))}: "
                f"&ldquo;{html.escape(str(f.get('span_before','')))}&rdquo; → "
                f"&ldquo;{html.escape(str(f.get('span_after','')))}&rdquo;</span>"
                for f in applied if isinstance(f, dict)
            )
        else:
            chips = "<span class='chip none'>no features applied</span>"

        parts.append("<div class='anchor-block'>")
        parts.append(f"<div class='meta'>{' · '.join(meta_bits)}</div>")
        parts.append(f"<div class='label'>Anchor</div>")
        parts.append(f"<div class='anchor-text'>{html.escape(anchor_text)}</div>")
        parts.append(f"<div class='label'>Rewrite</div>")
        parts.append(f"<div class='{rewrite_class}'>{html.escape(rewrite)}</div>")
        parts.append(f"<div class='label'>Applied features</div>")
        parts.append(f"<div>{chips}</div>")
        if notes:
            parts.append(f"<div class='notes'>Notes: {html.escape(str(notes))}</div>")
        parts.append("</div>")

    parts.append("</body></html>")
    return "\n".join(parts)


CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    """Use headless Chrome to convert HTML → PDF."""
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            CHROME_BIN,
            "--headless=new",
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path.resolve()}",
            f"file://{html_path.resolve()}",
        ],
        capture_output=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0 or not pdf_path.exists():
        raise RuntimeError(
            f"Chrome PDF render failed ({proc.returncode}): {proc.stderr.decode(errors='replace')[:500]}"
        )


def _strip_html_shell(html_doc: str) -> str:
    """Pull out everything between <body> and </body> for combining into a single document."""
    lower = html_doc.lower()
    start = lower.find("<body")
    if start == -1:
        return html_doc
    start = lower.find(">", start) + 1
    end = lower.rfind("</body>")
    return html_doc[start:end if end != -1 else None]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=list(FAMILY_TITLES), default=None,
                        help="Render one family only. Default: all six.")
    parser.add_argument("--source", type=Path, default=Path("data/examples"),
                        help="Directory containing inventory_greedy_<family>.jsonl (default: data/examples).")
    parser.add_argument("--output-dir", type=Path, default=Path("docs/examples"),
                        help="Where to write the PDFs (default: docs/examples).")
    parser.add_argument("--combined", action="store_true",
                        help="Also produce a single inventory_greedy_all.pdf combining every family.")
    parser.add_argument("--keep-html", action="store_true",
                        help="Keep the intermediate .html files alongside each .pdf (default: remove them).")
    args = parser.parse_args()

    families = [args.family] if args.family else list(FAMILY_TITLES)
    rendered_bodies: list[str] = []

    for family in families:
        jsonl_path = args.source / f"inventory_greedy_{family}.jsonl"
        if not jsonl_path.exists():
            print(f"[skip] {family}: {jsonl_path} not found")
            continue
        rows = [json.loads(line) for line in jsonl_path.read_text().splitlines() if line.strip()]
        html_path = args.output_dir / f"inventory_greedy_{family}.html"
        pdf_path = args.output_dir / f"inventory_greedy_{family}.pdf"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        full_html = render_html(family, rows)
        html_path.write_text(full_html, encoding="utf-8")
        html_to_pdf(html_path, pdf_path)
        print(f"[ok]   {family}: wrote {pdf_path} ({pdf_path.stat().st_size:,} bytes) from {len(rows)} anchors")
        rendered_bodies.append(_strip_html_shell(full_html))
        if not args.keep_html:
            html_path.unlink()

    if args.combined and not args.family and rendered_bodies:
        combined_html = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>Inventory-Driven Rewrites — All Families</title>"
            f"<style>{CSS}\n.family-break {{ page-break-before: always; }}</style></head><body>"
            + "<hr class='family-break'/>".join(rendered_bodies)
            + "</body></html>"
        )
        combined_html_path = args.output_dir / "inventory_greedy_all.html"
        combined_pdf_path = args.output_dir / "inventory_greedy_all.pdf"
        combined_html_path.write_text(combined_html, encoding="utf-8")
        html_to_pdf(combined_html_path, combined_pdf_path)
        print(f"[ok]   COMBINED: wrote {combined_pdf_path} ({combined_pdf_path.stat().st_size:,} bytes)")
        if not args.keep_html:
            combined_html_path.unlink()


if __name__ == "__main__":
    main()
