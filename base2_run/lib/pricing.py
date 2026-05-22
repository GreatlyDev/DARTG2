from __future__ import annotations

PRICE_TABLE: dict[str, dict[str, float]] = {
    "gpt-4o":                 {"in": 2.50, "out": 10.00},
    "gpt-4o-mini":            {"in": 0.15, "out":  0.60},
    "claude-haiku-4-5":       {"in": 1.00, "out":  5.00},
    "claude-sonnet-4-6":      {"in": 3.00, "out": 15.00},
    "text-embedding-3-small": {"in": 0.02, "out":  0.00},
}


def cost_usd(model: str, tokens_in: int | None, tokens_out: int | None) -> float | None:
    if tokens_in is None or tokens_out is None:
        return None
    prices = PRICE_TABLE.get(model)
    if not prices:
        return None
    return round((tokens_in * prices["in"] + tokens_out * prices["out"]) / 1_000_000, 6)
