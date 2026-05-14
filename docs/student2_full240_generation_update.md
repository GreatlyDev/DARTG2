# Student 2 Full 240 Generation Update

## Quick Summary

I finished the first full Student 2 generation run using the final 80-anchor dataset. The pipeline now produces candidate dialect variants instead of only preparing prompt jobs.

This run used the current expanded dialect feature inventory and the updated AAE terminology requested by Dr. Dacon. The outputs are still demo/unvalidated candidates, meaning they are ready for team review, filtering, and validation, but they should not be treated as final DART benchmark examples yet.

## What Was Generated

The current full run generated:

| Item | Count |
| --- | ---: |
| Anchor responses | 80 |
| Candidate variants per anchor | 3 |
| Total generated candidate variants | 240 |
| Unique candidate IDs | 240 |
| Unique anchor IDs | 80 |
| Model used | `gpt-5.2` |
| Candidate status | `demo_unvalidated` |

The generation setup is still the Stage 1 greedy setup: each anchor is assigned to one dialect family, and the model generates three candidate variants for that anchor-dialect pair.

## Anchor Dataset Used

The run used the final 80-anchor file from Student 1:

`data/raw/DART_FINAL_80_ANCHORS.csv`

The anchors come from three source datasets:

| Source Dataset | Anchors |
| --- | ---: |
| ASAP-AES | 40 |
| ASAP++ | 16 |
| ASAP_2.0 | 24 |

The score-band distribution is:

| Score Band | Anchors |
| --- | ---: |
| HIGH | 28 |
| MID | 26 |
| LOW | 26 |

## Dialect Family Coverage

Because 80 anchors does not divide evenly across the six dialect families, two dialect families receive 14 anchors each and the remaining four receive 13 anchors each. Since each anchor produces three candidates, this gives the following output distribution:

| Dialect Family | Candidate Variants |
| --- | ---: |
| Southern American English | 42 |
| Midwestern/North Central | 42 |
| Northeastern/New England | 39 |
| Western American English | 39 |
| Appalachian English | 39 |
| African American English (AAE) | 39 |

## Files Produced

The main generated output is:

`data/generated/final80_candidates_aae_full.jsonl`

The readable report is:

`docs/final80_candidates_aae_full.md`

The generated prompt jobs used for this run are:

`data/generated/final80_greedy_prompt_jobs_aae.jsonl`

The assignment file used to build those prompt jobs is:

`data/assignments/final80_greedy_assignments_aae.jsonl`

## What Changed From the Earlier Demo

Before this, the repository had an 18-candidate smoke-test demo. That smaller test was useful because it showed one anchor per dialect family and let the team quickly inspect whether the prompt and feature inventory were producing visible dialect variation.

The full run expands that same workflow to the full 80-anchor set:

- 80 anchors instead of 6 demo anchors
- 240 candidate variants instead of 18
- AAE terminology throughout the generated jobs and outputs
- The expanded feature inventory used in the generation prompt
- No terminal printing of all candidate responses during the full run

The full run writes the generated variants to a JSONL file and a readable Markdown report. The smaller smoke test can still print responses in the terminal because it is meant for quick inspection.

## Current Limitations

These candidates have not been human validated yet.

They still need:

- semantic-equivalence review
- dialect-feature review
- stereotype or inauthenticity review
- rejection/revision of weak candidates
- final selection of one approved variant per anchor-dialect pair, if the team decides to keep that structure

Some generated candidates may still be too close to the original response, while others may apply dialect features too strongly. That is expected at this stage because this run is meant to expose what the current prompt and inventory are doing at scale.

## Next Work I Am Taking On

My next focus is tightening the dialect feature inventory so every feature used in generation is tied back to a credible source. I am also keeping safer features separated from review-only or high-risk features so the generation pipeline does not treat all dialect markers as equally appropriate.

After the team reviews the 240 generated candidates, the next Student 2 pass should focus on improving the prompt and feature inventory based on observed failure cases.
