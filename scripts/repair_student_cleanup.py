import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.io_utils import read_records, write_jsonl
from dart_pipeline.scoring import row_candidate_text


WORD_RE = re.compile(r"[A-Za-z][A-Za-z']*")


def _word_spans(text: str) -> list[tuple[str, int, int]]:
    return [(match.group(0), match.start(), match.end()) for match in WORD_RE.finditer(text or "")]


def _correction_set(corrections: list[str]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for correction in corrections:
        if " -> " not in correction:
            continue
        before, after = correction.split(" -> ", 1)
        pairs.add((before.lower(), after.lower()))
    return pairs


def repair_cleanup_text(anchor_text: str, candidate_text: str, corrections: list[str]) -> tuple[str, list[str]]:
    pairs = _correction_set(corrections)
    if not pairs:
        return candidate_text, []

    anchor_spans = _word_spans(anchor_text)
    candidate_spans = _word_spans(candidate_text)
    matcher = SequenceMatcher(
        a=[word.lower() for word, _, _ in anchor_spans],
        b=[word.lower() for word, _, _ in candidate_spans],
    )

    replacements: list[tuple[int, int, str, str]] = []
    for tag, start_a, end_a, start_b, end_b in matcher.get_opcodes():
        if tag == "equal" or start_a == end_a or start_b == end_b:
            continue
        before = " ".join(word for word, _, _ in anchor_spans[start_a:end_a])
        after = " ".join(word for word, _, _ in candidate_spans[start_b:end_b])
        if (before.lower(), after.lower()) not in pairs:
            continue
        replace_start = candidate_spans[start_b][1]
        replace_end = candidate_spans[end_b - 1][2]
        replacements.append((replace_start, replace_end, before, f"{before} -> {after}"))

    repaired = candidate_text
    applied: list[str] = []
    for start, end, before, label in sorted(replacements, reverse=True):
        repaired = repaired[:start] + before + repaired[end:]
        applied.append(label)
    applied.reverse()
    return repaired, applied


def main() -> None:
    parser = argparse.ArgumentParser(description="Mechanically revert detected student-text cleanup spans.")
    parser.add_argument("--raw-candidates", required=True, type=Path)
    parser.add_argument("--scored-candidates", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    scored_by_id = {str(row.get("candidate_id")): row for row in read_records(args.scored_candidates)}
    repaired_rows: list[dict] = []
    repaired_count = 0
    for row in read_records(args.raw_candidates):
        candidate_id = str(row.get("candidate_id") or "")
        scored = scored_by_id.get(candidate_id, {})
        corrections = scored.get("student_text_corrections") or []
        if corrections:
            repaired_text, applied_repairs = repair_cleanup_text(
                str(scored.get("anchor_response") or scored.get("anchor_text") or ""),
                row_candidate_text(row),
                corrections,
            )
        else:
            repaired_text, applied_repairs = row_candidate_text(row), []

        output_row = dict(row)
        if applied_repairs:
            output_row["candidate_response"] = repaired_text
            output_row["raw_output"] = repaired_text
            output_row["mechanical_cleanup_repairs"] = applied_repairs
            repaired_count += 1
        repaired_rows.append(output_row)

    write_jsonl(args.output, repaired_rows)
    print(f"Applied mechanical repairs to {repaired_count} candidate(s).")
    print(f"Wrote {len(repaired_rows)} candidate records to {args.output}")


if __name__ == "__main__":
    main()
