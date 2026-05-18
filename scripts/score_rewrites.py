"""Post-process dialect-rewrite JSONL files with similarity metrics.

Adds a `similarity_scores` block to every record. Cheap-tier metrics are
always computed (exact_match, length_ratio, Levenshtein, Jaccards, difflib).
Embedding-tier cosines are added when --embedders is set (default both).

Embedder keys:
  openai  — OpenAI text-embedding-3-small (cloud, $0.02/M tokens)
  hf      — Local sentence-transformers all-MiniLM-L6-v2 (free, slower; first
            run pip-installs sentence-transformers and downloads the model)

Usage:
    python scripts/score_rewrites.py                                   # default: both embedders
    python scripts/score_rewrites.py --embedders ""                    # cheap only
    python scripts/score_rewrites.py --embedders openai
    python scripts/score_rewrites.py --input 'data/generated/naive__*.jsonl'
    python scripts/score_rewrites.py --output-suffix scored            # writes .scored.jsonl beside each input
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dart_pipeline.generation import load_env_file
from dart_pipeline.io_utils import read_jsonl, write_jsonl
from dart_pipeline.similarity import cheap_scores, cosine_from_vectors
from dart_pipeline.strategies import FAMILY_TITLES, prompt_path_for


OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
DEFAULT_INPUT_GLOB = "data/generated/*__*__*.jsonl"


# ───────────────────────── OpenAI embedder ─────────────────────────


def openai_embed_batch(texts: list[str], model: str, api_key: str, timeout: int = 60) -> list[list[float]]:
    """Submit a batch of inputs to OpenAI's embeddings endpoint. Returns a list of vectors."""
    payload = {"model": model, "input": texts}
    req = urllib.request.Request(
        OPENAI_EMBEDDINGS_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI embeddings request failed HTTP {exc.code}: {body}") from exc
    return [item["embedding"] for item in raw.get("data", [])]


def openai_cosines(pairs: list[tuple[str, str]], model: str, api_key: str, batch_size: int = 100) -> list[float]:
    """For each (anchor, rewrite) pair, return cosine similarity using OpenAI embeddings.
    Batches all texts in groups of `batch_size` to minimize API calls."""
    # Flatten to one list, batch, then split back into pairs.
    flat: list[str] = []
    for a, r in pairs:
        flat.append(a if a.strip() else " ")
        flat.append(r if r.strip() else " ")

    vectors: list[list[float]] = []
    for i in range(0, len(flat), batch_size):
        chunk = flat[i : i + batch_size]
        print(f"  openai embeddings: batch {i // batch_size + 1}/{(len(flat) + batch_size - 1) // batch_size} "
              f"({len(chunk)} inputs)")
        vectors.extend(openai_embed_batch(chunk, model=model, api_key=api_key))

    cosines: list[float] = []
    for j in range(0, len(vectors), 2):
        cosines.append(cosine_from_vectors(vectors[j], vectors[j + 1]))
    return cosines


# ────────────────────────── HF embedder ──────────────────────────


_HF_MODEL_CACHE: dict[str, object] = {}


def hf_load_model(name: str):
    if name in _HF_MODEL_CACHE:
        return _HF_MODEL_CACHE[name]
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise SystemExit(
            "sentence-transformers is not installed. Run `pip install sentence-transformers` first, "
            "or pass --embedders openai (or --embedders \"\") to skip HF."
        ) from exc
    print(f"  loading HF model {name} (downloads on first use)…")
    model = SentenceTransformer(name)
    _HF_MODEL_CACHE[name] = model
    return model


def hf_cosines(pairs: list[tuple[str, str]], model_name: str) -> list[float]:
    """Encode all anchor/rewrite texts locally and return cosines."""
    model = hf_load_model(model_name)
    flat: list[str] = []
    for a, r in pairs:
        flat.append(a if a.strip() else " ")
        flat.append(r if r.strip() else " ")
    print(f"  encoding {len(flat)} texts on HF model {model_name}…")
    vectors = model.encode(flat, convert_to_numpy=False, show_progress_bar=False)
    cosines: list[float] = []
    for j in range(0, len(vectors), 2):
        cosines.append(cosine_from_vectors(list(vectors[j]), list(vectors[j + 1])))
    return cosines


# ───────────────────────────── main ─────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default=DEFAULT_INPUT_GLOB,
                        help=f"Glob of JSONL files to score (default: {DEFAULT_INPUT_GLOB}).")
    parser.add_argument("--embedders", default="hf",
                        help="Comma-separated embedders to run. Valid: openai, hf. "
                             "Default: hf (local-only; OpenAI embeddings model isn't enabled on this project). "
                             "Pass --embedders openai,hf to use both, or --embedders \"\" to skip embeddings entirely.")
    parser.add_argument("--openai-embedding-model", default="text-embedding-3-small")
    parser.add_argument("--hf-embedding-model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--openai-batch-size", type=int, default=100)
    parser.add_argument("--key-file", type=Path, default=Path(".openaiapi"))
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--output-suffix", default=None,
                        help="If set, write results to <stem>.<suffix>.jsonl beside each input. "
                             "Default: in-place.")
    parser.add_argument("--dry-run", action="store_true", help="Print which files would be scored, then exit.")
    return parser.parse_args()


def load_openai_key(key_file: Path, env_file: Path) -> str:
    if key_file.exists():
        k = key_file.read_text(encoding="utf-8").strip()
        if k:
            return k
    load_env_file(env_file)
    return os.environ.get("OPENAI_API_KEY", "").strip()


