# DART Generation Pipeline

This repository contains the first version of the DART generation and pre-filtering pipeline I started building for the Student 2 work.

The main goal is to turn an approved anchor response into controlled generation jobs by combining:

- the agreed generation prompt template
- a target dialect family
- that dialect family's feature inventory
- anchor-to-dialect assignments
- repeatable candidate-generation jobs
- lightweight pre-filter checks before human validation

## Current Scope

This version does not call an LLM API yet. It prepares reproducible prompt jobs that can be fed into a model once the team confirms the anchors, feature inventories, and model access. That keeps the first generation run controlled instead of producing candidate variants before the pipeline has been reviewed.

## Current Working Strategy: Stage 1 Greedy

For the current research workflow, we are using **Stage 1 greedy**:

```text
one dialect assignment per anchor
three candidate generations per anchor-dialect pair
```

That means 40 anchors produce 40 anchor-dialect assignments and 120 prompt jobs. This is a pilot/iteration strategy: use the best current anchors and Appendix A feature inventories, generate prompt jobs quickly, inspect failures, and improve.

Balanced assignment support exists in the code, but it is not the current working path. It is reserved for later cleanup/final benchmark balancing once the anchor set has complete metadata such as `source_corpus`, `domain`, `prompt`, and `rubric_dimensions`.

## Main Files

- `config/features.index.json`: maps each dialect family to its own feature file under `config/features/`. The per-dialect files are populated from Appendix A and marked for team review.
- `prompts/generation_v1.txt`: agreed controlled rewrite prompt template.
- `scripts/build_assignments.py`: creates greedy or balanced anchor-to-dialect assignments.
- `scripts/render_prompt_jobs.py`: renders one prompt job per candidate generation attempt.
- `scripts/prefilter_candidates.py`: runs lightweight length and feature-presence checks on generated candidates.

## Strategies

### Greedy

The greedy strategy uses anchors in the order provided and cycles through the dialect families. In Stage 1, each anchor receives exactly one dialect family assignment and three candidate generation prompts.

Use greedy for:

- the current pilot work
- prompt pipeline testing
- early generation runs
- quick failure inspection

### Balanced

The balanced strategy interleaves anchors across available `source_corpus`, `score_band`, and `domain` strata before assigning dialects. This is closer to final benchmark balancing, but it requires complete anchor metadata to be meaningful.

Use balanced later for:

- final dataset cleanup
- checking underrepresented slices
- stratified benchmark construction

## Example Commands

Build Stage 1 greedy assignments from the current CSV anchor file:

```powershell
python scripts/build_assignments.py --anchors "C:\Users\great\Downloads\final_anchors.csv" --strategy greedy --output data/assignments/stage1_greedy_assignments.jsonl --candidates 3
```

Render Stage 1 greedy prompt jobs:

```powershell
python scripts/render_prompt_jobs.py --anchors "C:\Users\great\Downloads\final_anchors.csv" --assignments data/assignments/stage1_greedy_assignments.jsonl --output data/generated/stage1_greedy_prompt_jobs.jsonl
```

Run tests:

```powershell
python -m unittest discover -s tests
```

## Required Anchor Fields

The pipeline can work with either `anchor_id` or `essay_id`, but generation-ready anchors should eventually include:

- `anchor_id`
- `prompt`
- `anchor_response`
- `human_score` normalized to the DART 1-5 scale
- `score_band`
- `domain`
- `source_corpus`
- `rubric_dimensions`

If `prompt` is missing, prompt jobs will render `[PROMPT NOT PROVIDED]`, which is acceptable for plumbing tests but not final generation.

## Important Research Caution

The feature inventories are Appendix A drafts, not final linguistic authority. The team should review them before real benchmark generation. The pipeline is designed so the team can update individual files under `config/features/` without rewriting the rest of the workflow.
