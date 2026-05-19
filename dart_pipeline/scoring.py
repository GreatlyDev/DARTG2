from __future__ import annotations

from typing import Any

from dart_pipeline.generation import is_failed_candidate
from dart_pipeline.prefilter import word_count
from dart_pipeline.similarity import cheap_scores
from dart_pipeline.trace_generation import detect_student_text_corrections, traced_candidate_response


PASSING_STATUSES = {"ok", "demo_unvalidated", "generated", "scored"}


def row_anchor_text(row: dict[str, Any]) -> str:
    return str(row.get("anchor_response") or row.get("anchor_text") or "")


def row_candidate_text(row: dict[str, Any]) -> str:
    return str(row.get("candidate_response") or row.get("candidate_text") or traced_candidate_response(row))


def candidate_quality_score(
    row: dict[str, Any],
    *,
    min_change: float = 0.005,
    max_length_delta: float = 0.20,
    min_word_count: int = 10,
) -> tuple[bool, list[str]]:
    reasons = list(row.get("rejection_reasons") or [])
    status = str(row.get("generation_status") or "").strip().lower()
    candidate_text = row_candidate_text(row)

    if status and status not in PASSING_STATUSES:
        reasons.append(f"generation_status:{status}")
    if is_failed_candidate(row) or candidate_text.strip().upper() == "FAIL":
        reasons.append("generation_failed")
    if row.get("student_text_corrections"):
        reasons.append("student_text_correction")
    if row.get("anchor_word_count") and row.get("candidate_word_count"):
        anchor_words = max(int(row["anchor_word_count"]), 1)
        candidate_words = int(row["candidate_word_count"])
        length_delta = abs(candidate_words - anchor_words) / anchor_words
        if length_delta > max_length_delta:
            reasons.append("length_outside_tolerance")
    if int(row.get("candidate_word_count") or 0) < min_word_count:
        reasons.append("candidate_too_short")
    if float(row.get("composite_change_score") or 0.0) < min_change:
        reasons.append("insufficient_change")

    deduped = sorted(set(reasons))
    return not deduped, deduped


def score_candidate_row(
    row: dict[str, Any],
    *,
    min_change: float = 0.005,
    max_length_delta: float = 0.20,
    min_word_count: int = 10,
    allowed_feature_markers: set[str] | None = None,
) -> dict[str, Any]:
    scored = dict(row)
    anchor_text = row_anchor_text(scored)
    candidate_text = row_candidate_text(scored)
    scores = cheap_scores(anchor_text, candidate_text)
    anchor_words = word_count(anchor_text)
    candidate_words = word_count(candidate_text)
    corrections = detect_student_text_corrections(
        anchor_text,
        candidate_text,
        applied_features=scored.get("applied_features") or [],
        allowed_feature_markers=allowed_feature_markers,
    )

    scored["similarity_scores"] = {**(scored.get("similarity_scores") or {}), **scores}
    scored["anchor_word_count"] = anchor_words
    scored["candidate_word_count"] = candidate_words
    scored["rewrite_word_count"] = candidate_words
    scored["composite_change_score"] = round(1 - float(scores["difflib_ratio"]), 4)
    scored["student_text_corrections"] = corrections
    passed, reasons = candidate_quality_score(
        scored,
        min_change=min_change,
        max_length_delta=max_length_delta,
        min_word_count=min_word_count,
    )
    scored["passed_quality_filter"] = passed
    scored["rejection_reasons"] = reasons
    scored["quality_score"] = round(scored["composite_change_score"] * float(scores["token_jaccard"]), 4)
    return scored
