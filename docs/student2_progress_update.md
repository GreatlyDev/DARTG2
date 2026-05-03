# Student 2 Progress Update: Generation Pipeline

## Quick Summary

I started building out the Student 2 side of DART, which is the generation pipeline. The main goal of this part is to take an anchor response, pair it with a target dialect family, insert the approved feature inventory, and turn that into a controlled prompt that can later be sent to an LLM.

This is not the final benchmark yet. This is the first working version of the pipeline so we can test the flow before running full generation and validation.

The basic idea I am working from is:

```text
prompt template + anchor response + target dialect + feature inventory = candidate-generation prompt
```

A candidate-generation prompt is what we send to the LLM. A candidate is the LLM-generated attempt. A variant is a candidate that later passes filtering and validation.

## What I Added To The Repository

I pushed the first version of this work to my fork:

https://github.com/GreatlyDev/DARTG2

The main additions are:

- `prompts/generation_v1.txt`: the agreed controlled generation prompt
- `config/features.index.json`: an index that points each dialect family to its own inventory file
- `config/features/`: one JSON feature inventory file per dialect family
- `scripts/build_assignments.py`: creates anchor-to-dialect assignments
- `scripts/render_prompt_jobs.py`: renders generation prompts for each assignment
- `scripts/prefilter_candidates.py`: starter pre-filtering logic
- `dart_pipeline/`: helper code for assignments, inventory loading, prompt rendering, and pre-filter checks
- `tests/`: unit tests for the pipeline

## Feature Inventory Work

I split the feature inventory into one file per dialect family instead of keeping everything in one large JSON file. That makes it easier for people to review one dialect at a time and update features without touching the whole inventory.

The current dialect files are:

- Southern American English
- Midwestern/North Central
- Northeastern/New England
- Western American English
- Appalachian English
- African American Vernacular English (AAVE)

The current inventory is based on Appendix A from the DART EMNLP paper draft. I treated that appendix as the starting point, but I still think the inventory should be reviewed before real generation. Some features are also marked as blocked or review-only because they could be risky for generation, especially phonetic spellings or anything that could turn into a stereotype.

Current inventory counts:

| Dialect Family | Total Features | Allowed For Generation | Blocked / Review-Only |
|---|---:|---:|---:|
| Southern American English | 8 | 5 | 3 |
| Midwestern/North Central | 7 | 5 | 2 |
| Northeastern/New England | 6 | 3 | 3 |
| Western American English | 6 | 5 | 1 |
| Appalachian English | 9 | 5 | 4 |
| AAVE | 9 | 5 | 4 |
| **Total** | **45** | **28** | **17** |

This gives us a structured starting point, but it is not a complete extraction from every source in the references yet.

## Stage 1 Greedy Pilot

For the current pilot, I used a Stage 1 greedy setup:

```text
one dialect assignment per anchor
three candidate prompts per anchor-dialect pair
```

This means each anchor gets assigned to one dialect family for now, and then the pipeline renders three candidate-generation prompts for that anchor-dialect pair.

The greedy assignment cycles through the six dialect families in order. For example:

```text
Anchor A1 -> Southern American English
Anchor A2 -> Midwestern/North Central
Anchor A3 -> Northeastern/New England
Anchor A4 -> Western American English
Anchor A5 -> Appalachian English
Anchor A6 -> AAVE
Anchor A7 -> Southern American English
```

I used this approach because it lets us move quickly with the data we currently have. The balanced approach is still in the code, but I am treating that as something for later once the full metadata is available.

## Anchor Set Used For This Test

I tested the pipeline using the current anchor CSV:

```text
C:\Users\great\Downloads\final_anchors.csv
```

That file has 40 anchors.

Anchor set summary:

| Metric | Result |
|---|---:|
| Total anchors | 40 |
| Word length range | 63-150 words |
| Low score anchors | 15 |
| Mid score anchors | 10 |
| High score anchors | 15 |
| Original score range | 1-45 |
| Normalized score range | 1.8-5.0 |

The file currently includes:

- `essay_id`
- `essay_set`
- `anchor_response`
- `original_score`
- `normalized_score`
- `score_band`
- `length`
- `quality_score`
- `anchor_id`

The file is still missing a few things that matter before final generation:

- `prompt`
- `source_corpus`
- `domain` or `content_domain`
- `rubric_dimensions`

Because `prompt` is missing, the rendered prompt jobs currently show `[PROMPT NOT PROVIDED]`. That is fine for testing the pipeline structure, but it should be fixed before real generation.

## What The Pilot Produced

Using the Stage 1 greedy setup:

```text
40 anchors x 1 dialect assignment x 3 candidate prompts = 120 prompt jobs
```

Dialect assignment counts:

| Dialect Family | Anchor Assignments | Prompt Jobs |
|---|---:|---:|
| Southern American English | 7 | 21 |
| Midwestern/North Central | 7 | 21 |
| Northeastern/New England | 7 | 21 |
| Western American English | 7 | 21 |
| Appalachian English | 6 | 18 |
| AAVE | 6 | 18 |
| **Total** | **40** | **120** |

Candidate prompt counts:

| Candidate Index | Count |
|---|---:|
| Candidate 1 | 40 |
| Candidate 2 | 40 |
| Candidate 3 | 40 |

Important note: these are prompt jobs, not generated dialect variants yet. I have not run LLM generation from this pipeline yet.

## What This Proves So Far

This first pass shows that the pipeline can:

- read the current anchor CSV
- load the per-dialect feature inventories
- assign each anchor to one dialect family using the greedy strategy
- render three generation prompts per anchor-dialect pair
- keep generated output files out of git
- pass the current test suite

The current tests pass with:

```powershell
python -m unittest discover -s tests
```

## Current Limitations

A few things still need to be handled before real generation:

1. The anchor file still needs prompt text.
2. The anchor file still needs source corpus, domain, and rubric dimensions.
3. The feature inventory is based on Appendix A, but we have not expanded it from every cited source yet.
4. No LLM-generated candidate variants have been produced yet.
5. No semantic-equivalence, NLI, or human validation has been run yet.
6. The greedy setup is useful for this pilot, but the final benchmark may still need a stronger balancing step later.

## What I Want To Accomplish Next

The next things I want to focus on are:

1. Confirm that Appendix A can be used as the baseline feature inventory for now.
2. Add the missing anchor metadata, especially the original prompt text.
3. Confirm that three candidate prompts per anchor-dialect pair is the correct first-run setup.
4. Run a small LLM generation pilot from the Stage 1 greedy prompt jobs.
5. Review generated candidates for meaning drift, stereotypes, and feature usage.
6. Expand the feature inventory from the cited references one dialect family at a time.

## Short Version

I built and pushed the first version of the Student 2 generation pipeline. It supports the agreed prompt, Appendix A feature inventories, greedy assignment, prompt-job rendering, CSV/JSONL input, and starter pre-filter logic. I tested it on the current 40-anchor CSV and produced 120 Stage 1 greedy prompt jobs. These are ready for review, but final generation still needs complete prompt text and team approval of the feature inventories.
