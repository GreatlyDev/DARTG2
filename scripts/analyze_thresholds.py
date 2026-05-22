#!/usr/bin/env python3
"""
Evaluate generated records against dual criterion:

1. Token-change percentage targets (Levin-style):
   - PASSABLE:  5%  <= change% < 10%
   - PREFERRED: 10% <= change% <= 20%  (sweet spot for short anchors)
   - HIGH:      20% < change% <= 25%   (acceptable upper bound)
   - OVER:      change% > 25%          (likely paraphrase / meaning drift)
   - UNDER:     change% < 5%           (basically unchanged)

2. Feature criterion (dialect strategy only):
   - SHORT anchor (<= 80 tokens):  >= 2 distinct feature realizations
   - LONG anchor  (> 80 tokens):   3..5 distinct feature realizations preferred

3. Semantic preservation: HF MiniLM cosine >= 0.85.

The script prints both per-(strategy, model) summary tables and a per-
(strategy, model, dialect_family) breakdown, plus a count of records that
meet every criterion in the dual rule.
"""
from __future__ import annotations

import argparse
import difflib
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from statistics import mean, median

GEN_DIR = "/Users/jonwhite/DART/DARTG2/data/generated"

TOKEN_RE = re.compile(r"\w+(?:'\w+)?|[^\w\s]", re.UNICODE)


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text or "")


def token_change_pct(anchor: str, rewrite: str) -> float:
    """Fraction of tokens that changed, via difflib on token lists.

    Computed as 1 - (2*matches) / (len(a) + len(b)). This is the standard
    difflib ratio applied to tokens (not characters). Returns a float in
    [0, 1]; multiply by 100 for percent.
    """
    a = tokens(anchor)
    b = tokens(rewrite)
    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    return 1.0 - sm.ratio()


def feature_count(applied) -> int:
    if not applied:
        return 0
    if isinstance(applied, list):
        return len(applied)
    return 0


def hf_cosine(sim_scores: dict) -> float | None:
    if not isinstance(sim_scores, dict):
        return None
    ce = sim_scores.get("cosine_embeddings")
    if not isinstance(ce, dict):
        return None
    # Real layout is a flat dict like {"hf/all-MiniLM-L6-v2": 0.94}
    for k, v in ce.items():
        if isinstance(v, (int, float)) and ("MiniLM" in k or "minilm" in k):
            return v
        if isinstance(v, dict):
            for k2, v2 in v.items():
                if isinstance(v2, (int, float)) and ("MiniLM" in k2 or "minilm" in k2):
                    return v2
    if ce:
        first = next(iter(ce.values()))
        return first if isinstance(first, (int, float)) else None
    return None


def bucket(pct: float) -> str:
    if pct < 0.05:
        return "UNDER"
    if pct < 0.10:
        return "PASS"
    if pct <= 0.20:
        return "PREF"
    if pct <= 0.25:
        return "HIGH"
    return "OVER"


def feature_ok(strategy: str, anchor_word_count: int, n_features: int) -> bool | None:
    """Return True/False if dual rule applies, None if not applicable (non-dialect)."""
    if strategy != "dialect":
        return None
    short = (anchor_word_count or 0) <= 80
    if short:
        return n_features >= 2
    return 3 <= n_features <= 5


