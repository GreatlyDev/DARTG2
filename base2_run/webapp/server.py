"""FastAPI webapp for visualizing the base2 sweep results.

Routes:
  /                       — overview + per-family stats (single-page UI)
  /api/dataset            — metadata about the loaded file
  /api/stats/overall      — aggregated stats across all records
  /api/stats/families     — per-family breakdown
  /api/records            — full record list (lean fields for table/filters)
  /api/record/{record_id} — single record (full fields) with diff HTML
  /api/prompts            — list available prompts & inventories with markdown
  /api/download.{fmt}     — download the filtered set as csv or jsonl
                            (filters supplied via query string)
Run:
    cd base2_run/webapp && python3 server.py
or  uvicorn webapp.server:app --reload  (from base2_run/)
"""

from __future__ import annotations

import csv
import difflib
import hashlib
import io
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

WEBAPP_DIR = Path(__file__).resolve().parent
BASE2_DIR = WEBAPP_DIR.parent
REPO_ROOT = BASE2_DIR.parent
DEFAULT_DATASET = BASE2_DIR / "output" / "base2__claude-sonnet-4-6__all.jsonl"
# Directories scanned by /api/datasets. Loads are restricted to these roots
# (resolved + path-prefix check) so a malicious /api/load body can't read
# arbitrary files off disk.
DATASET_ROOTS: list[Path] = [
    BASE2_DIR / "output",
]

sys.path.insert(0, str(BASE2_DIR))
from lib.strategies import (  # noqa: E402
    FAMILY_INVENTORY_FILE,
    FAMILY_TITLES,
    PROMPT_PATH,
    PROMPT_VERSION,
    build_input,
    load_inventory,
)

