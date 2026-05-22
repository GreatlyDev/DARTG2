"""Dialect-rewrite strategies for the unified runner.

Three strategies, each one a small dict in STRATEGIES with:
- build_input(anchor_text, family, family_title, inventory) -> str
    The full Responses-API input string (system instructions + per-anchor inputs).
- parse_output(raw_text) -> ParsedOutput
    Convert the model's text response into the unified record fields.

The runner is strategy-agnostic — it only knows about these two callables and the
unified schema returned by parse_output.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .inventories import format_disallowed_features, format_feature_inventory

REPO_ROOT = Path(__file__).resolve().parents[1]

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


@dataclass
class ParsedOutput:
    rewrite_text: str
    applied_features: list[dict] | None = None
    rejected_candidates: list[dict] | None = None
    model_notes: str | None = None
    parse_error: str | None = None
    generation_status: str = "ok"


def load_inventory(family: str) -> dict:
    path = REPO_ROOT / "config" / "features" / FAMILY_INVENTORY_FILE[family]
    return json.loads(path.read_text(encoding="utf-8"))


def prompt_path_for(strategy_name: str, family: str) -> str:
    """Repo-relative path to the prompt file a given (strategy, family) actually uses."""
    if strategy_name == "naive":
        return "prompts/naive.md"
    if strategy_name in ("base", "inventory_injected"):       # legacy name kept for back-compat
        return "prompts/base.md"
    if strategy_name == "base2":
        return "prompts/base2.md"
    if strategy_name in ("dialect", "inventory_greedy"):      # legacy name kept for back-compat
        return f"prompts/dialects/{family}.md"
    return ""


def _read_prompt_file(name: str) -> str:
    return (REPO_ROOT / "prompts" / name).read_text(encoding="utf-8")


# ───────────────────────────── naive ─────────────────────────────


def _build_naive(anchor_text: str, family: str, family_title: str, inventory: dict) -> str:
    template = _read_prompt_file("naive.md")
    return (
        template
        .replace("{DIALECT_TITLE}", family_title)
        .replace("{DIALECT_FAMILY}", family)
        .replace("{ANCHOR_TEXT}", anchor_text)
    )


def _parse_naive(raw: str) -> ParsedOutput:
    text = raw.strip()
    if text.upper().strip() in {"FAIL", "FAIL."}:
        return ParsedOutput(rewrite_text="", generation_status="model_fail", parse_error="model returned FAIL")
    # Strip leading/trailing quotes the model sometimes adds even when told not to.
    text = re.sub(r'^["“]\s*', "", text)
    text = re.sub(r'\s*["”]$', "", text)
    return ParsedOutput(rewrite_text=text)


# ──────────────────────── inventory_injected ────────────────────────


def _build_inventory_injected(anchor_text: str, family: str, family_title: str, inventory: dict) -> str:
    template = _read_prompt_file("base.md")
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


def _parse_inventory_injected(raw: str) -> ParsedOutput:
    text = raw.strip()
    if text.upper().strip() in {"FAIL", "FAIL."}:
        return ParsedOutput(rewrite_text="", generation_status="model_fail", parse_error="model returned FAIL")
    return ParsedOutput(rewrite_text=text)


# ────────────────────────────── base2 ──────────────────────────────


def _build_base2(anchor_text: str, family: str, family_title: str, inventory: dict) -> str:
    template = _read_prompt_file("base2.md")
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


def _parse_base2(raw: str) -> ParsedOutput:
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
    notes = None
    if isinstance(declared_count, int) and applied_list is not None and declared_count != len(applied_list):
        notes = f"feature_count={declared_count} disagrees with len(applied_features)={len(applied_list)}"

    return ParsedOutput(
        rewrite_text=rewrite,
        applied_features=applied_list,
        model_notes=notes,
    )


# ───────────────────────── inventory_greedy ─────────────────────────


def _build_inventory_greedy(anchor_text: str, family: str, family_title: str, inventory: dict) -> str:
    system_prompt = _read_prompt_file(f"dialects/{family}.md")
    user_block = f"ANCHOR: {anchor_text}\n\nINVENTORY: {json.dumps(inventory, ensure_ascii=False)}"
    return f"{system_prompt}\n\n---\n\n{user_block}"


def _parse_inventory_greedy(raw: str) -> ParsedOutput:
    text = raw.strip()
    if text.upper().strip() in {"FAIL", "FAIL."}:
        return ParsedOutput(rewrite_text="", generation_status="model_fail", parse_error="model returned FAIL")

    parsed, err = _extract_json_object(text)
    if parsed is None:
        return ParsedOutput(rewrite_text="", generation_status="parse_error", parse_error=err)

    # Output key varies by family: aae_output, southern_output, etc.
    output_key = next((k for k in parsed if k.endswith("_output")), None)
    rewrite = str(parsed.get(output_key, "") if output_key else parsed.get("output", ""))
    applied = parsed.get("applied_features")
    rejected = parsed.get("rejected_candidates")
    notes = parsed.get("notes")
    return ParsedOutput(
        rewrite_text=rewrite,
        applied_features=applied if isinstance(applied, list) else None,
        rejected_candidates=rejected if isinstance(rejected, list) else None,
        model_notes=str(notes) if isinstance(notes, str) else None,
    )


def _extract_json_object(text: str) -> tuple[dict | None, str | None]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None, None if isinstance(obj, dict) else "not_a_json_object"
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


# ───────────────────────────── registry ─────────────────────────────


@dataclass
class Strategy:
    name: str
    prompt_version: str
    build_input: Callable[[str, str, str, dict], str]
    parse_output: Callable[[str], ParsedOutput]
    description: str


STRATEGIES: dict[str, Strategy] = {
    "naive": Strategy(
        name="naive",
        prompt_version="naive_v1",
        build_input=_build_naive,
        parse_output=_parse_naive,
        description="One-line conversion prompt. No inventory. Output is the rewrite text only.",
    ),
    "base": Strategy(
        name="base",
        prompt_version="base_v1",
        build_input=_build_inventory_injected,
        parse_output=_parse_inventory_injected,
        description="prompts/base.md with the family's allowed feature inventory injected as text. Free-text rewrite.",
    ),
    "base2": Strategy(
        name="base2",
        prompt_version="base2_v1",
        build_input=_build_base2,
        parse_output=_parse_base2,
        description="prompts/base2.md — stronger variation targets and feature-count reporting. JSON output with rewrite_text + applied_features + feature_count.",
    ),
    "dialect": Strategy(
        name="dialect",
        prompt_version="dialect_v1",
        build_input=_build_inventory_greedy,
        parse_output=_parse_inventory_greedy,
        description="prompts/dialects/<family>.md greedy license-by-anchor prompt. Returns structured JSON with applied_features.",
    ),
}
