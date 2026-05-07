# Student 2 Update: Candidate Generation Demo

## Quick Summary

I added the next working piece of the Student 2 pipeline: actual candidate generation.

Before this update, the pipeline could create prompt jobs, but it did not send those jobs to a model or produce candidate variants. Now the repo includes a command-line generator that can send prepared prompt jobs to the OpenAI Responses API and save the generated candidate responses with metadata.

The basic flow now is:

```text
anchor response + dialect assignment + feature inventory + generation prompt
= prompt job

prompt job + OpenAI model
= demo candidate variant
```

These candidates are still marked as `demo_unvalidated`. They are not final DART benchmark variants.

## Why I Changed The Prompt

After the first small generation test, I noticed some outputs were too close to the original anchor response. In a few cases, the model only changed one word or made a very small surface-level edit.

That showed me the first prompt was too conservative. It protected the meaning, which is important, but it gave the model too much room to produce nearly identical rewrites.

I updated the prompt so it now says:

- the rewrite must not be nearly identical to the anchor
- one minor word change is not enough
- the model should use 2-4 approved dialect features when natural
- the rewrite still cannot add facts, remove facts, change tone, or use stereotypes

This made the demo candidates more visibly different, but it also showed why we need strong filtering and human validation before anything becomes final.

## What I Added

The main additions are:

- `scripts/generate_candidates.py`: generates candidate variants from rendered prompt jobs using the OpenAI API
- `dart_pipeline/generation.py`: helper logic for OpenAI requests, response parsing, metadata, and `.env` loading
- `scripts/render_candidate_report.py`: turns generated JSONL candidates into a readable Markdown report
- `data/examples/stage1_demo_candidates_a1_a6.jsonl`: curated example JSONL output with 18 demo candidates
- `docs/examples/stage1_demo_candidates_a1_a6.md`: readable version of the same 18 demo candidates
- updated `README.md` commands so another person can run the generator locally
- updated tests for the new generation/reporting pieces

I also added `.env` to `.gitignore` so API keys stay local and do not get pushed.

## Demo Run

For the demo, I generated one anchor set for each dialect family:

| Anchor | Dialect Family | Candidates |
|---|---|---:|
| A1 | Southern American English | 3 |
| A2 | Midwestern/North Central | 3 |
| A3 | Northeastern/New England | 3 |
| A4 | Western American English | 3 |
| A5 | Appalachian English | 3 |
| A6 | African American Vernacular English (AAVE) | 3 |
| **Total** | **6 dialect families** | **18** |

The committed example is intentionally small. I did not commit every local generation run. The repo now has one clean example that people can inspect, while future local runs stay ignored under `data/generated/`.

## How Professor White Or Another Collaborator Can Run It

The collaborator needs an OpenAI API key in a local `.env` file:

```text
OPENAI_API_KEY=their_key_here
```

Then they can run:

```powershell
python scripts/generate_candidates.py --jobs data/generated/stage1_greedy_prompt_jobs.jsonl --output data/generated/stage1_demo_candidates.jsonl --model gpt-5.2 --limit 18 --resume --print-output
```

Then render a readable report:

```powershell
python scripts/render_candidate_report.py --anchors "C:\Users\great\Downloads\final_anchors.csv" --candidates data/generated/stage1_demo_candidates.jsonl --output docs/stage1_demo_candidates.md
```

The generated files stay local unless the person intentionally commits them.

## What I Noticed From The Candidates

The demo candidates proved that the generation pipeline works, but they also showed quality issues we need to handle.

Some candidates still seem too close to the original anchor. Others go too far in the other direction and change things we may not want changed.

Specific issues I noticed:

- the model sometimes corrects student spelling or grammar
- the model sometimes completes missing or unfinished text
- some dialect features feel forced or inserted
- some candidates are too similar to each other
- some rewrites change the academic tone too much
- AAVE outputs need especially careful review because the feature inventory is not robust enough yet

This confirms that generation alone is not enough. We need filtering and validation.

## Current Limitation

The feature inventories are still draft inventories. They were enough to test the pipeline, but they are not yet strong enough to treat these candidates as final benchmark data.

That means the current candidates should be read as:

```text
working demo candidates
not validated DART variants
```

## What I Think Needs To Happen Next

The next things I want to focus on are:

1. Add stronger candidate quality checks.
2. Flag candidates that are too similar to the anchor.
3. Flag candidates where the model corrected spelling or grammar.
4. Flag candidates that may have added or removed meaning.
5. Continue building a more source-backed feature inventory.
6. Use human review before accepting any candidate as a real DART variant.

## Short Version

I moved the Student 2 pipeline from prompt-job preparation to actual demo candidate generation. The repo can now generate candidate variants through the OpenAI API, save them as JSONL, and render a readable report. I also included one curated 18-candidate example covering all six dialect families. The demo works, but the outputs show why we still need stronger feature inventories, filtering, and validation before calling anything final.
