import argparse
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.io_utils import read_jsonl, write_jsonl


WORD_RE = re.compile(r"[A-Za-z][A-Za-z']*")


def words(text: str) -> list[str]:
    return [match.group(0).lower() for match in WORD_RE.finditer(text or "")]


def normalized_text(text: str) -> str:
    return " ".join(words(text))


def candidate_text(row: dict) -> str:
    return str(row.get("candidate_response") or row.get("candidate_text") or row.get("raw_output") or "")


def sequence_ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, normalized_text(left), normalized_text(right)).ratio()


def is_tiny_append(anchor_text: str, variant_text: str, max_extra_words: int = 3) -> bool:
    anchor_words = words(anchor_text)
    variant_words = words(variant_text)
    if len(variant_words) <= len(anchor_words):
        return False
    extra = len(variant_words) - len(anchor_words)
    return extra <= max_extra_words and variant_words[: len(anchor_words)] == anchor_words


def changed_word_count(anchor_text: str, variant_text: str) -> int:
    anchor_words = words(anchor_text)
    variant_words = words(variant_text)
    matcher = SequenceMatcher(a=anchor_words, b=variant_words)
    total = 0
    for tag, start_a, end_a, start_b, end_b in matcher.get_opcodes():
        if tag == "equal":
            continue
        total += (end_a - start_a) + (end_b - start_b)
    return total


def is_weak_minimal_edit(row: dict) -> bool:
    anchor = str(row.get("anchor_response") or row.get("anchor_text") or "")
    variant = candidate_text(row)
    detected = row.get("detected_features") or []
    ratio = sequence_ratio(anchor, variant)
    changed = changed_word_count(anchor, variant)
    if is_tiny_append(anchor, variant):
        return True
    if changed <= 2 and len(detected) <= 1:
        return True
    if ratio >= 0.996:
        return True
    return False


def aae_authenticity_reasons(row: dict) -> list[str]:
    if "african american" not in str(row.get("dialect_family") or "").lower():
        return []
    text = candidate_text(row).lower()
    reasons: list[str] = []
    if re.search(r"\bdone\s+be\b", text):
        reasons.append("aae_done_be_stack")
    stacked = [
        marker
        for marker, pattern in {
            "finna": r"\bfinna\b",
            "ain't": r"\bain['’]?t\b",
            "gonna": r"\bgonna\b",
        }.items()
        if re.search(pattern, text)
    ]
    if len(stacked) >= 2:
        reasons.append("aae_marker_pileup:" + "+".join(stacked))
    return reasons


def has_cross_family_tag_right(row: dict) -> bool:
    if "appalachian" not in str(row.get("dialect_family") or "").lower():
        return False
    return bool(re.search(r"\bright\s*\?", candidate_text(row), flags=re.IGNORECASE))


def add_reason(row: dict, reason: str) -> None:
    reasons = list(row.get("rejection_reasons") or [])
    if reason not in reasons:
        reasons.append(reason)
    row["rejection_reasons"] = reasons
    row["passed_quality_filter"] = False


def audit_rows(rows: list[dict], duplicate_threshold: float) -> list[dict]:
    audited = [dict(row) for row in rows]
    by_anchor: dict[str, list[dict]] = defaultdict(list)
    for row in audited:
        by_anchor[str(row.get("anchor_id") or "")].append(row)

    for anchor_rows in by_anchor.values():
        anchor_rows.sort(key=lambda row: int(row.get("candidate_index") or 0))
        for index, row in enumerate(anchor_rows):
            text = candidate_text(row)
            siblings = [
                {
                    "candidate_id": str(other.get("candidate_id") or ""),
                    "candidate_response": candidate_text(other),
                }
                for other in anchor_rows
                if other is not row
            ]
            row["sibling_candidate_responses"] = siblings
            for previous in anchor_rows[:index]:
                ratio = sequence_ratio(candidate_text(previous), text)
                if ratio >= duplicate_threshold:
                    add_reason(row, "within_anchor_duplicate")
                    row["duplicate_of_candidate_id"] = previous.get("candidate_id")
                    row["duplicate_similarity"] = round(ratio, 4)
                    break

    for row in audited:
        if is_weak_minimal_edit(row):
            add_reason(row, "weak_minimal_edit_or_append")
        if has_cross_family_tag_right(row):
            add_reason(row, "cross_family_tag_right")
        aae_reasons = aae_authenticity_reasons(row)
        if aae_reasons:
            add_reason(row, "aae_authenticity_review")
            row["aae_authenticity_notes"] = aae_reasons

    return audited


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit DART candidates for Ricky-review quality concerns.")
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--duplicate-threshold", type=float, default=0.985)
    args = parser.parse_args()

    rows = read_jsonl(args.candidates)
    audited = audit_rows(rows, duplicate_threshold=args.duplicate_threshold)
    write_jsonl(args.output, audited)

    rejected = [row for row in audited if not row.get("passed_quality_filter")]
    reason_counts = Counter(reason for row in rejected for reason in (row.get("rejection_reasons") or []))
    print(f"Input records: {len(rows)}")
    print(f"Passed after audit: {len(audited) - len(rejected)}")
    print(f"Review after audit: {len(rejected)}")
    for reason, count in reason_counts.most_common(12):
        print(f"  {reason}: {count}")
    print(f"Wrote audited records to {args.output}")


if __name__ == "__main__":
    main()
