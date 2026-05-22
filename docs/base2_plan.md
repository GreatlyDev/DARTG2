# base2 Run Plan

This document describes the prompt, model, and scope chosen for the base2 regeneration sweep, and exactly what will be produced so the resulting records can be traced end-to-end.

## Decision summary

| Choice | Value | Reason |
|---|---|---|
| Prompt | `prompts/base2.md` | Encodes the dual criterion (feature count + 5–25% token-change band) and emits structured `applied_features` + `feature_count`. |
| Model | `claude-sonnet-4-6` | Matrix assessment shows it sits on the threshold (median Δ ≈ 9.1%, 75% dual-pass rate, only 3.5% past the 25% ceiling). gpt-4o overshoots — both historically and in the base2 smoke. |
| Strategy name | `base2` | Registered in `dart_pipeline/strategies.py` as `STRATEGIES["base2"]` with `prompt_version = "base2_v1"`. |
| Scope | TBD — one of: full 6-family matrix (480 records) / single family (80 records). |

## Why base2 × claude-sonnet-4-6

The matrix assessment of the existing `base`/`naive`/`dialect` × `gpt-4o`/`sonnet`/`haiku` runs gives concrete numbers we can lean on:

- **gpt-4o overshoots the threshold.** `base × gpt-4o` had median Δ = 26.4% with 54% of records past the 25% ceiling. The base2 5-anchor smoke on gpt-4o landed at 33–51% token-diff per record — same overshoot pattern, pushed slightly harder by base2's stronger instructions.
- **claude-sonnet-4-6 already lives in the target band.** `base × claude-sonnet-4-6`: median Δ = 9.1%, 33% of records in the 10–20% PREF band, 3.5% over the 25% ceiling, 75% dual-pass rate (5% ≤ Δ ≤ 25% AND cosine ≥ 0.85). Best cell of the original matrix.
- **base2 encodes the assessment's recommendation #4.** The assessment proposed tweaking base.md to require ≥2 features on short anchors and 3–5 on longer anchors, target 10–20% token change, never exceed 25%. That language is now in base2.md.
- **base2 also addresses the assessment's recommendation #3.** It emits `applied_features` (each entry: `feature` + `realization`) and a self-reported `feature_count`, removing the need for a separate post-hoc diff-against-inventory pass to know which features were used per record.

## What gets run

Single CLI invocation per `(model, family)` cell:

```
python3 scripts/run_dialect_rewrite.py \
  --strategy base2 \
  --family <family> \
  --model claude-sonnet-4-6 \
  --anchors data/raw/DART_FINAL_80_ANCHORS.csv
```

Optional flags used in practice: `--limit`, `--anchor-id`, `--resume`, `--print-output`, `--sleep`, `--timeout`, `--max-output-tokens`, `--run-id`.

### Inputs (frozen and traceable)

| Input | Path | Notes |
|---|---|---|
| Anchor essays | `data/raw/DART_FINAL_80_ANCHORS.csv` | 80 anchors; columns include `essay_id`, `text`. |
| Prompt | `prompts/base2.md` | Loaded at runtime; recorded as `prompt_path` on every record. |
| Inventory | `config/features/<family>.json` | Per family. Same files used by the existing base/dialect runs. |
| Strategy code | `dart_pipeline/strategies.py` | `STRATEGIES["base2"]`, `prompt_version = "base2_v1"`. |
| API key | `.anthropicapi` (or `ANTHROPIC_API_KEY` in `.env`) | Required for the sonnet model. |

### Output

One JSONL file per cell at:

```
data/generated/base2__claude-sonnet-4-6__<family>.jsonl
```

One line per anchor. Schema (every field useful for tracing is included):

| Field | Purpose |
|---|---|
| `record_id` | `base2__claude-sonnet-4-6__<family>__<anchor_id>` — unique row key. |
| `run_id` | uuid4, shared across all anchors of one CLI invocation. |
| `timestamp`, `started_at`, `finished_at`, `duration_seconds` | When the call ran. |
| `anchor_id`, `anchor_text` | Identity of the input essay (matches `essay_id` in the CSV). |
| `dialect_family`, `dialect_title` | Which inventory was used. |
| `strategy`, `prompt_version`, `prompt_path`, `prompt_name` | Which prompt produced this row. For base2: `base2`, `base2_v1`, `prompts/base2.md`, `base2`. |
| `model`, `provider` | `claude-sonnet-4-6`, `anthropic`. |
| `rewrite_text` | The dialect rewrite. |
| `applied_features` | List of `{feature, realization, id}` — what the model claims it used (new for base2). |
| `model_notes` | Populated only when the model's self-reported `feature_count` disagrees with `len(applied_features)`. |
| `generation_status` | `ok` / `model_fail` / `parse_error` / `api_error`. |
| `raw_output` | Full JSON string the model returned, so the record can be re-parsed without re-calling the API. |
| `parse_error` | Reason for any non-`ok` status. |
| `openai_response_id` | The provider's response id for billing/audit cross-ref. |
| `tokens_in`, `tokens_out`, `cost_usd`, `usage` | Spend per record. |
| `anchor_extras` | `dataset`, `score`, `score_band`, `prompt`, `domain`, etc. carried through from the CSV. |

### How to retrace a result

Given a `record_id` like `base2__claude-sonnet-4-6__southern__764`, you can reconstruct:

- The prompt text by reading `prompt_path` at the commit referenced (`git log prompts/base2.md`).
- The inventory by reading `config/features/southern.json` at the same commit.
- The anchor by `anchor_id = 764` in `data/raw/DART_FINAL_80_ANCHORS.csv`.
- The model's claim of features used in `applied_features`, with the literal model JSON preserved in `raw_output`.
- The provider billing entry via `openai_response_id`.

## Smoke-test baseline already on disk

`data/test_tmp/base2_smoke_southern.jsonl` — 5 anchors, base2 × **gpt-4o**, Southern. Result: 4 ok / 1 model_fail; ok rewrites carried 3–5 distinct features each with realization snippets. Token-diff 33–51%, which is above the 25% ceiling and consistent with the assessment's finding that gpt-4o overshoots — the main reason the planned regeneration uses claude-sonnet-4-6 instead. This file is a smoke artifact only and not part of the regeneration output.

## Scope options (pick one)

| Option | Volume | Estimated cost | Estimated wall time |
|---|---|---|---|
| Full 6-family matrix | 6 × 80 = 480 records | ~$2.40 | ~30–40 min |
| Single family (southern) | 80 records | ~$0.40 | ~8–10 min |
| Single family (aae) | 80 records | ~$0.40 | ~8–10 min |

Choose the full matrix for an apples-to-apples comparison with the existing `base`/`naive`/`dialect` matrix. Choose a single family for the fastest validation of base2's behavior before committing to the full sweep.

## What is *not* changing

- The anchor CSV is unchanged.
- The per-family inventories under `config/features/` are unchanged.
- The other strategies (`naive`, `base`, `dialect`) and their existing output files are untouched.
- No changes to `prompts/base.md`, `prompts/naive.md`, or `prompts/dialects/*`.
