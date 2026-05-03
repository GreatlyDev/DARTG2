from collections import deque
from itertools import cycle
from typing import Iterable, Sequence

STRATA_FIELDS = ("source_corpus", "score_band", "domain")
SCORE_BAND_ORDER = {"low": 0, "mid": 1, "medium": 1, "high": 2}


def anchor_identifier(anchor: dict) -> str:
    for key in ("anchor_id", "essay_id", "id"):
        value = anchor.get(key)
        if value is not None and str(value).strip():
            return str(value)
    raise ValueError("Anchor is missing anchor_id, essay_id, or id.")


def _assignment_row(anchor: dict, dialect: str, candidates_per_pair: int, strategy: str) -> dict:
    return {
        "anchor_id": anchor_identifier(anchor),
        "dialect_family": dialect,
        "target_candidates": candidates_per_pair,
        "assignment_strategy": strategy,
        "source_corpus": anchor.get("source_corpus"),
        "score_band": anchor.get("score_band"),
        "domain": anchor.get("domain"),
    }


def make_greedy_assignments(
    anchors: Sequence[dict],
    dialects: Sequence[str],
    candidates_per_pair: int = 3,
    limit: int | None = None,
) -> list[dict]:
    if not dialects:
        raise ValueError("At least one dialect family is required.")
    selected = list(anchors[:limit]) if limit is not None else list(anchors)
    dialect_cycle = cycle(dialects)
    return [
        _assignment_row(anchor, next(dialect_cycle), candidates_per_pair, "greedy")
        for anchor in selected
    ]


def make_balanced_assignments(
    anchors: Sequence[dict],
    dialects: Sequence[str],
    candidates_per_pair: int = 3,
    limit: int | None = None,
) -> list[dict]:
    if not dialects:
        raise ValueError("At least one dialect family is required.")
    strata: dict[tuple, deque[dict]] = {}
    for anchor in anchors:
        key = tuple(anchor.get(field, "unknown") for field in STRATA_FIELDS)
        strata.setdefault(key, deque()).append(anchor)

    def sort_key(key: tuple) -> tuple:
        source, score_band, domain = key
        return (SCORE_BAND_ORDER.get(str(score_band).lower(), 99), str(source), str(domain))

    ordered_keys = sorted(strata, key=sort_key)
    mixed: list[dict] = []
    while ordered_keys:
        next_keys: list[tuple] = []
        for key in ordered_keys:
            bucket = strata[key]
            if bucket:
                mixed.append(bucket.popleft())
            if bucket:
                next_keys.append(key)
        ordered_keys = next_keys

    if limit is not None:
        mixed = mixed[:limit]

    dialect_cycle = cycle(dialects)
    return [
        _assignment_row(anchor, next(dialect_cycle), candidates_per_pair, "balanced")
        for anchor in mixed
    ]

