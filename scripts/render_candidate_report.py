import argparse
import sys
import re
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.assignments import anchor_identifier
from dart_pipeline.io_utils import read_records


def index_by_anchor_id(rows: list[dict]) -> dict[str, dict]:
    return {anchor_identifier(row): row for row in rows}


def anchor_text(anchor: dict) -> str:
    return anchor.get("anchor_response") or anchor.get("essay") or anchor.get("text") or ""


def clean_anchor_for_display(text: str) -> str:
    """Light report-only cleanup for source text readability.

    Candidate outputs are preserved verbatim. This function only affects how
    anchor text is displayed in review reports; it does not alter source data.
    """
    replacements = {
        "\u0093": '"',
        "\u0094": '"',
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"([.!?])(?=[A-Za-z0-9@])", r"\1 ", text)
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([.!?])\s+", r"\1 ", text)

    def capitalize_sentence(match: re.Match) -> str:
        return f"{match.group(1)} {match.group(2).upper()}"

    text = re.sub(r"([.!?])\s+([a-z])", capitalize_sentence, text)
    return text.strip()


def write_block(lines: list[str], title: str, text: str) -> None:
    lines.append(title)
    lines.append("")
    lines.append("```text")
    lines.append(text.strip() or "[EMPTY]")
    lines.append("```")
    lines.append("")


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a readable Markdown report of generated DART candidates.")
    parser.add_argument("--anchors", required=True, type=Path, help="Anchor CSV/JSONL file.")
    parser.add_argument("--candidates", required=True, type=Path, help="Generated candidates JSONL.")
    parser.add_argument("--output", required=True, type=Path, help="Output Markdown report.")
    args = parser.parse_args()

    anchors = index_by_anchor_id(read_records(args.anchors))
    candidates = read_records(args.candidates)
    grouped: dict[str, list[dict]] = defaultdict(list)
    for candidate in candidates:
        grouped[str(candidate["anchor_id"])].append(candidate)

    lines: list[str] = [
        "# DART Candidate Variant Review Report",
        "",
        f"Total anchors with candidates: {len(grouped)}",
        f"Total candidate records: {len(candidates)}",
        "",
        "These candidate variants are generated outputs for team review. They have not yet passed semantic-equivalence review, dialect-feature review, or human validation.",
        "",
    ]

    for anchor_id in sorted(grouped):
        anchor = anchors.get(anchor_id, {})
        anchor_response = anchor_text(anchor)
        rows = sorted(grouped[anchor_id], key=lambda row: (row.get("dialect_family", ""), int(row.get("candidate_index", 0))))
        dialects = sorted({str(row.get("dialect_family", "")) for row in rows})

        lines.append(f"## Anchor {anchor_id}")
        lines.append(f"- Dialect family: {', '.join(dialects)}")
        if anchor.get("score_band"):
            lines.append(f"- Score band: {anchor['score_band']}")
        if anchor.get("normalized_score"):
            lines.append(f"- Normalized score: {anchor['normalized_score']}")
        lines.append("")
        write_block(lines, "Original anchor response:", clean_anchor_for_display(anchor_response))

        for row in rows:
            lines.append(f"### Candidate {row.get('candidate_index')} - {row.get('dialect_family')}")
            lines.append(f"- Candidate ID: `{row.get('candidate_id')}`")
            lines.append(f"- Status: `{row.get('generation_status')}`")
            lines.append(f"- Model: `{row.get('model')}`")
            lines.append("")
            write_block(lines, "Candidate response:", str(row.get("candidate_response", "")))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8-sig")
    print(f"Wrote candidate report to {args.output}")


if __name__ == "__main__":
    main()
