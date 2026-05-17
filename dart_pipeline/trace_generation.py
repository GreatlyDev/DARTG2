from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?|\n?```\s*$", re.IGNORECASE)
WORD_RE = re.compile(r"[A-Za-z][A-Za-z']*")


FAMILY_OUTPUT_KEYS = {
    "aae": "aae_output",
    "african american english (aae)": "aae_output",
    "southern": "southern_output",
    "southern american english": "southern_output",
    "appalachian": "appalachian_output",
    "appalachian english": "appalachian_output",
    "midwestern": "midwestern_output",
    "midwestern/north central": "midwestern_output",
    "northeastern": "northeastern_output",
    "northeastern/new england": "northeastern_output",
    "western": "western_output",
    "western american english": "western_output",
}


def parse_model_json(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    text = JSON_FENCE_RE.sub("", raw.strip()).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None, f"json_decode_error: {exc}"
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as nested_exc:
            return None, f"json_decode_error after substring extraction: {nested_exc}"
    if not isinstance(parsed, dict):
        return None, "json_decode_error: parsed output is not an object"
    return parsed, None


def family_output_key(dialect_family: str) -> str:
    normalized = str(dialect_family).strip().lower()
    return FAMILY_OUTPUT_KEYS.get(normalized, f"{normalized.replace(' ', '_').replace('/', '_')}_output")


def build_trace_generation_input(
    template_path: Path,
    dialect_family: str,
    anchor_text: str,
    feature_config: dict[str, Any],
) -> str:
    template = template_path.read_text(encoding="utf-8-sig")
    replacements = {
        "{DIALECT_FAMILY}": dialect_family,
        "{OUTPUT_KEY}": family_output_key(dialect_family),
        "{ANCHOR_RESPONSE}": anchor_text,
        "{FEATURE_INVENTORY_JSON}": json.dumps(feature_config, ensure_ascii=False, indent=2),
    }
    rendered = template
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)
    return rendered


def traced_candidate_response(row: dict[str, Any]) -> str:
    parsed = row.get("parsed_output")
    if isinstance(parsed, dict):
        output = parsed.get(family_output_key(str(row.get("dialect_family", ""))))
        if isinstance(output, str):
            return output.strip()
    return str(row.get("candidate_response") or row.get("raw_output") or "").strip()


def _words(text: str) -> list[str]:
    return WORD_RE.findall(text or "")


def _applied_spans(applied_features: list[dict[str, Any]]) -> set[str]:
    spans: set[str] = set()
    for feature in applied_features:
        if not isinstance(feature, dict):
            continue
        for key in ("span_before", "span_after"):
            value = feature.get(key)
            if isinstance(value, str) and value.strip():
                spans.add(value.strip().lower())
    return spans


def detect_student_text_corrections(
    anchor_text: str,
    candidate_text: str,
    applied_features: list[dict[str, Any]] | None = None,
    known_student_forms: set[str] | None = None,
) -> list[str]:
    anchor_words = _words(anchor_text)
    candidate_words = _words(candidate_text)
    applied = _applied_spans(applied_features or [])
    suspicious_forms = {form.lower() for form in (known_student_forms or set())}
    corrections: set[str] = set()

    matcher = SequenceMatcher(a=[word.lower() for word in anchor_words], b=[word.lower() for word in candidate_words])
    for tag, start_a, end_a, start_b, end_b in matcher.get_opcodes():
        if tag == "equal":
            continue
        before = " ".join(anchor_words[start_a:end_a]).strip()
        after = " ".join(candidate_words[start_b:end_b]).strip()
        if not before or not after:
            continue
        before_lower = before.lower()
        after_lower = after.lower()
        if before_lower in applied or after_lower in applied:
            continue
        if suspicious_forms and before_lower not in suspicious_forms:
            continue
        if before_lower != after_lower:
            corrections.add(f"{before} -> {after}")

    return sorted(corrections)
