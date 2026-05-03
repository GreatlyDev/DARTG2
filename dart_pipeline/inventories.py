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


def load_feature_inventory(path: Path) -> dict[str, dict[str, Any]]:
    data = _read_json(path)
    if not isinstance(data, dict):
        raise ValueError("Feature inventory must be a JSON object.")

    if path.name.endswith(".index.json"):
        inventory: dict[str, dict[str, Any]] = {}
        for family, relative_file in data.items():
            feature_path = path.parent / str(relative_file)
            config = _read_json(feature_path)
            if config.get("dialect_family") != family:
                raise ValueError(f"Feature file {feature_path} does not match index family {family}.")
            _validate_feature_config(family, config)
            inventory[family] = config
        return inventory

    # Backward-compatible combined inventory support.
    for family, config in data.items():
        if not isinstance(config, dict):
            raise ValueError(f"Feature inventory for {family} must be an object.")
        if "features" in config:
            _validate_feature_config(family, config)
        else:
            missing = [bucket for bucket in FEATURE_BUCKETS if bucket not in config]
            if missing:
                raise ValueError(f"Feature inventory for {family} is missing: {', '.join(missing)}")
    return data


def _validate_feature_config(family: str, config: dict[str, Any]) -> None:
    if not isinstance(config.get("features"), list):
        raise ValueError(f"Feature inventory for {family} must include a features list.")
    for feature in config["features"]:
        for key in ("id", "category", "feature", "source_reference", "allowed_for_generation"):
            if key not in feature:
                raise ValueError(f"Feature inventory for {family} has a feature missing {key}.")
        if feature["category"] not in CATEGORY_LABELS:
            raise ValueError(f"Feature {feature['id']} has unsupported category {feature['category']}.")


def _feature_name(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("feature", "")).strip()
    return str(value).strip()


def flatten_allowed_features(config: dict[str, Any]) -> list[str]:
    if "features" in config:
        return [
            _feature_name(feature)
            for feature in config["features"]
            if feature.get("allowed_for_generation") and _feature_name(feature)
        ]

    features: list[str] = []
    for bucket in FEATURE_BUCKETS:
        values = config.get(bucket, [])
        if isinstance(values, list):
            features.extend(_feature_name(value) for value in values if _feature_name(value))
    return features


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
