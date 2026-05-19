from __future__ import annotations

import difflib
import re
from collections.abc import Iterable


WORD_RE = re.compile(r"\w+", re.UNICODE)


def exact_match(anchor: str, candidate: str) -> bool:
    return anchor.strip() == candidate.strip()


def length_ratio(anchor: str, candidate: str) -> float:
    if not anchor:
        return 0.0
    return round(len(candidate) / len(anchor), 4)


def levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    if len(left) < len(right):
        left, right = right, left

    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def levenshtein_normalized(anchor: str, candidate: str) -> float:
    max_len = max(len(anchor), len(candidate))
    if max_len == 0:
        return 0.0
    return round(levenshtein_distance(anchor, candidate) / max_len, 4)


def _tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in WORD_RE.finditer(text or "")}


def token_jaccard(anchor: str, candidate: str) -> float:
    anchor_tokens = _tokens(anchor)
    candidate_tokens = _tokens(candidate)
    if not anchor_tokens and not candidate_tokens:
        return 1.0
    if not anchor_tokens or not candidate_tokens:
        return 0.0
    return round(len(anchor_tokens & candidate_tokens) / len(anchor_tokens | candidate_tokens), 4)


def _char_ngrams(text: str, n: int = 3) -> set[str]:
    text = (text or "").lower()
    if len(text) < n:
        return {text}
    return {text[index : index + n] for index in range(len(text) - n + 1)}


def char_3gram_jaccard(anchor: str, candidate: str) -> float:
    anchor_grams = _char_ngrams(anchor)
    candidate_grams = _char_ngrams(candidate)
    if not anchor_grams and not candidate_grams:
        return 1.0
    if not anchor_grams or not candidate_grams:
        return 0.0
    return round(len(anchor_grams & candidate_grams) / len(anchor_grams | candidate_grams), 4)


def difflib_ratio(anchor: str, candidate: str) -> float:
    return round(difflib.SequenceMatcher(None, anchor, candidate).ratio(), 4)


def cosine_from_vectors(left: Iterable[float], right: Iterable[float]) -> float:
    left_values = [float(value) for value in left]
    right_values = [float(value) for value in right]
    if len(left_values) != len(right_values) or not left_values:
        return 0.0
    dot = sum(a * b for a, b in zip(left_values, right_values))
    left_norm = sum(a * a for a in left_values) ** 0.5
    right_norm = sum(b * b for b in right_values) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return round(dot / (left_norm * right_norm), 4)


def cheap_scores(anchor: str, candidate: str) -> dict[str, float | bool | int]:
    return {
        "exact_match": exact_match(anchor, candidate),
        "length_ratio": length_ratio(anchor, candidate),
        "levenshtein_distance": levenshtein_distance(anchor, candidate),
        "levenshtein_normalized": levenshtein_normalized(anchor, candidate),
        "token_jaccard": token_jaccard(anchor, candidate),
        "char_3gram_jaccard": char_3gram_jaccard(anchor, candidate),
        "difflib_ratio": difflib_ratio(anchor, candidate),
    }