app = FastAPI(title="base2 sweep viewer")
app.mount("/static", StaticFiles(directory=str(WEBAPP_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(WEBAPP_DIR / "templates"))


# ─────────────────────────── data loading ───────────────────────────


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _build_record_index(records: list[dict]) -> dict[str, int]:
    return {r["record_id"]: i for i, r in enumerate(records)}


RECORDS: list[dict] = []
RECORD_INDEX: dict[str, int] = {}
# BASE2_STARTUP_DATASET lets the __main__ block pass a startup dataset across
# the uvicorn re-import boundary (uvicorn.run("server:app") imports this
# module afresh in the worker, which would otherwise re-fire the module-level
# reload_dataset() and stomp the CLI choice).
_STARTUP_DATASET_ENV = "BASE2_STARTUP_DATASET"
_startup_override = os.environ.get(_STARTUP_DATASET_ENV)
DATASET_PATH: Path = Path(_startup_override) if _startup_override else DEFAULT_DATASET


def reload_dataset(path: Path | None = None) -> None:
    global RECORDS, RECORD_INDEX, DATASET_PATH
    if path:
        DATASET_PATH = Path(path)
    elif _startup_override:
        DATASET_PATH = Path(_startup_override)
    else:
        DATASET_PATH = DEFAULT_DATASET
    if not DATASET_PATH.exists():
        RECORDS = []
        RECORD_INDEX = {}
        return
    RECORDS = _load_jsonl(DATASET_PATH)
    RECORD_INDEX = _build_record_index(RECORDS)


def _resolve_under_roots(raw: str) -> Path:
    """Resolve `raw` to an absolute path and require it to live under one of
    DATASET_ROOTS. Raises HTTPException(400/404) otherwise."""
    if not raw:
        raise HTTPException(status_code=400, detail="path is required")
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        # Permit names relative to any configured root, first match wins.
        for root in DATASET_ROOTS:
            trial = (root / raw).resolve()
            if trial.exists():
                candidate = trial
                break
        else:
            raise HTTPException(status_code=404, detail=f"no dataset found at {raw!r}")
    else:
        candidate = candidate.resolve()
    for root in DATASET_ROOTS:
        try:
            candidate.relative_to(root.resolve())
            break
        except ValueError:
            continue
    else:
        roots = ", ".join(str(r) for r in DATASET_ROOTS)
        raise HTTPException(status_code=400,
                            detail=f"path is outside allowed dataset roots: {roots}")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail=f"dataset not found: {candidate}")
    if candidate.suffix.lower() != ".jsonl":
        raise HTTPException(status_code=400, detail="only .jsonl files are loadable")
    return candidate


def _scan_dataset_roots() -> list[dict]:
    """Return every *.jsonl under DATASET_ROOTS as {label, path, size_bytes, mtime}.
    Sorted by mtime (newest first) so fresh runs surface at the top."""
    out: list[dict] = []
    seen: set[Path] = set()
    for root in DATASET_ROOTS:
        if not root.exists():
            continue
        for path in root.glob("*.jsonl"):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            stat = resolved.stat()
            try:
                rel = resolved.relative_to(REPO_ROOT)
            except ValueError:
                rel = resolved
            out.append({
                "name": resolved.name,
                "path": str(resolved),
                "rel_path": str(rel),
                "size_bytes": stat.st_size,
                "mtime_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "is_current": resolved == DATASET_PATH.resolve() if DATASET_PATH.exists() else False,
            })
    out.sort(key=lambda d: d["mtime_utc"], reverse=True)
    return out


reload_dataset()


# ────────────────────────── stats helpers ──────────────────────────


def _median(values: Iterable[float | int | None]) -> float | None:
    nums = sorted(float(v) for v in values if v is not None)
    if not nums:
        return None
    mid = len(nums) // 2
    if len(nums) % 2 == 1:
        return nums[mid]
    return (nums[mid - 1] + nums[mid]) / 2


def _mean(values: Iterable[float | int | None]) -> float | None:
    nums = [float(v) for v in values if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def _cosine_for(row: dict) -> float | None:
    cos = row.get("cosine_similarity")
    if cos is None or cos == -1:
        return None
    return float(cos)


def _aggregate(rows: list[dict]) -> dict:
    """Aggregate the metrics that matter most for an overall or per-family view."""
    if not rows:
        return {"records": 0}
    ok = [r for r in rows if r.get("generation_status") == "ok"]
    statuses = {}
    for r in rows:
        statuses[r.get("generation_status", "?")] = statuses.get(r.get("generation_status", "?"), 0) + 1

    feat_counts = [r.get("applied_feature_count") or 0 for r in ok]
    token_change = [r.get("similarity_scores", {}).get("token_change_ratio") for r in ok]
    cosines = [_cosine_for(r) for r in ok]
    grounding = [r.get("feature_realization", {}).get("rate") for r in ok]
    new_hits = [r.get("inventory_pattern_hits", {}).get("count_new") or 0 for r in ok]
    passes = [r.get("dialect_pass") for r in ok if r.get("dialect_pass") is not None]
    pass_rate = (sum(1 for p in passes if p) / len(passes)) if passes else None
    refused = sum(1 for r in rows if r.get("refused"))
    attempts = [r.get("attempts") or 1 for r in rows]
    multi_attempt = sum(1 for a in attempts if a > 1)

    return {
        "records": len(rows),
        "ok": len(ok),
        "ok_rate": round(len(ok) / len(rows), 4) if rows else None,
        "statuses": statuses,
        "median_feature_count": _median(feat_counts),
        "mean_feature_count": _mean(feat_counts),
        "median_token_change_pct": (round(100 * _median(token_change), 2)
                                    if token_change and _median(token_change) is not None else None),
        "mean_token_change_pct": (round(100 * _mean(token_change), 2)
                                  if token_change and _mean(token_change) is not None else None),
        "median_cosine": (round(_median(cosines), 4) if _median(cosines) is not None else None),
        "mean_cosine": (round(_mean(cosines), 4) if _mean(cosines) is not None else None),
        "dialect_pass_rate": round(pass_rate, 4) if pass_rate is not None else None,
        "median_grounding_rate": (round(_median(grounding), 4) if _median(grounding) is not None else None),
        "median_new_inventory_hits": _median(new_hits),
        "refused_count": refused,
        "multi_attempt_count": multi_attempt,
        "tokens_in_total": sum(int(r.get("tokens_in") or 0) for r in rows),
        "tokens_out_total": sum(int(r.get("tokens_out") or 0) for r in rows),
        "cost_usd_total": round(sum(float(r.get("cost_usd") or 0) for r in rows), 4),
    }


# ───────────────────────── filter parsing ─────────────────────────


def _passes_filters(row: dict, *, family: list[str] | None, status: list[str] | None,
                     dialect_pass: str | None, min_token_change: float | None,
                     max_token_change: float | None, min_cosine: float | None,
                     max_cosine: float | None, min_feature_count: int | None,
                     refused: str | None, search: str | None) -> bool:
    if family and row.get("dialect_family") not in family:
        return False
    if status and row.get("generation_status") not in status:
        return False
    if dialect_pass and dialect_pass != "any":
        want = {"true": True, "false": False, "none": None}.get(dialect_pass)
        if row.get("dialect_pass") is not want:
            return False
    tcr = row.get("similarity_scores", {}).get("token_change_ratio")
    if min_token_change is not None and (tcr is None or tcr < min_token_change):
        return False
    if max_token_change is not None and (tcr is None or tcr > max_token_change):
        return False
    cos = _cosine_for(row)
    if min_cosine is not None and (cos is None or cos < min_cosine):
        return False
    if max_cosine is not None and (cos is None or cos > max_cosine):
        return False
    if min_feature_count is not None and (row.get("applied_feature_count") or 0) < min_feature_count:
        return False
    if refused and refused != "any":
        want = refused == "true"
        if bool(row.get("refused")) is not want:
            return False
    if search:
        hay = " ".join([
            str(row.get("anchor_text", "")),
            str(row.get("rewrite_text", "")),
            str(row.get("anchor_id", "")),
        ]).lower()
        if search.lower() not in hay:
            return False
    return True


def _split_csv_param(value: str | None) -> list[str] | None:
    if not value:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return parts or None


def _lean_record(row: dict) -> dict:
    """Trimmed record for the table view — drops raw_output and other heavy fields."""
    return {
        "record_id": row.get("record_id"),
        "anchor_id": row.get("anchor_id"),
        "dialect_family": row.get("dialect_family"),
        "dialect_title": row.get("dialect_title"),
        "generation_status": row.get("generation_status"),
        "attempts": row.get("attempts"),
        "anchor_word_count": row.get("anchor_word_count"),
        "rewrite_word_count": row.get("rewrite_word_count"),
        "length_band": row.get("length_band"),
        "score_band": (row.get("anchor_extras") or {}).get("score_band"),
        "tokens_changed_absolute": row.get("tokens_changed_absolute"),
        "min_change_budget_words": row.get("min_change_budget_words"),
        "max_change_budget_words": row.get("max_change_budget_words"),
        "feature_density_per_100w": row.get("feature_density_per_100w"),
        "applied_feature_count": row.get("applied_feature_count"),
        "declared_feature_count": row.get("declared_feature_count"),
        "token_change_ratio": row.get("similarity_scores", {}).get("token_change_ratio"),
        "difflib_ratio": row.get("similarity_scores", {}).get("difflib_ratio"),
        "cosine_similarity": row.get("cosine_similarity"),
        "dialect_pass": row.get("dialect_pass"),
        "feature_realization_rate": row.get("feature_realization", {}).get("rate"),
        "new_inventory_hits": row.get("inventory_pattern_hits", {}).get("count_new"),
        "refused": row.get("refused"),
        "cost_usd": row.get("cost_usd"),
        "tokens_in": row.get("tokens_in"),
        "tokens_out": row.get("tokens_out"),
        "anchor_preview": (str(row.get("anchor_text", ""))[:200]),
        "rewrite_preview": (str(row.get("rewrite_text", ""))[:200]),
    }


# ──────────────────────── diff HTML builder ────────────────────────


_WORD_SPLIT_RE = re.compile(r"(\s+|[^\w\s']+)")


def _tokenize_for_diff(text: str) -> list[str]:
    """Split into a list of tokens that preserves whitespace and punctuation so
    we can re-emit the original spacing/punctuation when rendering the diff."""
    parts = _WORD_SPLIT_RE.split(text)
    return [p for p in parts if p != ""]


def _escape_html(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                 .replace('"', "&quot;").replace("'", "&#39;"))


def _diff_html(anchor: str, rewrite: str) -> dict:
    """Produce HTML for anchor and rewrite with word-level diff classes.

    anchor_html: kept words get class="kept", words removed (in anchor only) get class="del".
    rewrite_html: kept words get class="kept", words added (in rewrite only) get class="add".
    """
    a_tokens = _tokenize_for_diff(anchor)
    r_tokens = _tokenize_for_diff(rewrite)
    matcher = difflib.SequenceMatcher(a=a_tokens, b=r_tokens, autojunk=False)
    anchor_pieces: list[str] = []
    rewrite_pieces: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        a_chunk = "".join(a_tokens[i1:i2])
        b_chunk = "".join(r_tokens[j1:j2])
        if tag == "equal":
            anchor_pieces.append(f'<span class="kept">{_escape_html(a_chunk)}</span>')
            rewrite_pieces.append(f'<span class="kept">{_escape_html(b_chunk)}</span>')
        elif tag == "delete":
            anchor_pieces.append(f'<span class="del">{_escape_html(a_chunk)}</span>')
        elif tag == "insert":
            rewrite_pieces.append(f'<span class="add">{_escape_html(b_chunk)}</span>')
        elif tag == "replace":
            anchor_pieces.append(f'<span class="del">{_escape_html(a_chunk)}</span>')
            rewrite_pieces.append(f'<span class="add">{_escape_html(b_chunk)}</span>')
    return {"anchor_html": "".join(anchor_pieces), "rewrite_html": "".join(rewrite_pieces)}


# ──────────────────────────── routes ────────────────────────────


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> Any:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "dataset_name": DATASET_PATH.name if DATASET_PATH.exists() else "(missing)",
            "record_count": len(RECORDS),
            "families": sorted(FAMILY_TITLES),
        },
    )


