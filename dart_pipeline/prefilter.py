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
    feature_realization_count: int = 0
    student_text_corrections: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    semantic_equivalence_status: str = "not_checked"


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text or ""))


def detect_features(candidate_text: str, feature_config: dict) -> list[str]:
    text = candidate_text.lower()
    detected: list[str] = []
    for feature in allowed_feature_markers(feature_config):
        if _count_marker_occurrences(text, feature) and feature not in detected:
            detected.append(feature)
    for feature in feature_config.get("features", []):
        if not isinstance(feature, dict) or not feature.get("allowed_for_generation"):
            continue
        if _detect_pattern_feature(text, feature):
            label = str(feature.get("feature") or feature.get("id") or "").strip()
            if label and label not in detected:
                detected.append(label)
    return detected


def _detect_pattern_feature(text: str, feature: dict) -> bool:
    return _count_pattern_feature(text, feature) > 0


def _count_pattern_feature(text: str, feature: dict) -> int:
    feature_id = str(feature.get("id", "")).lower()
    feature_label = str(feature.get("feature", "")).lower()
    if feature_id == "aae_habitual_be" or feature_label == "habitual be":
        return len(
            re.findall(
                r"\b(?:i|you|he|she|it|we|they|people|students?|kids?|children|cowboys|computers?|[a-z]+s)\s+"
                r"(?:also\s+|always\s+|usually\s+|often\s+)?be\s+[a-z]+ing\b",
                text,
            )
        )
    return 0


def _count_marker_occurrences(text: str, marker: str) -> int:
    marker = marker.lower().strip()
    if not marker:
        return 0
    pattern = re.escape(marker)
    if marker[0].isalnum():
        pattern = r"\b" + pattern
    if marker[-1].isalnum():
        pattern = pattern + r"\b"
    return len(re.findall(pattern, text))


def detect_feature_realizations(candidate_text: str, feature_config: dict) -> list[str]:
    text = candidate_text.lower()
    realizations: list[str] = []
    for feature in allowed_feature_markers(feature_config):
        realizations.extend([feature] * _count_marker_occurrences(text, feature))
    for feature in feature_config.get("features", []):
        if not isinstance(feature, dict) or not feature.get("allowed_for_generation"):
            continue
        label = str(feature.get("feature") or feature.get("id") or "").strip()
        if label:
            realizations.extend([label] * _count_pattern_feature(text, feature))
    return realizations


def allowed_feature_markers(feature_config: dict) -> list[str]:
    markers: list[str] = []
    for marker in flatten_allowed_features(feature_config):
        if marker:
            markers.append(marker)

    for feature in feature_config.get("features", []):
        if not isinstance(feature, dict) or not feature.get("allowed_for_generation"):
            continue
        for marker in feature.get("detection_markers") or []:
            markers.append(str(marker))
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
        marker = marker.strip()
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
    realizations = detect_feature_realizations(candidate_text, feature_config)
    corrections = detect_student_text_corrections(
        anchor_response,
        candidate_text,
        allowed_feature_markers=set(flatten_allowed_features(feature_config)),
    )
    reasons: list[str] = []

    if length_delta > length_tolerance:
        reasons.append("length_outside_tolerance")
    if len(realizations) < min_detected_features:
        reasons.append("insufficient_approved_features")
    if candidate_text.strip().upper() == "FAIL":
        reasons.append("generation_failed")
    if corrections:
        reasons.append("student_text_correction")

    return PrefilterResult(
        passed_prefilter=not reasons,
        length_delta=round(length_delta, 4),
        detected_features=detected,
        feature_realization_count=len(realizations),
        student_text_corrections=corrections,
        rejection_reasons=reasons,
    )
