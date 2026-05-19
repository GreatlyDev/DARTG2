# DART Generation Pipeline

This repository contains the current Student 2 generation pipeline for DART. The pipeline takes approved anchor responses, assigns each anchor to a target U.S. English dialect family, renders controlled generation prompts from the dialect feature inventory, and generates candidate dialect variants for later filtering and human validation.

The current working dataset is the final 80-anchor set from Student 1.

## Current Scope

This repo currently supports:

- source-backed dialect feature inventories under `config/features/`
- greedy and balanced anchor-to-dialect assignment generation
- a curated final-80 demo assignment set
- prompt-job rendering for OpenAI generation
- candidate generation through the OpenAI Responses API
- readable Markdown candidate reports
- lightweight prefilter scaffolding

Generated candidates are **not final DART variants**. They should stay marked as `demo_unvalidated` until they pass semantic-equivalence review, dialect-feature review, and human validation.

## Current Working Strategy

The current Stage 1 strategy is:

```text
one dialect assignment per anchor
three candidate generations per anchor-dialect pair
```

For the final 80-anchor dataset, that gives:

```text
80 anchors x 1 dialect assignment x 3 candidates = 240 prompt jobs
```

We also keep a smaller curated demo:

```text
6 anchor-dialect pairs x 3 candidates = 18 demo candidates
```

The curated demo intentionally covers all six dialect families, all three score bands, and all three source datasets.

## Repository Structure

- `config/features.index.json`: maps each dialect family to its feature file.
- `config/features/`: one paper-source-backed feature inventory per dialect family.
- `data/raw/`: final Student 1 anchor files committed for the current pipeline.
- `data/examples/`: curated candidate examples that the team intentionally commits.
- `data/generated/`: local generated outputs; ignored by Git.
- `data/assignments/`: local assignment files; ignored by Git.
- `docs/examples/`: readable committed demo reports.
- `docs/`: progress/update docs and team-facing notes.
- `prompts/generation_v1.txt`: controlled rewrite prompt template.
- `scripts/build_assignments.py`: creates greedy or balanced assignments.
- `scripts/build_demo_assignments.py`: creates the curated final-80 demo assignment file.
- `scripts/render_prompt_jobs.py`: renders candidate-generation prompt jobs.
- `scripts/generate_candidates.py`: calls the OpenAI Responses API and writes generated candidates.
- `scripts/render_candidate_report.py`: renders generated JSONL candidates into readable Markdown.
- `scripts/prefilter_candidates.py`: lightweight prefilter checks.
- `tests/`: unit tests for the Student 2 pipeline.

## Committed Data

The current committed anchor files are:

```text
data/raw/DART_FINAL_80_ANCHORS.csv
data/raw/DART_ANCHOR_SUMMARY.csv
```

The current committed demo outputs are:

```text
data/examples/final80_demo_candidates_expanded_inventory.jsonl
docs/examples/final80_demo_candidates_expanded_inventory.md
```

These examples are intentionally committed so collaborators can inspect what the pipeline produces without needing to run the OpenAI API first.

## Environment Setup

Set your OpenAI API key before running generation:

```powershell
$env:OPENAI_API_KEY="your_api_key_here"
```

You can also create a local `.env` file in the repo root:

```text
OPENAI_API_KEY=your_api_key_here
```

The `.env` file is ignored by Git.

## Final 80 Workflow

### Recommended Base/GPT-4o Review Run

The current recommended Student 2 production-style pass uses the inventory-injected base prompt with `gpt-4o`, then runs prefiltering, scoring, and curation with hard rejection for spelling/grammar cleanup of original student text:

```powershell
python scripts/run_base_gpt4o_workflow.py
```

For a small smoke test:

```powershell
python scripts/run_base_gpt4o_workflow.py --limit 6
```

See `docs/student2_base_gpt4o_workflow.md` for output paths and review notes.

### Manual Step-By-Step Workflow

Build the full final-80 greedy assignment file:

```powershell
python scripts/build_assignments.py --anchors data/raw/DART_FINAL_80_ANCHORS.csv --features config/features.index.json --strategy greedy --candidates 3 --output data/assignments/final80_greedy_assignments.jsonl
```

Render the full 240 prompt jobs:

```powershell
python scripts/render_prompt_jobs.py --anchors data/raw/DART_FINAL_80_ANCHORS.csv --assignments data/assignments/final80_greedy_assignments.jsonl --features config/features.index.json --template prompts/generation_v1.txt --output data/generated/final80_greedy_prompt_jobs.jsonl
```