@app.get("/api/dataset")
def api_dataset() -> dict:
    return {
        "path": str(DATASET_PATH),
        "name": DATASET_PATH.name,
        "exists": DATASET_PATH.exists(),
        "records": len(RECORDS),
        "families": {fam: FAMILY_TITLES[fam] for fam in sorted(FAMILY_TITLES)},
        "model": RECORDS[0].get("model") if RECORDS else None,
        "strategy": RECORDS[0].get("strategy") if RECORDS else None,
        "prompt_version": RECORDS[0].get("prompt_version") if RECORDS else None,
        "run_id": RECORDS[0].get("run_id") if RECORDS else None,
    }


@app.get("/api/datasets")
def api_datasets() -> dict:
    """List every .jsonl under DATASET_ROOTS that the UI can swap to."""
    return {
        "current": str(DATASET_PATH),
        "current_name": DATASET_PATH.name,
        "roots": [str(r) for r in DATASET_ROOTS],
        "datasets": _scan_dataset_roots(),
    }


@app.post("/api/load")
def api_load(payload: dict = Body(...)) -> dict:
    """Swap the in-memory dataset. Body: {"path": "..."} — accepts an absolute
    path, a path relative to one of the dataset roots, or a bare filename
    matched against the roots."""
    raw = (payload or {}).get("path") or (payload or {}).get("name") or ""
    path = _resolve_under_roots(str(raw))
    reload_dataset(path)
    return {
        "loaded": str(DATASET_PATH),
        "name": DATASET_PATH.name,
        "records": len(RECORDS),
        "model": RECORDS[0].get("model") if RECORDS else None,
        "strategy": RECORDS[0].get("strategy") if RECORDS else None,
    }


