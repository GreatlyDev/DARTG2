# Student 2 Handoff Draft For Ricky

Date: 2026-05-17

## Current Status

I have the Student 2 generation pipeline working for the final 80-anchor dataset.

Current run status:

- 80 anchors from Student 1
- 1 assigned dialect family per anchor
- 3 candidate variants per anchor
- 240 demo/unvalidated candidate records
- 240 unique candidate IDs in the cleaned report
- 0 literal `FAIL` outputs after retry handling
- terminology updated from AAVE to African American English (AAE)
- feature inventories organized by dialect family, feature type, risk/safety status, and source reference
- local draft feature inventory matrix created for appendix review

The current 240 candidates are not final validated DART pairs. They are generated candidates prepared for filtering and human review.

## Main Repo Artifacts

- Candidate report: `docs/final80_candidates_aae_full.md`
- Feature inventories: `config/features/`
- Feature index: `config/features.index.json`
- Generation prompt: `prompts/generation_v1.txt`
- Trace prompt added from Professor White's branch idea: `prompts/inventory_trace_v1.txt`
- Optional trace generator: `scripts/generate_traced_candidates.py`
- Trace comparison report renderer: `scripts/render_trace_comparison.py`
- Local appendix-facing draft matrix: `docs/feature_inventory_matrix_draft.md`

## What Changed From Professor White's Branch

Professor White's branch had a useful traceability idea:

- output the rewrite as structured JSON
- include `applied_features`
- include `rejected_candidates`
- include notes explaining why features were or were not licensed by the anchor
- render readable comparison outputs

I kept the main branch as the base because it already has the full 240-candidate run, AAE terminology cleanup, and literal-failure retry handling. I selectively added the trace-style pieces without replacing the current pipeline.

Important issue found in Professor White's sample outputs:

- Some outputs corrected original student spelling/grammar even when no dialect feature was applied.
- Example: `pationt -> patient`, `cam -> can`, `snowmible -> snowmobile`, `troils -> trails`.
- That is a methodological problem because DART should isolate dialectal variation, not improve writing quality.

I added tooling to flag this kind of correction in trace-style outputs.

## Current Known Risks

The next Student 2 risks are:

- semantic drift in generated candidates
- unsupported dialect features appearing in outputs
- blocked/review-only features appearing in outputs
- correction of original student spelling or grammar
- too few documented dialect features in a candidate
- dialect features that are source-aware but not yet page-verified
- stereotype or register drift

## What Ricky Can Start On

Ricky can start analysis/mitigation planning using the current generated set, but should treat it as demo/unvalidated.

Recommended safe handoff framing:

> I have the full 240 candidate generation run working with zero failed outputs. The current outputs are demo/unvalidated candidates. My next Student 2 focus is making the feature inventory more defensible by tying each feature to sources and strengthening the pre-filtering layer before human validation. I also added trace-style tooling inspired by Professor White's branch so we can inspect applied/rejected features and flag cases where the model corrected original student spelling or grammar.

Suggested Ricky next steps:

- review the 240-candidate report for gross semantic drift and unsupported feature use
- use the feature inventory matrix to understand which features are demo-safe vs review-only
- coordinate analysis/mitigation experiments only after candidate filtering status is clear
- avoid treating any generated candidate as final benchmark data until validation is complete

## Student 2 Remaining Checklist

- [x] Build generation pipeline
- [x] Use final 80-anchor Student 1 dataset
- [x] Generate 240 candidate records
- [x] Update AAVE terminology to AAE
- [x] Add failure detection and retry handling for literal `FAIL` outputs
- [x] Create readable full-candidate report
- [x] Draft source-backed feature inventory matrix
- [x] Add trace-style applied/rejected feature tooling
- [ ] Page-verify source citations for inventory features
- [ ] Strengthen automated pre-filtering
- [ ] Add blocked-feature detection
- [ ] Add unsupported-feature detection
- [ ] Add student-error correction detection to the candidate review flow
- [ ] Add semantic-equivalence filtering or prepare an LLM/NLI judge plan
- [ ] Prepare final appendix-ready inventory and BibTeX table
- [ ] Run human validation / team review

## Paper Alignment Notes

The paper says DART needs:

- semantic equivalence
- documented dialectal variation
- feature inventories grounded in sociolinguistic literature
- automated pre-filtering
- human validation
- rejection of stereotype amplification
- full provenance

The paper draft also has a number mismatch:

- one section says GPT-4o generates 4 candidate variants per anchor-dialect pair
- Table 2 and the current target say 80 anchors -> 240 pairs
- 240 pairs means 3 variants per anchor, not 4

Current implementation follows the 240-pair target.
