# Student 2 Base GPT-4o Candidate Workflow

This workflow is the current recommended path for producing the next DART Student 2 candidate set for review.

## Position

Use the existing Student 2 pipeline with the final 80 anchors, greedy dialect assignment, and three candidates per anchor:

```text
80 anchors x 1 assigned dialect family x 3 candidates = 240 candidate records
```

The generation model for this pass is `gpt-4o`. Professor White's broader matrix run showed that the inventory-injected/base prompt with `gpt-4o` produced the best balance of visible rewriting, low refusal rate, and cost. We are intentionally not carrying forward the full multi-strategy/multi-model matrix for this production-style pass.

## Critical Constraint

Candidates must not correct original student spelling, grammar, punctuation, capitalization, wording, argument quality, or writing sophistication unless a documented target-dialect feature explicitly requires that exact local change.

This matters because DART is testing rubric stability under dialectal variation, not rubric stability after cleanup. A candidate that changes `pationt` to `patient`, `greatful` to `grateful`, or `thier` to `their` should be rejected.

## One-Command Workflow

Run the full base/gpt-4o workflow:

```powershell
python scripts/run_base_gpt4o_workflow.py
```

For a smoke test:

```powershell
python scripts/run_base_gpt4o_workflow.py --limit 6
```

To rerun only checks over an existing raw generation file:

```powershell
python scripts/run_base_gpt4o_workflow.py --skip-generation
```

## Outputs

The workflow writes local generated artifacts:

```text
data/assignments/final80_base_gpt4o_assignments.jsonl
data/generated/final80_base_gpt4o_prompt_jobs.jsonl
data/generated/final80_base_gpt4o_candidates_raw.jsonl
data/generated/final80_base_gpt4o_candidates_prefiltered.jsonl
data/generated/final80_base_gpt4o_candidates_scored.jsonl
data/generated/final80_base_gpt4o_candidates_curated.jsonl
data/generated/final80_base_gpt4o_candidates_rejected.jsonl
docs/final80_base_gpt4o_candidates_review.md
```

Files under `data/generated/` are ignored by Git. Treat the raw, scored, curated, and rejected files as review artifacts until the team decides which generated records should be committed or sent forward.

## Review Meaning

`final80_base_gpt4o_candidates_raw.jsonl` is the model output.

`final80_base_gpt4o_candidates_prefiltered.jsonl` applies the feature and length prefilter. The workflow requires at least one detected approved feature by default because some anchor/dialect pairs only license one safe feature without forcing unsupported changes.

`final80_base_gpt4o_candidates_scored.jsonl` adds cheap similarity/change metrics and student-text-cleanup detection.

The scoring layer uses a low change threshold because this workflow is intentionally minimal-edit. Exact no-op outputs still fail, but candidates are not rejected merely because they preserve most of the anchor text.

`final80_base_gpt4o_candidates_curated.jsonl` contains records that passed the automated review layer.

`final80_base_gpt4o_candidates_rejected.jsonl` preserves rejected records and rejection reasons for audit.

The curated file is still not the final DART benchmark. It is the cleaner candidate set to prepare for Ricky/team review.

## Cleanup Retry And Repair

If candidates are rejected for `student_text_correction`, use targeted retry first:

```powershell
python scripts/retry_rejected_candidates.py --jobs data/generated/final80_base_gpt4o_prompt_jobs.jsonl --raw-candidates data/generated/final80_base_gpt4o_candidates_raw.jsonl --scored-candidates data/generated/final80_base_gpt4o_candidates_scored.jsonl --output data/generated/final80_base_gpt4o_candidates_retry1_raw.jsonl --model gpt-4o --rejection-reasons student_text_correction
```

If a small number of candidates still contain cleanup after retries, use mechanical repair to revert only the detected cleanup spans back to the original anchor tokens:

```powershell
python scripts/repair_student_cleanup.py --raw-candidates data/generated/final80_base_gpt4o_candidates_retry1_raw.jsonl --scored-candidates data/generated/final80_base_gpt4o_candidates_retry1_scored.jsonl --output data/generated/final80_base_gpt4o_candidates_repaired_raw.jsonl
```

Mechanical repair is conservative: it does not add dialect features or rewrite content. It only restores exact anchor spellings/word forms for spans already flagged as cleanup.