def _derive_refused(row: dict, scores: dict) -> bool:
    """Heuristic: did the model effectively not rewrite anything?

    True when any of:
      - exact_match is True (anchor returned unchanged)
      - generation_status is a failure mode
      - strategy is inventory_greedy and applied_features is an empty list
    """
    if scores.get("exact_match"):
        return True
    status = row.get("generation_status")
    if status in {"model_fail", "parse_error", "api_error"}:
        return True
    if row.get("strategy") == "inventory_greedy":
        applied = row.get("applied_features")
        if isinstance(applied, list) and len(applied) == 0:
            return True
    return False


def output_path_for(input_path: Path, suffix: str | None) -> Path:
    if not suffix:
        return input_path
    stem = input_path.with_suffix("").name
    return input_path.parent / f"{stem}.{suffix}.jsonl"


def attribution_from_filename(input_path: Path) -> dict:
    """Parse `<strategy>__<model>__<family>.jsonl` into a dict. Returns {} on non-matching names."""
    stem = input_path.stem  # e.g. naive__gpt-4o__aae
    parts = stem.split("__")
    if len(parts) != 3:
        return {}
    strategy, model, family = parts
    prompt_path = prompt_path_for(strategy, family)
    return {
        "strategy": strategy,
        "model": model,
        "dialect_family": family,
        "dialect_title": FAMILY_TITLES.get(family, family),
        "prompt_path": prompt_path,
        "prompt_name": Path(prompt_path).stem if prompt_path else "",
    }


def backfill_attribution(row: dict, defaults: dict) -> None:
    """Fill in any missing attribution fields (strategy / model / family / prompt_path) from filename-derived defaults.
    Existing values are preserved — only blanks get filled."""
    for key, value in defaults.items():
        if row.get(key) in (None, "", []):
            row[key] = value


def main() -> None:
    args = parse_args()
    embedders = [e.strip() for e in args.embedders.split(",") if e.strip()]
    for e in embedders:
        if e not in {"openai", "hf"}:
            raise SystemExit(f"Unknown embedder {e!r}. Valid: openai, hf.")

    files = sorted(Path(p) for p in glob.glob(args.input))
    if not files:
        raise SystemExit(f"No files matched {args.input!r}.")

    print(f"Found {len(files)} file(s) matching {args.input!r}.")
    print(f"Embedders: {embedders if embedders else '(none — cheap tier only)'}")
    if args.dry_run:
        for f in files:
            print(f"  would score: {f}")
        return

    openai_key = ""
    if "openai" in embedders:
        openai_key = load_openai_key(args.key_file, args.env_file)
        if not openai_key:
            raise SystemExit(
                "OpenAI embedder requested but no key found in --key-file or OPENAI_API_KEY."
            )

    for input_path in files:
        rows = read_jsonl(input_path)
        if not rows:
            print(f"[skip] {input_path} is empty")
            continue

        # Backfill attribution fields (strategy / model / family / prompt_path / dialect_title)
        # from the filename for legacy records that predate those schema fields.
        defaults = attribution_from_filename(input_path)
        for row in rows:
            backfill_attribution(row, defaults)

        # Collect pairs that need embedding (status=ok, both texts non-empty).
        pairs: list[tuple[int, str, str]] = []
        for idx, row in enumerate(rows):
            anchor = str(row.get("anchor_text", "") or "")
            rewrite = str(row.get("rewrite_text", "") or "")
            pairs.append((idx, anchor, rewrite))

        # Cheap scores + derived top-level fields for every record.
        for idx, anchor, rewrite in pairs:
            scores = cheap_scores(anchor, rewrite)
            existing = rows[idx].get("similarity_scores") or {}
            existing.update(scores)
            rows[idx]["similarity_scores"] = existing

            # Derived top-level convenience fields.
            rows[idx]["anchor_word_count"] = len(anchor.split())
            rows[idx]["rewrite_word_count"] = len(rewrite.split())
            rows[idx]["composite_change_score"] = round(1 - scores["difflib_ratio"], 4)
            rows[idx]["refused"] = _derive_refused(rows[idx], scores)

        # Optional embedder passes. Only embed records that have non-empty texts
        # to avoid spurious API costs / encoder errors on empty strings.
        embeddable = [(idx, a, r) for idx, a, r in pairs if a.strip() and r.strip()]
        if embedders and embeddable:
            text_pairs = [(a, r) for _, a, r in embeddable]
            if "openai" in embedders:
                print(f"[{input_path.name}] OpenAI embedder over {len(text_pairs)} pair(s)…")
                cosines = openai_cosines(
                    text_pairs,
                    model=args.openai_embedding_model,
                    api_key=openai_key,
                    batch_size=args.openai_batch_size,
                )
                key = f"openai/{args.openai_embedding_model}"
                for (idx, _, _), value in zip(embeddable, cosines):
                    bucket = rows[idx]["similarity_scores"].setdefault("cosine_embeddings", {})
                    bucket[key] = value
            if "hf" in embedders:
                print(f"[{input_path.name}] HF embedder over {len(text_pairs)} pair(s)…")
                cosines = hf_cosines(text_pairs, model_name=args.hf_embedding_model)
                key = f"hf/{args.hf_embedding_model.split('/')[-1]}"
                for (idx, _, _), value in zip(embeddable, cosines):
                    bucket = rows[idx]["similarity_scores"].setdefault("cosine_embeddings", {})
                    bucket[key] = value

        out_path = output_path_for(input_path, args.output_suffix)
        write_jsonl(out_path, rows)
        # Surface the per-file attribution so the scored output stays easy to skim.
        first = rows[0]
        print(
            f"[ok]   wrote {len(rows)} scored record(s) to {out_path}\n"
            f"        strategy={first.get('strategy','?')}  model={first.get('model','?')}  "
            f"family={first.get('dialect_family','?')}  prompt_path={first.get('prompt_path','?')}"
        )


if __name__ == "__main__":
    main()
