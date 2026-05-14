"""Render PDFs of the per-dialect prompt files (prompts/<family>.md).

Uses pandoc to convert Markdown → HTML, then headless Chrome to convert HTML → PDF.

Usage:
    python scripts/render_prompt_pdf.py
    python scripts/render_prompt_pdf.py --family aae
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

FAMILIES = ["aae", "southern", "appalachian", "midwestern", "northeastern", "western"]

CSS = """
@page { size: Letter; margin: 0.75in; }
body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif; font-size: 10.5pt; line-height: 1.5; color: #1a1a1a; max-width: 100%; }
h1 { font-size: 18pt; margin: 0 0 12pt 0; padding-bottom: 4pt; border-bottom: 2px solid #2a6dba; }
h2 { font-size: 14pt; margin: 18pt 0 6pt 0; color: #2a6dba; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt 0; }
h4 { font-size: 10.5pt; margin: 10pt 0 4pt 0; color: #555; }
p { margin: 6pt 0; }
ol, ul { margin: 6pt 0 6pt 18pt; padding: 0; }
li { margin: 3pt 0; }
code { font-family: ui-monospace, "SF Mono", Menlo, monospace; font-size: 9.5pt; background: #f0f0f0; padding: 1pt 3pt; border-radius: 2px; }
pre { background: #f6f8fa; padding: 8pt 10pt; border-radius: 4px; overflow-x: auto; border: 1px solid #e0e0e0; }
pre code { background: transparent; padding: 0; font-size: 9pt; line-height: 1.4; }
strong { font-weight: 600; }
hr { border: none; border-top: 1px solid #ddd; margin: 16pt 0; }
"""


def md_to_html(md_path: Path, html_path: Path) -> None:
    proc = subprocess.run(
        [
            "pandoc",
            "--from=markdown+pipe_tables+backtick_code_blocks",
            "--to=html5",
            "--standalone",
            f"--metadata=title:{md_path.stem}",
            str(md_path),
        ],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"pandoc failed: {proc.stderr.decode(errors='replace')[:500]}")
    body_html = proc.stdout.decode("utf-8")
    # Inject CSS into the head
    if "<head>" in body_html:
        body_html = body_html.replace("</head>", f"<style>{CSS}</style></head>", 1)
    else:
        body_html = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{body_html}</body></html>"
    html_path.write_text(body_html, encoding="utf-8")


def html_to_pdf(html_path: Path, pdf_path: Path) -> None:
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
    lower = html_doc.lower()
    start = lower.find("<body")
    if start == -1:
        return html_doc
    start = lower.find(">", start) + 1
    end = lower.rfind("</body>")
    return html_doc[start:end if end != -1 else None]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--family", choices=FAMILIES, default=None,
                        help="Render one family only. Default: all six.")
    parser.add_argument("--prompts-dir", type=Path, default=Path("prompts"),
                        help="Directory containing <family>.md (default: prompts).")
    parser.add_argument("--output-dir", type=Path, default=Path("docs/examples"),
                        help="Where to write the PDFs (default: docs/examples).")
    parser.add_argument("--combined", action="store_true",
                        help="Also produce a single prompts_all.pdf combining every family.")
    parser.add_argument("--keep-html", action="store_true",
                        help="Keep the intermediate .html files alongside each .pdf (default: remove them).")
    args = parser.parse_args()

    families = [args.family] if args.family else FAMILIES
    rendered_bodies: list[str] = []

    for family in families:
        md_path = args.prompts_dir / f"{family}.md"
        if not md_path.exists():
            print(f"[skip] {family}: {md_path} not found")
            continue
        html_path = args.output_dir / f"prompt_{family}.html"
        pdf_path = args.output_dir / f"prompt_{family}.pdf"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        md_to_html(md_path, html_path)
        html_to_pdf(html_path, pdf_path)
        print(f"[ok]   {family}: wrote {pdf_path} ({pdf_path.stat().st_size:,} bytes)")
        rendered_bodies.append(_strip_html_shell(html_path.read_text(encoding="utf-8")))
        if not args.keep_html:
            html_path.unlink()

    if args.combined and not args.family and rendered_bodies:
        combined_html = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<title>Per-Dialect Conversion Prompts — All Families</title>"
            f"<style>{CSS}\n.family-break {{ page-break-before: always; border: none; margin: 0; padding: 0; }}</style></head><body>"
            + "<hr class='family-break'/>".join(rendered_bodies)
            + "</body></html>"
        )
        combined_html_path = args.output_dir / "prompts_all.html"
        combined_pdf_path = args.output_dir / "prompts_all.pdf"
        combined_html_path.write_text(combined_html, encoding="utf-8")
        html_to_pdf(combined_html_path, combined_pdf_path)
        print(f"[ok]   COMBINED: wrote {combined_pdf_path} ({combined_pdf_path.stat().st_size:,} bytes)")
        if not args.keep_html:
            combined_html_path.unlink()


if __name__ == "__main__":
    main()
