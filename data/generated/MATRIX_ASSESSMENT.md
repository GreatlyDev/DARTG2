# DART Matrix Assessment

**Run date:** 2026-05-18 to 2026-05-19
**Total records produced:** 4,193 (of a 4,320 target — 127 missing from two Haiku `base` cells that did not complete)
**Total cost:** **$37.97**
**Total tokens:** 7.94M input · 1.85M output

---

## 1. Headline

Across 3 strategies × 3 models × 6 dialect families × 80 anchors:

| Strategy × Model | n | ok% | refused% | avg change | avg HF cosine | $/rec |
|---|---:|---:|---:|---:|---:|---:|
| **base · gpt-4o** ★ | 480 | 99% | 1% | **0.66** | 0.918 | $0.003 |
| naive · gpt-4o | 480 | 100% | 0% | 0.62 | 0.910 | $0.002 |
| naive · claude-sonnet-4-6 | 480 | 100% | 0% | 0.39 | 0.923 | $0.003 |
| naive · claude-haiku-4-5 | 480 | 100% | 4% | 0.33 | 0.942 | $0.001 |
| base · claude-haiku-4-5 † | 353 | 100% | 0% | 0.33 | 0.960 | $0.002 |
| base · claude-sonnet-4-6 | 480 | 100% | 0% | 0.29 | 0.956 | $0.005 |
| dialect · gpt-4o | 480 | 100% | 54% | 0.05 | 0.991 | $0.015 |
| dialect · claude-sonnet-4-6 | 480 | 80% | 69% | 0.03 | 0.994 | $0.040 |
| dialect · claude-haiku-4-5 | 480 | 38% | 87% | 0.03 | 0.994 | $0.009 |

★ Recommended primary configuration for benchmark variant generation.
† Two cells (`midwestern`, `northeastern`) didn't complete during the run; 127 records missing.

Key takeaway: **`base × gpt-4o` is the only configuration that hits all four targets simultaneously** — it actually rewrites the anchor, preserves meaning, almost never refuses, and is cheap.

---

## 2. Five non-obvious findings

### Finding 1 — `base` rewrites MORE aggressively than `naive` on gpt-4o
- naive/gpt-4o avg change: 0.62
- base/gpt-4o avg change: **0.66**

Giving gpt-4o the explicit feature inventory in `base` increases rewriting depth, not decreases it. The inventory becomes a *permission slip* (legitimizing specific dialect transformations) rather than a *constraint*. **This is the most counterintuitive result of the run** and the most important for benchmark design — the inventory works.

### Finding 2 — The `dialect` strategy is structurally over-conservative for essay register
- 429 of 480 gpt-4o `dialect` records (89%) have composite_change < 0.1
- Refusal rate by family is concentrated in non-grammatical inventories:

| Family | Refused (dialect/gpt-4o) | Why |
|---|---:|---|
| midwestern | 90% | Inventory is mostly situational lexical (pop, bubbler, kitty-corner) — never appears in essays |
| northeastern | 60% | Same issue (tonic, jimmies, rotary) |
| western | 45% | Has `hella`, `gonna`, `quotative like` — these can fire |
| southern | **35%** | `reckon`, `right`, `y'all`, `fixin'` all hit naturally |
| aae | 45% | Grammatical features (habitual be, perfective done) fire |
| appalachian | 46% | Similar to southern |

The greedy license-by-anchor logic isn't broken — the *inventories themselves under-serve academic register* for midwestern and northeastern. The Sonnet midwestern/northeastern numbers are even worse: **99% / 70% refused.**

### Finding 3 — The "high cosine" stat on `dialect` is misleading
Both Anthropic models on dialect show HF cosine ≈ 0.994, which looks like exceptional meaning preservation. **It is — because the model returned the anchor unchanged.** 69–87% of those records are unchanged anchors with cosine 1.0, pulling the average toward perfection. The *real* rewriting subset is tiny.

### Finding 4 — Sonnet 4.6 is the wrong cost/value choice for this task
- Sonnet `dialect` alone consumed **$19.11 — 50% of the entire matrix budget**
- Most of those tokens were Sonnet writing reasoning prose before the JSON, exceeding `max_tokens=2500` and producing parse_errors anyway (20% of Sonnet dialect records ended up as parse_error even after recovery)
- For comparable change/cosine on `base`, Sonnet costs **$0.005/rec vs gpt-4o's $0.003** — 67% more expensive, with *lower* change and only marginally better cosine

