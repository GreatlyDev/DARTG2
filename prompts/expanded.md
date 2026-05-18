You are extending a paper-source-backed dialect feature inventory for the DART benchmark.

Your goal is to (a) enrich each existing feature entry for the target dialect family with richer, safer, more inspectable documentation, and (b) propose new feature entries that the existing inventory is missing. The output is a single JSON object that a human reviewer will merge back into the inventory file after manual review.

INPUTS
Target Dialect Family:
{DIALECT_FAMILY}

Existing Inventory (current features[] array, verbatim):
{EXISTING_INVENTORY}

Allowed Sources (the only sources you may cite):
{ALLOWED_SOURCES}

Existing Blocklist and Safety Notes:
{EXISTING_BLOCKLIST_AND_SAFETY_NOTES}

REGISTER REFERENCE
The inventory must support U.S. student-essay register, not casual speech. The five paragraphs below show the *kind* of writing the inventory must enable. Calibrate descriptions, examples, applicability_conditions, and stereotyping_risk_notes to this register.

1. Lexical features only. In the story, the author shows how Mama is fixin' to leave the farm because she can't keep up with the work anymore. Y'all can see this when she packs the small suitcase and stares at the photograph on the wall. I reckon the author wants the reader to feel sad and also a little hopeful, because Mama is moving toward her sister's house, not toward nothing in particular.

2. Grammatical features. By the end of the chapter, the boy has done figured out that his grandfather was right about the river. He might could have known sooner if he had listened, but he kept ignoring them warnings the old man gave him. Them lessons in the story show that the boy grows up by paying attention to the people around him.

3. Mixed features. The character keeps a-trying even after he loses the race. He buys him a new pair of shoes and goes back to the track the next morning. The author shows this is right important because it tells the reader that effort matters more than winning, and that the character has changed from the person he was at the beginning of the story.

4. Discourse and longer-form. All y'all can see two reasons the author writes about the storm. The first reason is that the storm shows the family's strength when everything goes wrong. The second is that the storm changes how the daughter sees her father, one. He had to choose to protect the house or to drive into town for help, one, and he chose his family. I reckon that decision is what the author wants the reader to remember by the end of the chapter.

5. Restrained, full-paragraph register. In the poem, the speaker is fixin' to leave home, but she keeps thinking about her mother's words. Y'all can hear the regret in the way she describes the porch and the field. The author shows that growing up is not just leaving a place but carrying something with you. The speaker done learned that lesson by the last stanza, even though she might could go back and visit some day.

OUTPUT SCHEMA
You must output a single JSON object with exactly two keys: enriched_existing (an array) and new_proposed (an array). Each element of either array is a feature entry with the following fields. Use empty strings or empty arrays when a field genuinely has no content; do not omit fields.

Existing fields (preserve exactly for enriched entries; assign for new entries):
- id: short snake_case slug prefixed by the family short name (e.g., southern_*, aae_*, appalachian_*, midwestern_*, northeastern_*, western_*)
- category: one of "lexical", "syntactic", "discourse", "orthographic"
- feature: short human-readable feature name
- description: one or two sentences explaining the feature precisely
- safe_example: a single short example used in student-essay register
- blocked_context: contexts in which the feature must not be used
- risk_level: one of "low", "medium", "high"
- source_reference: semicolon-separated source string drawn only from {ALLOWED_SOURCES}
- citation_status: one of "appendix_a_direct", "paper_reference_expansion_needs_page_check", "needs_team_source_review"
- allowed_for_generation: boolean

New fields to add for every entry:
- examples: array of 2-4 short rewrites in student-essay register (not casual speech)
- counter_examples: array of 1-2 lines that look superficially similar but are NOT this feature
- applicability_conditions: explicit semantic/syntactic prerequisites the anchor must satisfy before this feature can be inserted
- intra_dialect_variation: short note on which sub-region, generation, or register uses this most; flags features that are not pan-family
- co_occurrence_notes: features in the same inventory that pair well, and any pairs that should not co-occur
- stereotyping_risk_notes: specific caricature, parody, or register risks beyond the generic disallowed_features list
- page_reference: page or chapter from the cited source; empty string if not yet confirmed
- meaning_preservation_check: one line a human reviewer can use to verify the rewrite preserved propositional content
- change_reason: for enriched_existing, a short note on what was added or refined relative to the prior entry; for new_proposed, exactly the string "new_entry"

INSTRUCTIONS
1. Operate strictly within {ALLOWED_SOURCES}. Any citation outside that list must set citation_status to "needs_team_source_review" and explain the source in stereotyping_risk_notes.
2. Never propose a feature that appears in {EXISTING_BLOCKLIST_AND_SAFETY_NOTES} or that overlaps semantically with a blocked feature.
3. For every entry in enriched_existing, preserve the existing id, category, feature, and source_reference exactly. You may refine description, safe_example, blocked_context, risk_level, citation_status, and allowed_for_generation only when the existing value is clearly under-specified or wrong by the cited source, and note the change in change_reason.
4. For every entry in new_proposed, only propose features that are documented in at least one source from {ALLOWED_SOURCES}. No internet-folk-linguistics, no caricature features, no features the inventory already covers under a different name.
5. Default allowed_for_generation to false for any new entry whose risk_level is "high", and for any orthographic or phonological feature regardless of risk level. Leave the gating decision to human review.
6. Calibrate every example, counter_example, and safe_example to student-essay register matching the REGISTER REFERENCE above. Do not use casual-speech examples.
7. For AAE specifically, apply extra caution: any new high-risk feature must have allowed_for_generation set to false, and stereotyping_risk_notes must explicitly address how the feature could be misread as error or caricature.
8. Output a single JSON object only. No prose outside the JSON. No markdown fences. No commentary. No trailing explanation.
9. If you cannot defensibly propose at least three new features for this family, return new_proposed as an empty array. Do not pad with weak features.

QUALITY CHECK BEFORE WRITING
Before producing the final JSON, verify:
- every cited source appears in {ALLOWED_SOURCES} or carries citation_status "needs_team_source_review"
- every entry has all required fields, including the new fields, with non-null values
- every new_proposed entry has at least one non-empty examples entry and a non-empty applicability_conditions
- no entry duplicates an existing id or feature name (case-insensitive comparison)
- no entry overlaps semantically with anything in {EXISTING_BLOCKLIST_AND_SAFETY_NOTES}
- every enriched_existing entry preserves the original id, category, feature, and source_reference exactly
- every orthographic or phonological new_proposed entry has allowed_for_generation set to false
- for AAE, every new high-risk entry has allowed_for_generation set to false and a non-empty stereotyping_risk_notes

If you cannot satisfy these constraints, output exactly:
FAIL
