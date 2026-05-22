You are rewriting a student response into a target U.S. English dialect for a controlled research benchmark.

Your goal is to produce ONE controlled dialect rewrite that preserves the exact propositional meaning of the original student response while adding meaningful and linguistically valid target-dialect features at the surface level. The rewrite must vary noticeably from the anchor, not be a one- or two-word edit.

INPUTS
Prompt:
{PROMPT}

Anchor Response:
{ANCHOR_RESPONSE}

Target Dialect Family:
{DIALECT_FAMILY}

Approved Feature Inventory:
{FEATURE_INVENTORY}

Disallowed Features / Notes:
{DISALLOWED_FEATURES_AND_NOTES}

INSTRUCTIONS
1. Start from the anchor response and produce a dialect-transformed version with meaningful surface variation, not a minimal edit or near-copy.
2. Preserve the full meaning, intent, reasoning, factual content, stance, and tone of the original response. Do NOT add or remove information.
3. Apply controlled dialectal transformations distributed across multiple linguistic levels, drawing only from the Approved Feature Inventory:
   - lexical substitutions (approved dialect vocabulary)
   - syntactic variation (sentence restructuring where natural for the dialect)
   - morphological variation (contractions, informal verb forms if allowed)
   - discourse markers (conversational connectors if in inventory)
4. Ensure the output reflects real dialectal usage patterns, not isolated token swaps or single-word insertions.
5. Use only features explicitly listed in the Approved Feature Inventory. Do NOT invent features.
6. Maintain naturalness and fluency consistent with human student writing in the target dialect.
7. Preserve the original sentence structure where possible, but allow local restructuring when required by an approved dialect pattern.
8. Do NOT correct or "clean" the student's writing style unless required by an approved dialect feature.
9. Avoid stereotypes, exaggerated slang, caricature spelling, or artificial transformations.
10. Do NOT introduce new information, explanations, or commentary.
11. Do NOT rely on a single transformation. Distribute multiple changes across the response.

TRANSFORMATION STRENGTH TARGETS
Apply BOTH a feature criterion and a surface-variation criterion. Meaning preservation is non-negotiable; the criteria below describe how much the SURFACE should change, not the content.

Feature criterion (primary):
- For short anchors (under ~60 words): use AT LEAST 2 distinct approved dialect feature realizations.
- For longer anchors: prefer 3 to 5 distinct approved dialect feature realizations.
- Each realization should be a recognizable instance of a published feature in the inventory, not a generic informal-English edit.

Surface-variation criterion (secondary):
- Minimum passable: roughly 5%-10% of tokens changed, IF those changes are clear published dialect features.
- Preferred target: roughly 10%-20% of tokens changed for short anchors.
- Upper bound: avoid going much beyond 20%-25% of tokens changed — beyond that the variant starts to read as paraphrase or meaning drift rather than dialect rewriting.

If the inventory does not support enough natural transformations to clear the minimum feature criterion, output FAIL rather than forcing unsupported features or paraphrasing.

MEANING PRESERVATION (STRICT)
- No change in argument or claim.
- No change in factual content.
- No change in stance or tone.
- Length should stay approximately similar; natural expansion or compression caused by dialect structure is acceptable.

If multiple valid rewrites are possible, choose the one with the highest naturalness, the most diverse feature usage, and the strongest dialect consistency.

QUALITY CHECK BEFORE WRITING
Before producing the final answer, verify:
- meaning is identical to the anchor response
- at least 2 distinct approved dialect features are realized (3-5 when the anchor is long enough)
- changes are distributed across the text, not localized to one spot
- surface variation falls within the 5%-25% token-change band
- no unsupported slang or invented dialect forms are used
- no single-token or prefix-only transformation strategy is used
- output is not a near-copy of the anchor

OUTPUT FORMAT
Output a single JSON object and nothing else. No markdown fences, no commentary, no preamble.

The JSON object MUST have exactly these keys:
{
  "rewrite_text": "<the rewritten response text only>",
  "applied_features": [
    {"feature": "<feature name copied verbatim from the Approved Feature Inventory>", "realization": "<the exact substring in the rewrite that realizes this feature>"}
  ],
  "feature_count": <integer count of distinct features actually used in the rewrite>
}

Rules for the JSON:
- "rewrite_text" must contain only the rewritten response — no labels, no quotes around the whole thing, no notes.
- "applied_features" must list each distinct approved-inventory feature you actually applied. The "feature" value must be copied verbatim from the Approved Feature Inventory text above (the short human-readable name shown there). The "realization" value must be a short snippet taken from your rewrite that demonstrates the feature.
- List a feature once even if it is realized in multiple places in the rewrite.
- "feature_count" must equal the number of entries in "applied_features".
- Do not include features you considered but did not apply.
- Do not invent features that are not in the inventory.

If you cannot produce a valid rewrite under these constraints, output exactly:
FAIL
