from pathlib import Path

from dart_pipeline.inventories import format_disallowed_features, format_feature_inventory


def render_generation_prompt(
    template_path: Path,
    assignment_prompt: str,
    anchor_response: str,
    dialect_family: str,
    feature_config: dict,
) -> str:
    template = template_path.read_text(encoding="utf-8-sig")
    replacements = {
        "{PROMPT}": assignment_prompt or "[PROMPT NOT PROVIDED]",
        "{ANCHOR_RESPONSE}": anchor_response,
        "{DIALECT_FAMILY}": dialect_family,
        "{FEATURE_INVENTORY}": format_feature_inventory(feature_config),
        "{DISALLOWED_FEATURES_AND_NOTES}": format_disallowed_features(feature_config),
    }
    rendered = template
    for placeholder, value in replacements.items():
        rendered = rendered.replace(placeholder, value)
    return rendered