@app.get("/api/stats/overall")
def api_stats_overall() -> dict:
    return _aggregate(RECORDS)


@app.get("/api/stats/distributions")
def api_stats_distributions() -> dict:
    """Raw arrays for client-side histogram rendering."""
    cosines: list[float] = []
    token_change: list[float] = []
    feature_counts: list[int] = []
    grounding: list[float] = []
    new_hits: list[int] = []
    family_pass: dict[str, dict] = {}
    family_cosine: dict[str, list[float]] = {}
    family_tcr: dict[str, list[float]] = {}
    family_feat: dict[str, list[int]] = {}
    for r in RECORDS:
        if r.get("generation_status") != "ok":
            continue
        cos = _cosine_for(r)
        if cos is not None:
            cosines.append(cos)
        tcr = r.get("similarity_scores", {}).get("token_change_ratio")
        if tcr is not None:
            token_change.append(float(tcr))
        feature_counts.append(int(r.get("applied_feature_count") or 0))
        gr = r.get("feature_realization", {}).get("rate")
        if gr is not None:
            grounding.append(float(gr))
        nh = r.get("inventory_pattern_hits", {}).get("count_new")
        if nh is not None:
            new_hits.append(int(nh))
        fam = r.get("dialect_family", "?")
        family_pass.setdefault(fam, {"pass": 0, "fail": 0, "uncomputed": 0})
        if r.get("dialect_pass") is True:
            family_pass[fam]["pass"] += 1
        elif r.get("dialect_pass") is False:
            family_pass[fam]["fail"] += 1
        else:
            family_pass[fam]["uncomputed"] += 1
        if cos is not None:
            family_cosine.setdefault(fam, []).append(cos)
        if tcr is not None:
            family_tcr.setdefault(fam, []).append(float(tcr))
        family_feat.setdefault(fam, []).append(int(r.get("applied_feature_count") or 0))

    return {
        "cosine": cosines,
        "token_change": token_change,
        "feature_counts": feature_counts,
        "grounding": grounding,
        "new_inventory_hits": new_hits,
        "family_pass": family_pass,
        "family_cosine_medians": {fam: round(_median(vs), 4) for fam, vs in family_cosine.items()},
        "family_token_change_medians": {fam: round(_median(vs), 4) for fam, vs in family_tcr.items()},
        "family_feature_count_medians": {fam: round(_median(vs), 2) for fam, vs in family_feat.items()},
    }


