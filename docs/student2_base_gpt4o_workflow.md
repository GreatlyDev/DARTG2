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

`final80_base_gpt4o_candidates_prefiltered.jsonl` applies the feature and length prefilter.

`final80_base_gpt4o_candidates_scored.jsonl` adds cheap similarity/change metrics and student-text-cleanup detection.

`final80_base_gpt4o_candidates_curated.jsonl` contains records that passed the automated review layer.

`final80_base_gpt4o_candidates_rejected.jsonl` preserves rejected records and rejection reasons for audit.

The curated file is still not the final DART benchmark. It is the cleaner candidate set to prepare for Ricky/team review.
