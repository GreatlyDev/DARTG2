"""base2-only strategy: prompt builder + JSON output parser.

Strips down the upstream multi-strategy registry to the single strategy that
this directory exists to run."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .inventories import format_disallowed_features, format_feature_inventory, load_feature_inventory_file

BASE2_DIR = Path(__file__).resolve().parents[1]

FAMILY_TITLES: dict[str, str] = {
    "aae":          "African American English (AAE)",
    "southern":     "Southern American English",
    "appalachian":  "Appalachian English",
    "midwestern":   "Midwestern / North Central",
    "northeastern": "Northeastern / New England",
    "western":      "Western American English",
}

FAMILY_INVENTORY_FILE: dict[str, str] = {
    "aae":          "aae.json",
    "southern":     "southern.json",
    "appalachian":  "appalachian.json",
    "midwestern":   "midwestern_north_central.json",
    "northeastern": "northeastern_new_england.json",
    "western":      "western.json",
}

PROMPT_VERSION = "base2_v1"
PROMPT_PATH = "prompts/base2.md"


@dataclass
class ParsedOutput:
    rewrite_text: str
    applied_features: list[dict] | None = None
    model_notes: str | None = None
    declared_feature_count: int | None = None
    parse_error: str | None = None
    generation_status: str = "ok"


def load_inventory(family: str) -> dict:
    return load_feature_inventory_file(BASE2_DIR / "config" / "features" / FAMILY_INVENTORY_FILE[family])


def _read_prompt() -> str:
    return (BASE2_DIR / "prompts" / "base2.md").read_text(encoding="utf-8")


def build_input(anchor_text: str, family_title: str, inventory: dict) -> str:
    template = _read_prompt()
    feature_block = format_feature_inventory(inventory)
    disallowed_block = format_disallowed_features(inventory)
    return (
        template
        .replace("{PROMPT}", "[PROMPT NOT PROVIDED]")
        .replace("{ANCHOR_RESPONSE}", anchor_text)
        .replace("{DIALECT_FAMILY}", family_title)
        .replace("{FEATURE_INVENTORY}", feature_block)
        .replace("{DISALLOWED_FEATURES_AND_NOTES}", disallowed_block)
    )


def _extract_json_object(text: str) -> tuple[dict | None, str | None]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()
    try:
        obj = json.loads(text)
        return (obj if isinstance(obj, dict) else None,
                None if isinstance(obj, dict) else "not_a_json_object")
    except json.JSONDecodeError as exc:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            try:
                obj = json.loads(match.group(0))
                if isinstance(obj, dict):
                    return obj, None
            except json.JSONDecodeError as exc2:
                return None, f"json_decode_error after substring extraction: {exc2}"
        return None, f"json_decode_error: {exc}"


def parse_output(raw: str) -> ParsedOutput:
    text = raw.strip()
    if text.upper().strip() in {"FAIL", "FAIL."}:
        return ParsedOutput(rewrite_text="", generation_status="model_fail", parse_error="model returned FAIL")

    parsed, err = _extract_json_object(text)
    if parsed is None:
        return ParsedOutput(rewrite_text="", generation_status="parse_error", parse_error=err)

    rewrite = str(parsed.get("rewrite_text", "")).strip()
    if not rewrite:
        return ParsedOutput(rewrite_text="", generation_status="parse_error", parse_error="missing rewrite_text")

    applied = parsed.get("applied_features")
    applied_list: list[dict] | None = None
    if isinstance(applied, list):
        applied_list = []
        for item in applied:
            if not isinstance(item, dict):
                continue
            name = str(item.get("feature") or item.get("id") or "").strip()
            normalized = dict(item)
            if name and "id" not in normalized:
                normalized["id"] = name
            applied_list.append(normalized)

    declared_count = parsed.get("feature_count")
    declared_int = int(declared_count) if isinstance(declared_count, int) else None
    notes = None
    if isinstance(declared_count, int) and applied_list is not None and declared_count != len(applied_list):
        notes = f"feature_count={declared_count} disagrees with len(applied_features)={len(applied_list)}"

    return ParsedOutput(
        rewrite_text=rewrite,
        applied_features=applied_list,
        model_notes=notes,
        declared_feature_count=declared_int,
    )
