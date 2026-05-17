import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.io_utils import read_jsonl
from dart_pipeline.trace_generation import detect_student_text_corrections, traced_candidate_response


def _parsed_list(row: dict, key: str) -> list:
    parsed = row.get("parsed_output")
    if not isinstance(parsed, dict):
        return []
    value = parsed.get(key, [])
    return value if isinstance(value, list) else []


def _parsed_note(row: dict) -> str:
    parsed = row.get("parsed_output")
    if isinstance(parsed, dict):
        return str(parsed.get("notes") or "")
    return ""


def _write_block(lines: list[str], title: str, text: str) -> None:
    lines.append(title)
    lines.append("")
    lines.append("```text")
    lines.append(text.strip() or "[EMPTY]")
    lines.append("```")
    lines.append("")


def _known_forms(raw: str) -> set[str]:
    return {part.strip() for part in raw.split(",") if part.strip()}


def _corrections(row: dict, known_student_forms: set[str]) -> list[str]:
    existing = row.get("detected_student_corrections")
    if isinstance(existing, list) and existing:
        return [str(value) for value in existing]
    if not known_student_forms:
        return []
    return detect_student_text_corrections(
        str(row.get("anchor_text") or ""),
        traced_candidate_response(row),
        applied_features=_parsed_list(row, "applied_features"),
        known_student_forms=known_student_forms,
    )


def render_report(rows: list[dict], known_student_forms: set[str] | None = None) -> str:
    known_student_forms = known_student_forms or set()
    row_corrections = {index: _corrections(row, known_student_forms) for index, row in enumerate(rows)}
    correction_rows = [row for index, row in enumerate(rows) if row_corrections[index]]
    changed_rows = [
        row for row in rows
        if traced_candidate_response(row).strip() != str(row.get("anchor_text") or "").strip()
    ]
    applied_count = sum(len(_parsed_list(row, "applied_features")) for row in rows)

    lines: list[str] = [
        "# DART Trace Comparison Report",
        "",
        f"Total trace records: {len(rows)}",
        f"Records with changed output: {len(changed_rows)}",
        f"Applied feature count: {applied_count}",
        f"Records with possible student-text corrections: {len(correction_rows)}",
        "",
        "This report is for Student 2 review. It highlights whether a trace-style output applied documented dialect features, rejected features, left the anchor unchanged, or appeared to correct original student wording.",
        "",
    ]

    for row_index, row in enumerate(rows):
        anchor_id = str(row.get("anchor_id", ""))
        dialect_family = str(row.get("dialect_family", ""))
        candidate = traced_candidate_response(row)
        anchor = str(row.get("anchor_text") or "")
        applied = _parsed_list(row, "applied_features")
        rejected = _parsed_list(row, "rejected_candidates")
        corrections = row_corrections.get(row_index, [])

        lines.append(f"## Anchor {anchor_id}")
        lines.append(f"- Dialect family: `{dialect_family}`")
        lines.append(f"- Status: `{row.get('generation_status', '')}`")
        lines.append(f"- Changed output: `{str(candidate.strip() != anchor.strip()).lower()}`")
        lines.append(f"- Applied features: `{len(applied)}`")
        lines.append(f"- Possible student-text corrections: `{len(corrections)}`")
        lines.append("")
        _write_block(lines, "Anchor:", anchor)
        _write_block(lines, "Trace output:", candidate)

        if applied:
            lines.append("Applied feature trace:")
            for feature in applied:
                if isinstance(feature, dict):
                    lines.append(
                        f"- `{feature.get('id', '')}`: `{feature.get('span_before', '')}` -> `{feature.get('span_after', '')}`"
                    )
            lines.append("")

        if rejected:
            lines.append("Rejected feature trace:")
            for feature in rejected:
                if isinstance(feature, dict):
                    lines.append(f"- `{feature.get('id', '')}`: {feature.get('reason', '')}")
            lines.append("")

        if corrections:
            lines.append("Possible student-text corrections:")
            for correction in corrections:
                lines.append(f"- `{correction}`")
            lines.append("")

        note = _parsed_note(row)
        if note:
            lines.append(f"Trace note: {note}")
            lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a Markdown report for trace-style DART candidate outputs.")
    parser.add_argument("--traces", required=True, type=Path, help="Trace JSONL produced by trace-style generation.")
    parser.add_argument("--output", required=True, type=Path, help="Output Markdown report path.")
    parser.add_argument(
        "--known-student-forms",
        default="",
        help="Comma-separated student spellings/forms that should be flagged if they are silently corrected.",
    )
    args = parser.parse_args()

    rows = read_jsonl(args.traces)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_report(rows, known_student_forms=_known_forms(args.known_student_forms)), encoding="utf-8")
    print(f"Wrote trace comparison report to {args.output}")


if __name__ == "__main__":
    main()
