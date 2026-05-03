import re
from dataclasses import dataclass, field

from dart_pipeline.inventories import flatten_allowed_features

WORD_RE = re.compile(r"\b\S+\b")


@dataclass
class PrefilterResult:
    passed_prefilter: bool
    length_delta: float
    detected_features: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    semantic_equivalence_status: str = "not_checked"


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text or ""))


def detect_features(candidate_text: str, feature_config: dict) -> list[str]:
    text = candidate_text.lower()
    detected: list[str] = []
    for feature in flatten_allowed_features(feature_config):
        marker = feature.lower()
        if marker and marker in text:
            detected.append(feature)
    return detected


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
    reasons: list[str] = []

    if length_delta > length_tolerance:
        reasons.append("length_outside_tolerance")
    if len(detected) < min_detected_features:
        reasons.append("insufficient_approved_features")
    if candidate_text.strip().upper() == "FAIL":
        reasons.append("generation_failed")

    return PrefilterResult(
        passed_prefilter=not reasons,
        length_delta=round(length_delta, 4),
        detected_features=detected,
        rejection_reasons=reasons,
    )
