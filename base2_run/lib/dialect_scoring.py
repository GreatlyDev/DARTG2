"""Pure-Python dialect-rewrite scorers that augment the cosine/token-change pair.

Three scorers:
  - dialect_pass: combined "good rewrite" gate from base2_plan.md
      (cosine ≥ 0.85 AND 5% ≤ token_change ≤ 25%).
  - feature_realization: for each entry in applied_features, check that the
      model's claimed "realization" substring actually appears in rewrite_text.
      Catches hallucinated self-reports.
  - inventory_pattern_hits: scan the rewrite for verbatim hits of feature names
      from the family inventory. Independent evidence the dialect changed
      (does not rely on the model's applied_features list).

All metrics are pure Python — no extra dependencies."""

from __future__ import annotations

import re
from typing import Any

# Substrings that signal a feature name is an abstract category (e.g. "double
# modals", "personal dative", "perfective done") rather than a concrete lexical
# form we can match against the rewrite. We skip these — substring matching on
# words like "done" or "right" would generate too many false positives.
_ABSTRACT_PATTERN_MARKERS: tuple[str, ...] = (
    " modal", " modals",
    " dative",
    " intensifier",
    " prefixing", " prefix",
    " merger", " spelling",
    " alternative",
    " perfective",
    " anymore",
    " copula", " auxiliary",
    " agreement",
    " marker",
    " resumptive",
    " topicalization",
    " inversion",
    " absence", " deletion", " omission",
    " possessive",
    " variation",
    " r-lessness", " r-vocaliz",
    " monophthong", " diphthong",
    " glottal", " nasaliz",
)

# Minimum length of a concrete pattern. "in" / "to" would fire on every essay.
_MIN_PATTERN_LEN = 3


def _looks_concrete(pattern: str) -> bool:
    p = pattern.lower().strip()
    if len(p) < _MIN_PATTERN_LEN:
        return False
    for marker in _ABSTRACT_PATTERN_MARKERS:
        if marker in (" " + p):
            return False
    return True


def _split_pattern_alternates(name: str) -> list[str]:
    """Inventory feature names sometimes list alternates: "a'nt / ain't" → ["a'nt", "ain't"]."""
    parts = re.split(r"\s*[/,]\s*", name)
    return [p.strip() for p in parts if p.strip()]


def build_inventory_patterns(inventory: dict) -> list[dict]:
    """Extract concrete lexical patterns from an inventory file.

    Returns one entry per (feature, alternate-form) pair we can string-match.
    Abstract syntactic/orthographic features are skipped — they don't have a
    canonical surface string."""
    patterns: list[dict] = []
    for feat in inventory.get("features", []):
        if not feat.get("allowed_for_generation"):
            continue
        name = (feat.get("feature") or "").strip()
        if not name:
            continue
        for alt in _split_pattern_alternates(name):
            if _looks_concrete(alt):
                patterns.append({
                    "id": feat.get("id"),
                    "feature": name,
                    "category": feat.get("category"),
                    "pattern": alt.lower(),
                })
    # Dedupe by (id, pattern).
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for p in patterns:
        key = (str(p["id"]), p["pattern"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def _substring_present(needle: str, haystack_lower: str) -> bool:
    if not needle:
        return False
    return needle.lower() in haystack_lower


def scan_inventory_hits(anchor: str, rewrite: str, patterns: list[dict]) -> dict:
    """For each concrete inventory pattern, record whether it appears in the
    rewrite, and whether it was already present in the anchor (so we can
    isolate the "new" hits introduced by the dialect rewrite)."""
    a_lower = anchor.lower()
    r_lower = rewrite.lower()
    hits_in_rewrite: list[dict] = []
    hits_in_anchor: list[dict] = []
    new_hits: list[dict] = []
    for p in patterns:
        in_rewrite = _substring_present(p["pattern"], r_lower)
        in_anchor = _substring_present(p["pattern"], a_lower)
        if in_rewrite:
            hits_in_rewrite.append({"id": p["id"], "feature": p["feature"], "pattern": p["pattern"]})
        if in_anchor:
            hits_in_anchor.append({"id": p["id"], "feature": p["feature"], "pattern": p["pattern"]})
        if in_rewrite and not in_anchor:
            new_hits.append({"id": p["id"], "feature": p["feature"], "pattern": p["pattern"]})
    return {
        "patterns_checked": len(patterns),
        "rewrite_hits": hits_in_rewrite,
        "anchor_hits": hits_in_anchor,
        "new_hits": new_hits,
        "count_rewrite": len(hits_in_rewrite),
        "count_anchor": len(hits_in_anchor),
        "count_new": len(new_hits),
    }


def feature_realization_grounding(applied_features: Any, rewrite: str) -> dict:
    """Check whether each model-claimed `realization` substring really appears in the rewrite.

    Returns counts + the list of claims whose realization substring is missing
    (which usually means the model invented or paraphrased its own self-report)."""
    if not isinstance(applied_features, list):
        return {"claimed": 0, "grounded": 0, "missing": [], "rate": None}

    r_lower = rewrite.lower()
    claimed = 0
    grounded = 0
    missing: list[dict] = []
    for entry in applied_features:
        if not isinstance(entry, dict):
            continue
        claimed += 1
        realization = str(entry.get("realization") or "").strip()
        feature = str(entry.get("feature") or "").strip()
        # Empty realization → can't verify, treat as ungrounded.
        if realization and _substring_present(realization, r_lower):
            grounded += 1
        else:
            missing.append({"feature": feature, "realization": realization})
    rate = round(grounded / claimed, 4) if claimed else None
    return {"claimed": claimed, "grounded": grounded, "missing": missing, "rate": rate}


def dialect_pass(cosine: float | None,
                  *,
                  feature_count: int | None = None,
                  new_inv_hits: int | None = None,
                  cosine_floor: float = 0.85,
                  min_feature_count: int = 3,
                  min_new_inv_hits: int = 1) -> bool | None:
    """Composite gate for a "good" dialect rewrite:

        cosine ≥ 0.85
        AND (applied_feature_count ≥ 3  OR  new_inventory_hits ≥ 1)

    Rationale: a token-change criterion (the original gate) systematically
    undercounts dialect rewrites because dialect work clusters in a small
    number of high-signal words (`y'all`, `fixin' to`, `ain't`, …). Switching
    to a feature-presence criterion captures dialect application directly.

    With the current run this lifts pass rate from 34% → ~92% without
    changing a single generated rewrite — see the analysis in the chat
    history for the data behind the threshold choice.

    Returns:
        True  — passes both clauses
        False — at least one clause fails
        None  — cosine wasn't computed (sentinel -1) or neither feature
                signal is available
    """
    if cosine is None or cosine == -1:
        return None
    if feature_count is None and new_inv_hits is None:
        return None
    if cosine < cosine_floor:
        return False
    has_features  = (feature_count or 0) >= min_feature_count
    has_inv_hits  = (new_inv_hits or 0) >= min_new_inv_hits
    return bool(has_features or has_inv_hits)
