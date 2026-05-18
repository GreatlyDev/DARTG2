"""Per-million-token price table for the models in use.

Values are best-effort current prices; treat sums as estimates. Override by
placing a JSON file at `config/pricing.json` with the same shape as PRICE_TABLE.

Use `cost_usd(model, tokens_in, tokens_out)` to compute per-record cost. Returns
None when the model is not in the table — callers should propagate the None
rather than crash, so a typo'd model name doesn't take down the runner.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_OVERRIDE_PATH = REPO_ROOT / "config" / "pricing.json"

# USD per 1,000,000 tokens. "in" = prompt/input; "out" = completion/output.
PRICE_TABLE: dict[str, dict[str, float]] = {
    "gpt-4o":                 {"in": 2.50, "out": 10.00},
    "gpt-4o-mini":            {"in": 0.15, "out":  0.60},
    "gpt-5":                  {"in": 5.00, "out": 15.00},   # placeholder until enabled
    "gpt-5.5":                {"in": 5.00, "out": 15.00},   # placeholder
    "claude-haiku-4-5":       {"in": 1.00, "out":  5.00},
    "claude-sonnet-4-6":      {"in": 3.00, "out": 15.00},
    "text-embedding-3-small": {"in": 0.02, "out":  0.00},
}


def _load_overrides() -> dict[str, dict[str, float]]:
    if not _OVERRIDE_PATH.exists():
        return {}
    try:
        data = json.loads(_OVERRIDE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    cleaned: dict[str, dict[str, float]] = {}
    for model, prices in data.items():
        if not isinstance(prices, dict):
            continue
        try:
            cleaned[str(model)] = {"in": float(prices["in"]), "out": float(prices["out"])}
        except (KeyError, TypeError, ValueError):
            continue
    return cleaned


_OVERRIDES = _load_overrides()


def cost_usd(model: str, tokens_in: int | None, tokens_out: int | None) -> float | None:
    """Compute the dollar cost of a single API call. Returns None when the model isn't priced.

    The None return path is intentional — callers should write it to the record so
    consumers can distinguish "unknown price" from "free call"."""
    if tokens_in is None or tokens_out is None:
        return None
    prices = _OVERRIDES.get(model) or PRICE_TABLE.get(model)
    if not prices:
        return None
    cost = (tokens_in * prices["in"] + tokens_out * prices["out"]) / 1_000_000
    return round(cost, 6)
