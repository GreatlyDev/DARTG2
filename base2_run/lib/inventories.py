import json
from pathlib import Path
from typing import Any

FEATURE_BUCKETS = (
    "allowed_lexical_features",
    "allowed_syntactic_features",
    "allowed_orthographic_features",
    "allowed_discourse_features",
)
CATEGORY_LABELS = {
    "lexical": "Lexical features",
    "syntactic": "Syntactic features",
    "orthographic": "Orthographic features",
    "discourse": "Discourse features",
}


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def load_feature_inventory_file(path: Path) -> dict[str, Any]:
    return _read_json(path)


def format_feature_inventory(config: dict[str, Any]) -> str:
    if "features" in config:
        lines: list[str] = []
        for category, label in CATEGORY_LABELS.items():
            features = [
                feature for feature in config["features"]
                if feature.get("category") == category and feature.get("allowed_for_generation")
            ]
            if features:
                formatted = []
                for feature in features:
                    text = feature["feature"]
                    if feature.get("description"):
                        text += f" ({feature['description']})"
                    if feature.get("blocked_context"):
                        text += f" Avoid: {feature['blocked_context']}"
                    formatted.append(text)
                lines.append(f"{label}: " + "; ".join(formatted))
        if config.get("review_status"):
            lines.append("Review status: " + str(config["review_status"]))
        return "\n".join(lines)

    lines = []
    labels = {
        "allowed_lexical_features": "Lexical features",
        "allowed_syntactic_features": "Syntactic features",
        "allowed_orthographic_features": "Orthographic features",
        "allowed_discourse_features": "Discourse features",
    }
    for key, label in labels.items():
        values = config.get(key, [])
        if values:
            lines.append(f"{label}: " + "; ".join(str(value) for value in values))
    if config.get("usage_notes"):
        lines.append("Usage notes: " + " ".join(str(note) for note in config["usage_notes"]))
    return "\n".join(lines)


def format_disallowed_features(config: dict[str, Any]) -> str:
    parts: list[str] = []
    disallowed = config.get("disallowed_features", [])
    if disallowed:
        parts.append("Disallowed features: " + "; ".join(str(value) for value in disallowed))
    notes = config.get("safety_notes", [])
    if notes:
        parts.append("Safety notes: " + " ".join(str(note) for note in notes))
    if config.get("review_status") and config.get("review_status") != "approved":
        parts.append(f"Draft status: {config['review_status']} requires team and/or linguist review before final benchmark use.")
    elif config.get("needs_linguist_review"):
        parts.append("Draft status: this inventory requires team and/or linguist review before final benchmark use.")
    return "\n".join(parts)