def load_records():
    for path in sorted(glob.glob(os.path.join(GEN_DIR, "*.jsonl"))):
        fname = os.path.basename(path)
        # Skip winners aggregate
        if fname == "winners.jsonl":
            continue
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                yield rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="optional path to write per-record CSV")
    ap.add_argument("--top", type=int, default=10,
                    help="how many exemplar records to print per cohort")
    args = ap.parse_args()

    # Bucket counts: key = (strategy, model), value = Counter
    by_sm: dict[tuple[str, str], Counter] = defaultdict(Counter)
    by_smd: dict[tuple[str, str, str], Counter] = defaultdict(Counter)
    pct_samples: dict[tuple[str, str], list[float]] = defaultdict(list)
    sem_fail: dict[tuple[str, str], int] = defaultdict(int)
    feat_ok_count: dict[tuple[str, str], int] = defaultdict(int)
    feat_n_total: dict[tuple[str, str], int] = defaultdict(int)
    dual_pass: dict[tuple[str, str], int] = defaultdict(int)
    refused_or_bad: dict[tuple[str, str], int] = defaultdict(int)
    total: dict[tuple[str, str], int] = defaultdict(int)

    exemplars: dict[tuple[str, str], list] = defaultdict(list)
    per_record_rows = []

    for rec in load_records():
        strategy = rec.get("strategy", "?")
        model = rec.get("model", "?")
        family = rec.get("dialect_family", "?")
        key = (strategy, model)
        keyd = (strategy, model, family)
        total[key] += 1

        anchor = rec.get("anchor_text") or ""
        rewrite = rec.get("rewrite_text") or ""
        anchor_wc = rec.get("anchor_word_count") or len(tokens(anchor))
        status = rec.get("generation_status") or ""
        refused = bool(rec.get("refused"))

        usable = (status == "ok") and (not refused) and bool(rewrite.strip())
        if not usable:
            refused_or_bad[key] += 1
            by_sm[key]["BAD"] += 1
            by_smd[keyd]["BAD"] += 1
            continue

        pct = token_change_pct(anchor, rewrite)
        b = bucket(pct)
        by_sm[key][b] += 1
        by_smd[keyd][b] += 1
        pct_samples[key].append(pct)

        cos = hf_cosine(rec.get("similarity_scores") or {})
        sem_pass = (cos is None) or (cos >= 0.85)
        if not sem_pass:
            sem_fail[key] += 1

        nfeat = feature_count(rec.get("applied_features"))
        fok = feature_ok(strategy, anchor_wc, nfeat)
        if fok is True:
            feat_ok_count[key] += 1
        if strategy == "dialect":
            feat_n_total[key] += nfeat

        pct_ok = 0.05 <= pct <= 0.25
        if strategy == "dialect":
            if pct_ok and sem_pass and fok is True:
                dual_pass[key] += 1
        else:
            if pct_ok and sem_pass:
                dual_pass[key] += 1

        # Keep a few exemplars in the PREFERRED band
        if 0.10 <= pct <= 0.20 and sem_pass and len(exemplars[key]) < args.top:
            exemplars[key].append({
                "family": family,
                "anchor_id": rec.get("anchor_id"),
                "pct": pct,
                "cos": cos,
                "nfeat": nfeat,
                "anchor_wc": anchor_wc,
                "anchor": anchor[:120],
                "rewrite": rewrite[:120],
            })

        if args.csv:
            per_record_rows.append((
                strategy, model, family, rec.get("anchor_id"),
                anchor_wc, len(tokens(rewrite)),
                round(pct, 4), b,
                round(cos, 4) if isinstance(cos, (int, float)) else "",
                nfeat,
                "ok" if (pct_ok and sem_pass and (fok is not False)) else "fail",
            ))

    # Print summary
    print()
    print("Token-change distribution (rows that produced any rewrite):")
    print()
    hdr = f"{'strategy':<8} {'model':<22} {'n':>5} {'UNDER':>6} {'PASS':>6} {'PREF':>6} {'HIGH':>6} {'OVER':>6} {'BAD':>5} {'median%':>8} {'mean%':>7} {'sem<0.85':>9} {'feat_ok':>8} {'dual_pass':>10}"
    print(hdr)
    print("-" * len(hdr))
    for key in sorted(by_sm):
        strat, mdl = key
        c = by_sm[key]
        n = sum(v for k, v in c.items() if k != "BAD")
        ps = pct_samples[key]
        med = f"{100*median(ps):.1f}" if ps else "-"
        mn = f"{100*mean(ps):.1f}" if ps else "-"
        feat_disp = f"{feat_ok_count[key]}" if strat == "dialect" else "n/a"
        print(f"{strat:<8} {mdl:<22} {n:>5} {c['UNDER']:>6} {c['PASS']:>6} {c['PREF']:>6} {c['HIGH']:>6} {c['OVER']:>6} {c['BAD']:>5} {med:>8} {mn:>7} {sem_fail[key]:>9} {feat_disp:>8} {dual_pass[key]:>10}")

    print()
    print("Same-by-family for dialect strategy only (feature criterion bites here):")
    print()
    hdr2 = f"{'model':<22} {'family':<14} {'n_ok':>5} {'UNDER':>6} {'PASS':>6} {'PREF':>6} {'HIGH':>6} {'OVER':>6} {'BAD':>5}"
    print(hdr2)
    print("-" * len(hdr2))
    for (strat, mdl, fam), c in sorted(by_smd.items()):
        if strat != "dialect":
            continue
        n = sum(v for k, v in c.items() if k != "BAD")
        print(f"{mdl:<22} {fam:<14} {n:>5} {c['UNDER']:>6} {c['PASS']:>6} {c['PREF']:>6} {c['HIGH']:>6} {c['OVER']:>6} {c['BAD']:>5}")

    print()
    print("Same-by-family for base strategy (token-change buckets):")
    print()
    print(hdr2)
    print("-" * len(hdr2))
    for (strat, mdl, fam), c in sorted(by_smd.items()):
        if strat != "base":
            continue
        n = sum(v for k, v in c.items() if k != "BAD")
        print(f"{mdl:<22} {fam:<14} {n:>5} {c['UNDER']:>6} {c['PASS']:>6} {c['PREF']:>6} {c['HIGH']:>6} {c['OVER']:>6} {c['BAD']:>5}")

    print()
    print("Same-by-family for naive strategy:")
    print()
    print(hdr2)
    print("-" * len(hdr2))
    for (strat, mdl, fam), c in sorted(by_smd.items()):
        if strat != "naive":
            continue
        n = sum(v for k, v in c.items() if k != "BAD")
        print(f"{mdl:<22} {fam:<14} {n:>5} {c['UNDER']:>6} {c['PASS']:>6} {c['PREF']:>6} {c['HIGH']:>6} {c['OVER']:>6} {c['BAD']:>5}")

    print()
    print("Exemplar PREFERRED-band records (10–20% token change, hf_cos >= 0.85):")
    print()
    for key in sorted(exemplars):
        strat, mdl = key
        if not exemplars[key]:
            continue
        print(f"  {strat} · {mdl}")
        for ex in exemplars[key][:5]:
            cos_str = f"{ex['cos']:.3f}" if isinstance(ex['cos'], (int, float)) else "-"
            print(f"    [{ex['family']:<12} anchor {ex['anchor_id']} wc={ex['anchor_wc']:<3} pct={100*ex['pct']:.1f}% cos={cos_str} feats={ex['nfeat']}]")
            print(f"      A: {ex['anchor']}")
            print(f"      R: {ex['rewrite']}")
        print()

    if args.csv:
        with open(args.csv, "w") as fh:
            fh.write("strategy,model,family,anchor_id,anchor_tokens,rewrite_tokens,change_pct,bucket,hf_cosine,n_features,verdict\n")
            for row in per_record_rows:
                fh.write(",".join(str(x) for x in row) + "\n")
        print(f"Wrote per-record CSV: {args.csv}")


if __name__ == "__main__":
    main()