# ─────────────── anchor-length / score-band analysis ───────────────
# Background: anchors are 50–150 words. A 5–25% token-change band is a tiny
# absolute budget on short anchors and a generous one on long anchors. These
# endpoints expose pass-rate / token-change behavior grouped by length band
# (short ≤60, medium 61–120, long >120) and by score band (LOW/MID/HIGH).
# See lib/similarity.py:length_band.


_LENGTH_BAND_ORDER = ("short", "medium", "long", "unknown")


def _group_aggregate(rows: list[dict], key_fn) -> dict:
    """Group OK rows by key_fn(row) and aggregate the metrics we need
    for the length / score-band tables and bars."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("generation_status") != "ok":
            continue
        groups.setdefault(key_fn(r) or "unknown", []).append(r)

    out: dict[str, dict] = {}
    for key, rs in groups.items():
        passes = [r.get("dialect_pass") for r in rs if r.get("dialect_pass") is not None]
        pass_rate = (sum(1 for p in passes if p) / len(passes)) if passes else None
        tcrs = [r.get("similarity_scores", {}).get("token_change_ratio") for r in rs
                if r.get("similarity_scores", {}).get("token_change_ratio") is not None]
        anchor_words = [r.get("anchor_word_count") for r in rs if r.get("anchor_word_count")]
        tokens_changed = [r.get("tokens_changed_absolute") for r in rs
                           if r.get("tokens_changed_absolute") is not None]
        feats = [r.get("applied_feature_count") or 0 for r in rs]
        cosines = [_cosine_for(r) for r in rs]
        density = [r.get("feature_density_per_100w") for r in rs
                   if r.get("feature_density_per_100w") is not None]
        out[key] = {
            "n": len(rs),
            "dialect_pass_rate":      round(pass_rate, 4) if pass_rate is not None else None,
            "median_anchor_words":    _median(anchor_words),
            "median_tokens_changed":  _median(tokens_changed),
            "median_token_change_pct": (round(100 * _median(tcrs), 2)
                                         if _median(tcrs) is not None else None),
            "median_feature_count":   _median(feats),
            "median_cosine":          (round(_median(cosines), 4)
                                       if _median(cosines) is not None else None),
            "median_feature_density_per_100w": (round(_median(density), 2)
                                                 if _median(density) is not None else None),
        }
    return out


def _length_band_sort_key(key: str) -> tuple[int, str]:
    try:
        return (_LENGTH_BAND_ORDER.index(key), key)
    except ValueError:
        return (len(_LENGTH_BAND_ORDER), key)


@app.get("/api/stats/length_bands")
def api_stats_length_bands() -> dict:
    """Pass-rate / token-change / feature-count medians grouped by:
    - length_band (short / medium / long)
    - score_band (LOW / MID / HIGH; from anchor_extras.score_band)"""
    by_length = _group_aggregate(RECORDS, lambda r: r.get("length_band"))
    # Stable sort by short/medium/long ordering for the UI.
    by_length_ordered = dict(sorted(by_length.items(), key=lambda kv: _length_band_sort_key(kv[0])))

    by_score = _group_aggregate(RECORDS, lambda r: (r.get("anchor_extras") or {}).get("score_band"))
    by_score_ordered = dict(sorted(by_score.items()))
    return {"by_length": by_length_ordered, "by_score": by_score_ordered}


@app.get("/api/stats/length_scatter")
def api_stats_length_scatter() -> dict:
    """Slim per-record array for the scatter chart on the Anchor-length tab.
    Only OK records are included."""
    points: list[dict] = []
    for r in RECORDS:
        if r.get("generation_status") != "ok":
            continue
        wc = r.get("anchor_word_count")
        tcr = r.get("similarity_scores", {}).get("token_change_ratio")
        if wc is None or tcr is None:
            continue
        points.append({
            "record_id": r.get("record_id"),
            "anchor_word_count": wc,
            "token_change_pct": round(float(tcr) * 100, 3),
            "dialect_pass": r.get("dialect_pass"),
            "length_band": r.get("length_band"),
            "score_band": (r.get("anchor_extras") or {}).get("score_band"),
            "dialect_family": r.get("dialect_family"),
            "applied_feature_count": r.get("applied_feature_count"),
        })
    return {"points": points, "band": {"low": 5.0, "high": 25.0}}


@app.get("/api/stats/families")
def api_stats_families() -> dict:
    out: dict[str, dict] = {}
    for fam in sorted(FAMILY_TITLES):
        out[fam] = {"title": FAMILY_TITLES[fam], **_aggregate([r for r in RECORDS
                                                                if r.get("dialect_family") == fam])}
    return out


@app.get("/api/records")
def api_records(
    family: Optional[str] = None,
    status: Optional[str] = None,
    dialect_pass: Optional[str] = None,
    min_token_change: Optional[float] = None,
    max_token_change: Optional[float] = None,
    min_cosine: Optional[float] = None,
    max_cosine: Optional[float] = None,
    min_feature_count: Optional[int] = None,
    refused: Optional[str] = None,
    search: Optional[str] = None,
) -> dict:
    fams = _split_csv_param(family)
    statuses = _split_csv_param(status)
    filtered = [r for r in RECORDS if _passes_filters(
        r, family=fams, status=statuses, dialect_pass=dialect_pass,
        min_token_change=min_token_change, max_token_change=max_token_change,
        min_cosine=min_cosine, max_cosine=max_cosine,
        min_feature_count=min_feature_count, refused=refused, search=search,
    )]
    return {"count": len(filtered), "records": [_lean_record(r) for r in filtered]}


@app.get("/api/record/{record_id}")
def api_record_detail(record_id: str) -> dict:
    idx = RECORD_INDEX.get(record_id)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"record {record_id} not found")
    row = RECORDS[idx]
    diff = _diff_html(str(row.get("anchor_text") or ""), str(row.get("rewrite_text") or ""))
    return {"record": row, "diff": diff, "neighbors": _neighbors(idx)}


def _neighbors(idx: int) -> dict:
    """Return prev / next ids both globally and within-family for the carousel."""
    family = RECORDS[idx].get("dialect_family")
    same_family = [i for i, r in enumerate(RECORDS) if r.get("dialect_family") == family]
    pos_in_family = same_family.index(idx) if idx in same_family else 0
    return {
        "global_prev": RECORDS[idx - 1]["record_id"] if idx > 0 else None,
        "global_next": RECORDS[idx + 1]["record_id"] if idx + 1 < len(RECORDS) else None,
        "family_prev": (RECORDS[same_family[pos_in_family - 1]]["record_id"]
                        if pos_in_family > 0 else None),
        "family_next": (RECORDS[same_family[pos_in_family + 1]]["record_id"]
                        if pos_in_family + 1 < len(same_family) else None),
        "family_index": pos_in_family,
        "family_total": len(same_family),
        "global_index": idx,
        "global_total": len(RECORDS),
    }


@app.get("/api/records/random")
def api_record_random(family: Optional[str] = None) -> dict:
    import random as _r
    pool = ([r for r in RECORDS if r.get("dialect_family") == family]
            if family else RECORDS)
    if not pool:
        raise HTTPException(status_code=404, detail="no records to pick from")
    pick = _r.choice(pool)
    return {"record_id": pick["record_id"]}


# Human-readable replacements for template placeholders. The raw template has
# tokens like `{ANCHOR_RESPONSE}` — we substitute these in the UI so the
# template is readable without showing variable names with underscores.
_TEMPLATE_PLACEHOLDER_HUMAN: dict[str, str] = {
    "{PROMPT}":                       "[prompt context — provided by caller]",
    "{ANCHOR_RESPONSE}":              "[the student's anchor essay]",
    "{DIALECT_FAMILY}":               "[target dialect name]",
    "{FEATURE_INVENTORY}":            "[allowed feature inventory for the family]",
    "{DISALLOWED_FEATURES_AND_NOTES}":"[disallowed features and safety notes]",
}


def _humanize_template(template: str) -> str:
    text = template
    for raw, human in _TEMPLATE_PLACEHOLDER_HUMAN.items():
        text = text.replace(raw, human)
    return text


def _render_actual_prompt(family: str) -> str:
    """Fully rendered prompt as the model actually saw it for that family —
    BYTE-FAITHFUL to what `run_base2.py` sent at generation time, except for
    the per-record anchor text. Uses the exact same `build_input()` function
    that the runner used, reading the same `prompts/base2.md` and the same
    `config/features/<family>.json` files on disk.

    The only substitution is the anchor placeholder, because the anchor varies
    per record. Every other token (including the literal `[PROMPT NOT PROVIDED]`
    string that build_input injects for the absent `{PROMPT}` arg) is preserved
    exactly as the model saw it."""
    inventory = load_inventory(family)
    return build_input(
        anchor_text="[the per-record anchor essay — actual text varies; view any specific anchor in the Reader tab]",
        family_title=FAMILY_TITLES[family],
        inventory=inventory,
    )


def _file_provenance(path: Path) -> dict:
    """Return source-file metadata for the provenance header on each prompt
    view: relative path, modification time, raw byte SHA-256."""
    if not path.exists():
        return {"path": str(path), "exists": False}
    raw = path.read_bytes()
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
    return {
        "path": str(path.relative_to(BASE2_DIR)),
        "exists": True,
        "mtime_utc": mtime,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
    }


def _records_use_this_prompt_version() -> dict:
    """How many records reference the current PROMPT_VERSION? Used to flag
    drift between the file on disk and the version recorded in the JSONL."""
    if not RECORDS:
        return {"records_total": 0, "matching_prompt_version": 0, "current_version": PROMPT_VERSION,
                "in_sync": True}
    versions = [r.get("prompt_version") for r in RECORDS]
    matches = sum(1 for v in versions if v == PROMPT_VERSION)
    return {
        "records_total": len(RECORDS),
        "matching_prompt_version": matches,
        "current_version": PROMPT_VERSION,
        "recorded_versions": sorted(set(v for v in versions if v)),
        "in_sync": matches == len(RECORDS),
    }


@app.get("/api/prompts")
def api_prompts() -> dict:
    out: list[dict] = []
    version_check = _records_use_this_prompt_version()
    # 1. Template (with human-readable placeholders).
    prompt_path = BASE2_DIR / "prompts" / "base2.md"
    if prompt_path.exists():
        raw = prompt_path.read_text(encoding="utf-8")
        template_prov = _file_provenance(prompt_path)
        out.append({
            "name": "base2 (template)",
            "kind": "template",
            "path": template_prov["path"],
            "provenance": template_prov,
            "version_check": version_check,
            "markdown": _humanize_template(raw),
            "raw_markdown": raw,  # also shippable so the user can verify byte-for-byte
        })
    # 2. Fully-rendered prompt per family — what the model actually saw.
    inv_dir = BASE2_DIR / "config" / "features"
    for fam in sorted(FAMILY_TITLES):
        try:
            rendered = _render_actual_prompt(fam)
            error = None
        except Exception as exc:
            rendered = ""
            error = f"failed to render: {exc}"
        inv_path = inv_dir / FAMILY_INVENTORY_FILE[fam]
        out.append({
            "name": f"{fam} (rendered)",
            "kind": "rendered",
            "family": fam,
            "title": FAMILY_TITLES[fam],
            "markdown": rendered,
            "error": error,
            "provenance": {
                "template": _file_provenance(prompt_path),
                "inventory": _file_provenance(inv_path),
                "build_input_function": "lib.strategies.build_input",
                "rendered_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest() if rendered else None,
                "prompt_version": PROMPT_VERSION,
                "note": (
                    "Byte-faithful to the prompt sent to the model at generation time, "
                    "except for the per-record anchor text (the only call-time variable)."
                ),
            },
            "version_check": version_check,
        })
    # 3. Each family inventory as a structured markdown view.
    for fam, fname in sorted({
        "aae":          "aae.json",
        "southern":     "southern.json",
        "appalachian":  "appalachian.json",
        "midwestern":   "midwestern_north_central.json",
        "northeastern": "northeastern_new_england.json",
        "western":      "western.json",
    }.items()):
        path = inv_dir / fname
        if not path.exists():
            continue
        out.append({
            "name": f"{fam} (inventory)",
            "kind": "inventory",
            "family": fam,
            "title": FAMILY_TITLES[fam],
            "path": str(path.relative_to(BASE2_DIR)),
            "provenance": _file_provenance(path),
            "markdown": _inventory_to_markdown(json.loads(path.read_text(encoding="utf-8"))),
        })
    return {"items": out, "version_check": version_check}


def _inventory_to_markdown(inv: dict) -> str:
    lines = []
    lines.append(f"# {inv.get('dialect_family', 'Inventory')}")
    if inv.get("review_status"):
        lines.append(f"*review status: {inv['review_status']}*")
    if inv.get("primary_references"):
        lines.append("\n**Primary references**")
        for ref in inv["primary_references"]:
            lines.append(f"- {ref}")
    by_cat: dict[str, list[dict]] = {}
    for feat in inv.get("features", []):
        by_cat.setdefault(feat.get("category", "other"), []).append(feat)
    for cat, feats in by_cat.items():
        lines.append(f"\n## {cat.capitalize()} features")
        for f in feats:
            allow = "" if f.get("allowed_for_generation") else "  _disallowed_"
            risk = f.get("risk_level") or ""
            risk_tag = f" `risk: {risk}`" if risk else ""
            line = f"- **{f.get('feature', f.get('id', ''))}**{allow}{risk_tag}"
            if f.get("description"):
                line += f" — {f['description']}"
            lines.append(line)
            if f.get("safe_example"):
                lines.append(f"  - example: _{f['safe_example']}_")
            if f.get("blocked_context"):
                lines.append(f"  - avoid: {f['blocked_context']}")
    if inv.get("disallowed_features"):
        lines.append("\n## Disallowed")
        for d in inv["disallowed_features"]:
            lines.append(f"- {d}")
    if inv.get("safety_notes"):
        lines.append("\n## Safety notes")
        for n in inv["safety_notes"]:
            lines.append(f"- {n}")
    return "\n".join(lines)


def _csv_iter(rows: list[dict]) -> Iterable[bytes]:
    """Stream CSV bytes for the download endpoint."""
    if not rows:
        yield b""
        return
    flat_rows = [_lean_record(r) for r in rows]
    fieldnames = list(flat_rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    yield buf.getvalue().encode("utf-8")
    buf.seek(0); buf.truncate()
    for r in flat_rows:
        writer.writerow(r)
        yield buf.getvalue().encode("utf-8")
        buf.seek(0); buf.truncate()


def _jsonl_iter(rows: list[dict]) -> Iterable[bytes]:
    for r in rows:
        yield (json.dumps(r, ensure_ascii=True) + "\n").encode("utf-8")


@app.get("/api/download.{fmt}")
def api_download(fmt: str, request: Request,
                 family: Optional[str] = None,
                 status: Optional[str] = None,
                 dialect_pass: Optional[str] = None,
                 min_token_change: Optional[float] = None,
                 max_token_change: Optional[float] = None,
                 min_cosine: Optional[float] = None,
                 max_cosine: Optional[float] = None,
                 min_feature_count: Optional[int] = None,
                 refused: Optional[str] = None,
                 search: Optional[str] = None,
                 full: bool = False) -> StreamingResponse:
    fams = _split_csv_param(family)
    statuses = _split_csv_param(status)
    filtered = [r for r in RECORDS if _passes_filters(
        r, family=fams, status=statuses, dialect_pass=dialect_pass,
        min_token_change=min_token_change, max_token_change=max_token_change,
        min_cosine=min_cosine, max_cosine=max_cosine,
        min_feature_count=min_feature_count, refused=refused, search=search,
    )]
    if fmt == "csv":
        return StreamingResponse(
            _csv_iter(filtered),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="base2_filtered.csv"'},
        )
    if fmt == "jsonl":
        rows = filtered if full else [_lean_record(r) for r in filtered]
        return StreamingResponse(
            _jsonl_iter(rows),
            media_type="application/x-ndjson",
            headers={"Content-Disposition": 'attachment; filename="base2_filtered.jsonl"'},
        )
    raise HTTPException(status_code=400, detail=f"unsupported format {fmt!r} (csv|jsonl)")


@app.get("/healthz", response_class=PlainTextResponse)
def healthz() -> str:
    return f"ok · {len(RECORDS)} records loaded from {DATASET_PATH.name}"


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="base2 sweep viewer")
    parser.add_argument("--dataset", type=Path, default=None,
                        help="JSONL file to load on startup (default: "
                             f"{DEFAULT_DATASET}). Can also be swapped at runtime "
                             "via the sidebar dropdown or POST /api/load.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--reload", action="store_true",
                        help="Enable uvicorn reload mode (dev only).")
    args = parser.parse_args()

    if args.dataset:
        path = args.dataset.expanduser().resolve()
        if not path.exists():
            raise SystemExit(f"--dataset path does not exist: {path}")
        # Stash in env so the module-level reload_dataset() in the freshly
        # re-imported worker process picks it up; reload it in this process
        # too so the boot-time log line is accurate.
        os.environ[_STARTUP_DATASET_ENV] = str(path)
        reload_dataset(path)
        print(f"Loaded {len(RECORDS)} records from {path}")

    uvicorn.run("server:app", host=args.host, port=args.port, reload=args.reload)
