"""Cheap-tier similarity / distance metrics for dialect rewrite scoring.

All functions take two strings (anchor, rewrite) and return a single value.
Pure Python — no external dependencies. Suitable for scoring thousands of
records in seconds.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable


def exact_match(anchor: str, rewrite: str) -> bool:
    return anchor.strip() == rewrite.strip()


def length_ratio(anchor: str, rewrite: str) -> float:
    """len(rewrite) / len(anchor). 1.0 = same length; 0 anchor returns 0."""
    if not anchor:
        return 0.0
    return round(len(rewrite) / len(anchor), 4)


def levenshtein_distance(a: str, b: str) -> int:
    """Standard DP Levenshtein over characters. O(len(a) * len(b)) time, O(len(b)) space."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    # Ensure b is the shorter one for memory locality.
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            insert = current[j - 1] + 1
            delete = previous[j] + 1
            substitute = previous[j - 1] + (0 if ca == cb else 1)
            current[j] = min(insert, delete, substitute)
        previous = current
    return previous[-1]


def levenshtein_normalized(anchor: str, rewrite: str) -> float:
    """Levenshtein distance normalized to [0, 1] by max length. 0 = identical, 1 = max distance."""
    max_len = max(len(anchor), len(rewrite))
    if max_len == 0:
        return 0.0
    return round(levenshtein_distance(anchor, rewrite) / max_len, 4)


_WORD_RE = re.compile(r"\w+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in _WORD_RE.finditer(text)}


def token_jaccard(anchor: str, rewrite: str) -> float:
    """Jaccard similarity over whitespace+punctuation-split lowercase tokens."""
    a, b = _tokens(anchor), _tokens(rewrite)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return round(inter / union, 4) if union else 0.0


def _char_ngrams(text: str, n: int = 3) -> set[str]:
    text = text.lower()
    if len(text) < n:
        return {text}
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def char_3gram_jaccard(anchor: str, rewrite: str) -> float:
    """Jaccard similarity over 3-character shingles. Catches sub-word changes (e.g. going → gonna)."""
    a, b = _char_ngrams(anchor), _char_ngrams(rewrite)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return round(len(a & b) / len(a | b), 4)


def difflib_ratio(anchor: str, rewrite: str) -> float:
    """Python stdlib SequenceMatcher.ratio() — gestalt-pattern-matching similarity in [0, 1]."""
    return round(difflib.SequenceMatcher(None, anchor, rewrite).ratio(), 4)


def cosine_from_vectors(a: Iterable[float], b: Iterable[float]) -> float:
    """Cosine similarity between two equal-length float vectors. Used by both embedders.

    Coerces inputs to Python floats so torch.Tensor / np.float32 inputs work transparently."""
    a = [float(x) for x in a]
    b = [float(x) for x in b]
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return round(dot / (na * nb), 4)


def cheap_scores(anchor: str, rewrite: str) -> dict:
    """Compute every cheap-tier metric in one call. Used by score_rewrites.py per record."""
    return {
        "exact_match": exact_match(anchor, rewrite),
        "length_ratio": length_ratio(anchor, rewrite),
        "levenshtein_distance": levenshtein_distance(anchor, rewrite),
        "levenshtein_normalized": levenshtein_normalized(anchor, rewrite),
        "token_jaccard": token_jaccard(anchor, rewrite),
        "char_3gram_jaccard": char_3gram_jaccard(anchor, rewrite),
        "difflib_ratio": difflib_ratio(anchor, rewrite),
    }
