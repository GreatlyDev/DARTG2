import argparse
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.io_utils import read_jsonl, write_jsonl


WORD_RE = re.compile(r"[A-Za-z][A-Za-z']*")
DEFAULT_COMMON_FEATURE_MARKERS = {
    "done",
    "for sure",
    "gonna",
    "ope",
    "pop",
    "reckon",
    "right",
    "wicked",
    "y'all",
    "you guys",
}


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


def surface_change_ratio(anchor_text: str, variant_text: str) -> float:
    anchor_count = max(len(words(anchor_text)), 1)
    return changed_word_count(anchor_text, variant_text) / anchor_count


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


def normalize_feature_marker(marker: str) -> str:
    return re.sub(r"\s+", " ", str(marker or "").lower().strip().strip(".,!?;:"))


def feature_realization_count(row: dict) -> int:
    try:
        return int(row.get("feature_realization_count") or 0)
    except (TypeError, ValueError):
        return 0


def feature_diversity_reasons(row: dict, common_feature_markers: set[str]) -> list[str]:
    detected = {
        normalize_feature_marker(feature)
        for feature in row.get("detected_features") or []
        if normalize_feature_marker(feature)
    }
    realization_count = feature_realization_count(row) or len(detected)
    if not detected or candidate_text(row).strip().upper() == "FAIL":
        return []

    reasons: list[str] = []
    if realization_count < 2:
        reasons.append("single_detected_feature")
    if detected <= common_feature_markers and len(detected) <= 2:
        reasons.append("common_feature_only")
    return reasons


def surface_change_reasons(
    row: dict,
    *,
    min_surface_change_ratio: float,
    max_surface_change_ratio: float,
    long_anchor_word_threshold: int,
    preferred_long_feature_count: int,
) -> list[str]:
    if candidate_text(row).strip().upper() == "FAIL":
        return []

    anchor = str(row.get("anchor_response") or row.get("anchor_text") or "")
    variant = candidate_text(row)
    anchor_count = len(words(anchor))
    ratio = surface_change_ratio(anchor, variant)
    row["surface_change_ratio"] = round(ratio, 4)
    row["audit_anchor_word_count"] = anchor_count
    row["audit_changed_word_count"] = changed_word_count(anchor, variant)
    if not row.get("feature_realization_count"):
        row["feature_realization_count"] = len(row.get("detected_features") or [])

    reasons: list[str] = []
    if ratio < min_surface_change_ratio:
        reasons.append("surface_change_below_minimum")
    if ratio > max_surface_change_ratio:
        reasons.append("surface_change_above_upper_bound")
    if anchor_count >= long_anchor_word_threshold and int(row.get("feature_realization_count") or 0) < preferred_long_feature_count:
        reasons.append("long_anchor_low_feature_count")
    return reasons


def add_reason(row: dict, reason: str) -> None:
    reasons = list(row.get("rejection_reasons") or [])
    if reason not in reasons:
        reasons.append(reason)
    row["rejection_reasons"] = reasons
    row["passed_quality_filter"] = False


def audit_rows(
    rows: list[dict],
    duplicate_threshold: float,
    common_feature_markers: set[str] | None = None,
    min_surface_change_ratio: float = 0.05,
    max_surface_change_ratio: float = 0.25,
    long_anchor_word_threshold: int = 80,
    preferred_long_feature_count: int = 3,
) -> list[dict]:
    common_feature_markers = {
        normalize_feature_marker(marker)
        for marker in (common_feature_markers or DEFAULT_COMMON_FEATURE_MARKERS)
        if normalize_feature_marker(marker)
    }
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
        for reason in surface_change_reasons(
            row,
            min_surface_change_ratio=min_surface_change_ratio,
            max_surface_change_ratio=max_surface_change_ratio,
            long_anchor_word_threshold=long_anchor_word_threshold,
            preferred_long_feature_count=preferred_long_feature_count,
        ):
            add_reason(row, reason)
        if is_weak_minimal_edit(row):
            add_reason(row, "weak_minimal_edit_or_append")
        if has_cross_family_tag_right(row):
            add_reason(row, "cross_family_tag_right")
        for reason in feature_diversity_reasons(row, common_feature_markers):
            add_reason(row, reason)
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
    parser.add_argument("--min-surface-change-ratio", type=float, default=0.05)
    parser.add_argument("--max-surface-change-ratio", type=float, default=0.25)
    parser.add_argument("--long-anchor-word-threshold", type=int, default=80)
    parser.add_argument("--preferred-long-feature-count", type=int, default=3)
    parser.add_argument(
        "--common-feature-markers",
        default=",".join(sorted(DEFAULT_COMMON_FEATURE_MARKERS)),
        help="Comma-separated feature markers that are valid but too generic if they are the only detected variation.",
    )
    args = parser.parse_args()

    rows = read_jsonl(args.candidates)
    common_feature_markers = {
        normalize_feature_marker(marker)
        for marker in args.common_feature_markers.split(",")
        if normalize_feature_marker(marker)
    }
    audited = audit_rows(
        rows,
        duplicate_threshold=args.duplicate_threshold,
        common_feature_markers=common_feature_markers,
        min_surface_change_ratio=args.min_surface_change_ratio,
        max_surface_change_ratio=args.max_surface_change_ratio,
        long_anchor_word_threshold=args.long_anchor_word_threshold,
        preferred_long_feature_count=args.preferred_long_feature_count,
    )
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
