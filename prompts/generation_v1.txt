You are rewriting a student response into a target U.S. English dialect for a controlled research benchmark.

Your goal is to produce ONE rewritten response that preserves the exact propositional meaning of the original while making the target dialect features visible enough for a robustness-testing benchmark.

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
1. Preserve the exact meaning of the anchor response.
2. Do not add, remove, exaggerate, or alter any facts, claims, reasoning, opinions, or tone.
3. Use only documented features from the approved feature inventory for the target dialect family.
4. Do not use stereotypes, caricatures, exaggerated slang, mocking spellings, or unsupported dialect features.
5. Keep the response sounding like natural, plausible student writing.
6. Keep the length close to the original response. Do not significantly shorten or expand it.
7. Do not correct the student's ideas, improve the argument, or make the writing more sophisticated.
8. Do not explain your choices.
9. Output only the rewritten response text.
10. The rewrite must not be nearly identical to the anchor. If only one minor word changes, the rewrite is invalid.
11. Use 2-4 approved target-dialect features when they can be used naturally without changing meaning.
12. If the approved inventory does not provide enough natural options for this anchor, use every safe applicable feature instead of forcing unsupported features.

QUALITY CHECK BEFORE WRITING
Before producing the final answer, make sure:
- the meaning matches the anchor response
- no new information has been introduced
- no original information has been removed
- at least two approved dialect features are present when the inventory and anchor meaning allow it
- the rewrite is visibly different from the anchor while still preserving meaning
- no disallowed feature is used

If you cannot produce a valid rewrite under these constraints, output exactly:
FAIL
