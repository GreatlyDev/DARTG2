import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.assignments import anchor_identifier
from dart_pipeline.io_utils import read_records


def index_by_anchor_id(rows: list[dict]) -> dict[str, dict]:
    return {anchor_identifier(row): row for row in rows}


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
        "# Stage 1 Demo Candidates",
        "",
        f"Total anchors with candidates: {len(grouped)}",
        f"Total candidate records: {len(candidates)}",
        "",
        "These are demo candidates generated from the current draft feature inventories. They are not final DART variants and have not passed semantic-equivalence review, linguistic review, or human validation.",
        "",
    ]

    for anchor_id in sorted(grouped):
        anchor = anchors.get(anchor_id, {})
        anchor_response = anchor.get("anchor_response", anchor.get("essay", ""))
        rows = sorted(grouped[anchor_id], key=lambda row: (row.get("dialect_family", ""), int(row.get("candidate_index", 0))))
        dialects = sorted({str(row.get("dialect_family", "")) for row in rows})

        lines.append(f"## Anchor {anchor_id}")
        lines.append(f"- Dialect family: {', '.join(dialects)}")
        if anchor.get("score_band"):
            lines.append(f"- Score band: {anchor['score_band']}")
        if anchor.get("normalized_score"):
            lines.append(f"- Normalized score: {anchor['normalized_score']}")
        lines.append("")
        write_block(lines, "Original anchor response:", anchor_response)

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