### Finding 5 — Some "low cosine" outputs are content-moderation refusals, not meaning drift
Spot-checking the worst HF cosines on `base/gpt-4o` (cosine = −0.05) revealed records like:
> anchor: "Also, the number one and two things that get most people in wrecks, texting and drinking..."
> rewrite: "Sorry, I can't assist with that."

These are **gpt-4o refusing the request entirely**, not bad rewrites. The cheap-tier scorers correctly flag these as outliers (`length_ratio` < 0.05, `composite_change` ≈ 1.0). Worth filtering on `length_ratio` thresholds when curating the benchmark.

---

## 3. Composite change distribution (gpt-4o, ok records only)

```
naive (480 ok):
  <0.1       29   ██
  0.1-0.3    66   ██████
  0.3-0.5    72   ███████
  0.5-0.7    76   ███████
  0.7-1.0   237   ███████████████████████

base (477 ok):
  <0.1       17   █
  0.1-0.3    35   ███
  0.3-0.5    89   ████████
  0.5-0.7    91   █████████
  0.7-1.0   245   ████████████████████████   ← strongest cohort

dialect (480 ok):
  <0.1      429   ██████████████████████████████████████████   ← 89% no-change
  0.1-0.3    26   ██
  0.3-0.5    14   █
  0.5-0.7     4
  0.7-1.0     7
```

`base` has the strongest middle-and-upper distribution: 425 of 477 records (89%) show non-trivial transformation (change > 0.3), and 245 (51%) show heavy transformation (change > 0.7). This is the benchmark-quality cohort.

---

## 4. Feature usage on `dialect` strategy (which features actually fired)

Across all 1,440 `dialect` records, the features the model selected most often:

| Family | Top features used | Count |
|---|---|---:|
| **aae** | topic_chaining · habitual_be · kinfolk · demonstrative_them · perfective_done | 43 · 39 · 34 · 20 · 13 |
| **southern** | reckon · right_intensifier · y'all · fixin' to · double_modal | 50 · 43 · 16 · 12 · 9 |
| **appalachian** | right_intensifier · nary · 'em · a_prefixing · y'all | 36 · 23 · 16 · 14 · 12 |
| **western** | hella · gonna · quotative_like · totally · you guys | 52 · 38 · 24 · 8 · 6 |
| **northeastern** | wicked · youse · pragmatic_deletion | 84 · 8 · 3 |
| **midwestern** | ope · needs_cleaned · you guys · alls | 5 · 2 · 2 · 1 |

Observations:
- **Midwestern is essentially unusable.** Only 10 feature applications across 240 records (3 models × 80 anchors). The inventory needs grammatical/discourse features added.
- **Northeastern is `wicked`-dominated.** 84/95 applications = 88% are just the intensifier. Single-feature dialects produce low variety.
- **AAE / southern / appalachian / western are healthy** — diverse, multi-feature dialects with broad essay applicability.

This is the single biggest finding for *inventory design*: the situational lexical features (food, geography, soft drinks) are dead weight in essay register. Grammar and intensifiers carry the load.

---

## 5. Cost breakdown

```
strategy   model                     $ total
─────────────────────────────────────────────
naive      claude-haiku-4-5         $   0.43
naive      gpt-4o                   $   0.84
naive      claude-sonnet-4-6        $   1.35
base       claude-haiku-4-5         $   0.59
base       gpt-4o                   $   1.61
base       claude-sonnet-4-6        $   2.44
dialect    claude-haiku-4-5         $   4.27
dialect    gpt-4o                   $   7.33
dialect    claude-sonnet-4-6        $  19.11   ← 50% of total budget
─────────────────────────────────────────────
TOTAL                               $  37.97
```

**$26.71 of the $37.97 (70%) was spent on the `dialect` strategy across all three models** — and only ~700 of those 1,440 records produced any actual rewrite. Per-useful-rewrite cost on Sonnet dialect: ~$0.14. On gpt-4o naive: ~$0.002. **70× cost differential between the cheapest and most expensive strategies for benchmark-equivalent output.**

---

## 6. Sample records (base · gpt-4o, the recommended config)

### Sweet-spot rewrite (change 0.55, hf_cos 0.95)

> **Anchor (AAE family):**
> The book still will be censored to be in that section or not, but we still will have those wonderful books that we all love so much. What if there was a great informative book about how to do a certain…
>
> **Rewrite:**
> The book still gonna be censored to be in that section or not, but we still finna have them wonderful books that we all love so much. What if there was a great informative book about how to do a certa…

Features visible: `gonna` substituted for "will" (Western-style but acceptable as AAE), `finna` for "will," `them` as demonstrative. Vocabulary preserved, meaning preserved, dialect plausibly applied.

