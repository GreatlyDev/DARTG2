# Structural Targeted Regeneration Runbook

This runbook lets another team member run the targeted Student 2 regeneration pass
without needing Great-Anthony's OpenAI credits.

## Purpose

Use this pass after the Dr. Dacon/Ricky review decision:

1. Keep the clean candidates already generated.
2. Regenerate only candidates flagged for low sibling diversity, near-anchor duplication, weak feature diversity, or surface-change issues.
3. Use structural sibling diversity, not only lexical changes.
4. Re-run the same audit metrics so the before/after comparison is clean.

## Required Local Setup

From a fresh clone of the repo:

```bash
git pull origin main
```

Create a local `.env` file in the repo root:

```bash
OPENAI_API_KEY=your_key_here
```

Do not commit `.env`.

## Inputs Already Tracked In GitHub

These input files are intentionally tracked even though most generated outputs are ignored:

- `data/generated/final80_structural_regen_prompt_jobs.jsonl`
- `data/generated/final80_structural_regen_input_raw.jsonl`
- `data/generated/final80_structural_regen_input_audit.jsonl`

They are the prompt jobs, current raw candidate pool, and current audit/review file needed
to run the targeted regeneration.

## Run Targeted Structural Regeneration

Run from the repo root:

```bash
python scripts/retry_rejected_candidates.py \
  --jobs data/generated/final80_structural_regen_prompt_jobs.jsonl \
  --raw-candidates data/generated/final80_structural_regen_input_raw.jsonl \
  --scored-candidates data/generated/final80_structural_regen_input_audit.jsonl \
  --output data/generated/final80_structural_targeted_retry_raw.jsonl \
  --model gpt-5.2 \
  --sleep 0.2 \
  --timeout 180 \
  --max-output-tokens 900 \
  --max-attempts 4 \
  --retry-wait 8
```

The script checkpoints after each successful candidate. If quota or rate limits stop the run,
run the same command again and it will resume from the existing output file.

## Re-run Prefiltering, Scoring, And Ricky Audit

```bash
python scripts/prefilter_candidates.py \
  --anchors data/raw/DART_FINAL_80_ANCHORS.csv \
  --candidates data/generated/final80_structural_targeted_retry_raw.jsonl \
  --output data/generated/final80_structural_targeted_retry_prefiltered.jsonl

python scripts/score_candidates.py \
  --anchors data/raw/DART_FINAL_80_ANCHORS.csv \
  --candidates data/generated/final80_structural_targeted_retry_prefiltered.jsonl \
  --output data/generated/final80_structural_targeted_retry_scored_base.jsonl

python scripts/audit_ricky_candidate_quality.py \
  --candidates data/generated/final80_structural_targeted_retry_scored_base.jsonl \
  --output data/generated/final80_structural_targeted_retry_scored_audit.jsonl
```

## Metrics To Compare Before And After

Compare the new audit file against:

`data/generated/final80_structural_regen_input_audit.jsonl`

Important metrics:

- `anchor_near_duplicate`
- `pairwise_sibling_similarity`
- `max_pairwise_sibling_similarity`
- `sibling_similarity_over_threshold_count`
- `feature_realization_count`
- `student_text_correction`
- literal `FAIL` outputs

## Notes

- Do not regenerate all 240 from scratch unless the team explicitly changes the plan.
- Do not change original anchor text.
- Do not push `.env` or any API key.
- Output filenames intentionally do not include dates.