Generate all 240 candidate responses:

```powershell
python scripts/generate_candidates.py --jobs data/generated/final80_greedy_prompt_jobs.jsonl --output data/generated/final80_candidates_expanded_inventory.jsonl --model gpt-5.2 --resume
```

Render a readable full-run report:

```powershell
python scripts/render_candidate_report.py --anchors data/raw/DART_FINAL_80_ANCHORS.csv --candidates data/generated/final80_candidates_expanded_inventory.jsonl --output docs/final80_candidates_expanded_inventory.md
```

The full 240-candidate run can take time and API budget. For quick review, use the curated demo below.

For full runs, leave off `--print-output`. The terminal will show normal progress lines like `[1/240] Generating ...` and the final output path, but it will not print all 240 candidate responses into the terminal. The full generated records are written to the JSONL file passed with `--output`.

## Curated 18-Candidate Demo

Build the curated six-pair demo assignment file:

```powershell
python scripts/build_demo_assignments.py --anchors data/raw/DART_FINAL_80_ANCHORS.csv --output data/assignments/final80_demo_assignments.jsonl --candidates 3
```

Render the 18 demo prompt jobs:

```powershell
python scripts/render_prompt_jobs.py --anchors data/raw/DART_FINAL_80_ANCHORS.csv --assignments data/assignments/final80_demo_assignments.jsonl --features config/features.index.json --template prompts/generation_v1.txt --output data/generated/final80_demo_prompt_jobs.jsonl
```

Run the 18-candidate demo:

```powershell
python scripts/generate_candidates.py --jobs data/generated/final80_demo_prompt_jobs.jsonl --output data/generated/final80_demo_candidates_expanded_inventory.jsonl --model gpt-5.2 --limit 18 --resume --print-output
```

The demo command keeps `--print-output` on purpose so reviewers can immediately see the generated candidate responses in the terminal. The same records are still written to the JSONL output file.

Render the readable demo report:

```powershell
python scripts/render_candidate_report.py --anchors data/raw/DART_FINAL_80_ANCHORS.csv --candidates data/generated/final80_demo_candidates_expanded_inventory.jsonl --output docs/final80_demo_candidates_expanded_inventory.md
```

Generated files in `data/generated/` and generated reports matching `docs/final80_demo_candidates*.md` are local run artifacts and ignored by Git. If the team wants to commit a curated example, copy it into:

```text
data/examples/
docs/examples/
```

## Older Stage 1 Commands

The repo still supports the earlier draft-anchor workflow. For the current research workflow, prefer the final-80 commands above.

Build draft Stage 1 greedy assignments:

```powershell
python scripts/build_assignments.py --anchors "C:\Users\great\Downloads\final_anchors.csv" --strategy greedy --output data/assignments/stage1_greedy_assignments.jsonl --candidates 3
```

Render draft Stage 1 prompt jobs:

```powershell
python scripts/render_prompt_jobs.py --anchors "C:\Users\great\Downloads\final_anchors.csv" --assignments data/assignments/stage1_greedy_assignments.jsonl --output data/generated/stage1_greedy_prompt_jobs.jsonl
```

## Local Generated Outputs

Local generation outputs are ignored by Git:

```text
data/assignments/
data/generated/
data/test_tmp/
docs/stage1_demo_candidates*.md
docs/final80_demo_candidates*.md
```

This keeps collaborators from accidentally committing their own generated candidate files.

## Required Anchor Fields

The pipeline now supports the final Student 1 CSV format:

- `essay_id`
- `dataset`
- `text`
- `score`
- `normalized_score`
- `score_band`

The pipeline also remains compatible with earlier anchor formats that use:

- `anchor_id`
- `source_corpus`
- `anchor_response`
- `essay`
- `prompt`
- `domain`

If `prompt` is missing, prompt jobs render `[PROMPT NOT PROVIDED]`. That is acceptable for plumbing tests, but final benchmark generation should eventually include prompt/rubric context when available.

## Feature Inventory Caution

The active feature inventories are paper-source-backed drafts. Each feature points to Appendix A of the DART paper or to a source already cited in the paper. Some features are allowed for generation, while higher-risk features are kept as blocked or review-only.

Generated demo candidates are useful for showing the pipeline, but they are not final benchmark variants. They still need semantic-equivalence review, dialect authenticity review, feature safety checks, and stereotyping-risk review.

## Tests

Run tests with:

```powershell
python -m unittest discover -s tests
```
