import re
from dataclasses import dataclass, field

from dart_pipeline.inventories import flatten_allowed_features
from dart_pipeline.trace_generation import detect_student_text_corrections

WORD_RE = re.compile(r"\b\S+\b")


@dataclass
class PrefilterResult:
    passed_prefilter: bool
    length_delta: float
    detected_features: list[str] = field(default_factory=list)
    student_text_corrections: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    semantic_equivalence_status: str = "not_checked"


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text or ""))


def detect_features(candidate_text: str, feature_config: dict) -> list[str]:
    text = candidate_text.lower()
    detected: list[str] = []
    for feature in allowed_feature_markers(feature_config):
        marker = feature.lower()
        if marker and marker in text and feature not in detected:
            detected.append(feature)
    return detected


def allowed_feature_markers(feature_config: dict) -> list[str]:
    markers: list[str] = []
    for marker in flatten_allowed_features(feature_config):
        if marker:
            markers.append(marker)

    for feature in feature_config.get("features", []):
        if not isinstance(feature, dict) or not feature.get("allowed_for_generation"):
            continue
        feature_id = str(feature.get("id", "")).lower()
        feature_label = str(feature.get("feature", "")).lower()
        if "tag_right" in feature_id or feature_label == "tag question right":
            markers.append("right")
        if "right_intensifier" in feature_id or feature_label == "right as intensifier":
            markers.append("right")
        if "perfective_done" in feature_id:
            markers.append("done")
        if "double_modal" in feature_id:
            markers.extend(["might could", "might can", "may could"])
        if "needs_cleaned" in feature_id:
            markers.append("needs ")
        if "wants_fixed" in feature_id:
            markers.append("wants ")
        if "a_prefixing" in feature_id:
            markers.append("a-")
        if "demonstrative_them" in feature_id:
            markers.append("them")
        if feature_label == "'em":
            markers.append("'em")

    unique: list[str] = []
    for marker in markers:
        if marker and marker not in unique:
            unique.append(marker)
    return unique


def prefilter_candidate(
    anchor_response: str,
    candidate_text: str,
    feature_config: dict,
    length_tolerance: float = 0.20,
    min_detected_features: int = 2,
) -> PrefilterResult:
    anchor_len = max(word_count(anchor_response), 1)
    candidate_len = word_count(candidate_text)
    length_delta = abs(candidate_len - anchor_len) / anchor_len
    detected = detect_features(candidate_text, feature_config)
    corrections = detect_student_text_corrections(
        anchor_response,
        candidate_text,
        allowed_feature_markers=set(flatten_allowed_features(feature_config)),
    )
    reasons: list[str] = []

    if length_delta > length_tolerance:
        reasons.append("length_outside_tolerance")
    if len(detected) < min_detected_features:
        reasons.append("insufficient_approved_features")
    if candidate_text.strip().upper() == "FAIL":
        reasons.append("generation_failed")
    if corrections:
        reasons.append("student_text_correction")

    return PrefilterResult(
        passed_prefilter=not reasons,
        length_delta=round(length_delta, 4),
        detected_features=detected,
        student_text_corrections=corrections,
        rejection_reasons=reasons,
    )