### Heavy rewrite (change 0.995, hf_cos 0.92) — Midwestern target

> **Anchor:**
> But it shouldn't get to the point where people can just remove books from the shelf at their own free will. Without some limit on censorship in a library, absol…
>
> **Rewrite:**
> People shouldn't be able to just take books off the shelf whenever they feel like it, right? Without some cap on censorship in a library, you guys could find ab…

Features: `you guys` (midwestern second-person plural), tag-question `right?`, plus the rewriter restructured the opening clause. Aggressive but meaning intact.

### Refusal mis-detection — content moderation, not meaning drift

> **Anchor (southern family):**
> Also, the number one and two things that get most people in wrecks, texting and drinking. People do not have to worry about a driverless car texting someone ba…
>
> **Rewrite:**
> Sorry, I can't assist with that.

The cheap-tier metrics correctly flag this as anomalous (hf_cos = −0.05, length_ratio ≈ 0.04). Filtering on `rewrite_word_count > 10` or `length_ratio > 0.3` removes these from the curated set.

---

## 7. Recommendations

**For producing the DART benchmark variants:**

1. **Primary generator: `base × gpt-4o`.** 99% ok rate, 0.66 average change, 0.918 average cosine, $0.003 per record. This is the headline configuration to scale.
2. **Diversity supplement: `naive × claude-sonnet-4-6`** (when you want different rewriting *style* — Anthropic models add features without eye-dialect spellings). Adds variety without breaking quality.
3. **Skip `dialect` for variant generation** — its 89% no-change rate makes it expensive ($/useful-rewrite). Keep it as an *analytical tool* to study which features actually fire (gpt-4o is the only model worth using here, since Anthropic mostly returns parse_errors).

**For inventory work:**

4. **Midwestern and northeastern inventories need redesign.** Add grammatical / discourse-marker features (e.g., midwestern `needs cleaned`, `wants fixed`, `come with`) that fire in essay text. Strip out food/drink/geography vocabulary that almost never licenses.
5. **AAE, southern, appalachian, western are healthy** — keep as-is.

**For curating final benchmark records:**

6. **Filter on `length_ratio` and `rewrite_word_count`** to remove content-moderation refusals (`length_ratio < 0.3` or `rewrite_word_count < 20`).
7. **Keep records with `composite_change ≥ 0.3` AND `hf_cos ≥ 0.85`** — gives ~250–350 high-quality variants per (strategy, model) cell.
8. **Drop the `refused == true` rows from variant sets.** Keep them in the dataset (audit trail) but not as published variants.

**For follow-up runs:**

9. **Fix the Haiku gaps** — re-run the 2 incomplete `base/claude-haiku-4-5` cells (`midwestern`, `northeastern`) — ~$1, ~10 min.
10. **Consider gpt-5 / future OpenAI tier upgrade.** Right now your project is restricted to gpt-4o only. If you can enable `text-embedding-3-small`, you'd also unlock semantic-cosine on the cloud side (currently HF-local only).
11. **Consider `claude-haiku-4-5` for `naive`/`base`** if cost matters more than transformation depth — at $0.001–0.002/rec it's 60% cheaper than gpt-4o for similar throughput.

---

## 8. Schema reference (per record)

Each JSONL record contains 36+ fields. The fields most useful for analysis:

| Field | Type | Meaning |
|---|---|---|
| `strategy` | str | `naive` / `base` / `dialect` |
| `model` | str | `gpt-4o` / `claude-haiku-4-5` / `claude-sonnet-4-6` |
| `dialect_family` | str | `aae` / `southern` / … |
| `anchor_text` | str | original essay |
| `rewrite_text` | str | model's transformation (empty when status ≠ ok) |
| `generation_status` | str | `ok` / `parse_error` / `model_fail` / `api_error` |
| `refused` | bool | True if anchor returned unchanged or status not ok |
| `composite_change_score` | float | 1 − difflib_ratio · single rank-able "how different" |
| `similarity_scores.cosine_embeddings.hf/all-MiniLM-L6-v2` | float | semantic similarity (0–1) |
| `applied_features` | list[dict] | only `dialect`: which features fired |
| `tokens_in`, `tokens_out`, `cost_usd` | int/float | API call metrics |
| `run_id` | str | UUID grouping all records produced in one matrix invocation |
| `prompt_path`, `prompt_name` | str | exact prompt used (attribution) |

Snapshots: `data/generated/original.zip` (pre-scoring) and `data/generated/enriched.zip` (post-scoring).
