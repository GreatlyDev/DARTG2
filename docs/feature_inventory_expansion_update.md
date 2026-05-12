# Feature Inventory Expansion Update

## Quick Summary

I expanded the dialect feature inventories so the generation pipeline has more documented options to work with before we run the next candidate-generation demo. The main goal is to reduce the problem we saw in the first demo: some candidate responses were too close to the original anchor because the model did not have enough safe, approved dialect features to use.

This is still a source-aware draft, not the final linguistic appendix. I separated features into two practical groups:

- **Allowed for generation:** safe enough to use in controlled candidate generation when the anchor meaning supports the feature.
- **Blocked or review-only:** documented or potentially relevant, but too risky for uncontrolled use because it could cause semantic drift, stereotype, accent parody, or register problems.

## Inventory Growth

| Dialect family | Previous total | Previous allowed | Expanded total | Expanded allowed |
|---|---:|---:|---:|---:|
| Southern American English | 8 | 5 | 15 | 10 |
| Midwestern/North Central | 7 | 5 | 13 | 10 |
| Northeastern/New England | 6 | 3 | 13 | 8 |
| Western American English | 6 | 5 | 12 | 10 |
| Appalachian English | 9 | 5 | 16 | 12 |
| African American Vernacular English (AAVE) | 9 | 5 | 17 | 7 |
| **Total** | **45** | **28** | **86** | **57** |

## What Changed

### Southern American English

I added safer lexical and grammatical options such as `all y'all`, `right` as an intensifier, personal datives, a-prefixing, and alternative one. I kept high-risk items like phonetic spellings and positive anymore blocked for now.

### Midwestern/North Central

I added features that should give the model more than just `ope`, including `you guys`, `kitty-corner`, `wants fixed`, `come with`, and the `alls` construction. This should help avoid forcing `ope` into places where it sounds awkward.

### Northeastern/New England

I added mostly lexical and phrase-level features such as `rotary`, `tonic`, `jimmies`, `youse/yous`, `down cellar`, and `down the shore`. I kept non-rhotic spellings blocked because they can easily become caricature.

### Western American English

I expanded beyond `hella`, `totally`, and `like` by adding `hecka`, `for sure`, `you guys`, `kinda`, and the Southern California freeway article pattern like `the 5`. I kept prosodic features such as uptalk blocked because they do not transfer cleanly into written anchors.

### Appalachian English

I added more Appalachian/Southern Appalachian features, including `right` as an intensifier, `nary`, perfective `done`, double modals, personal datives, and demonstrative `them`. I kept features that could become caricature or meaning drift blocked.

### AAVE

I expanded the AAVE inventory with paper-source-backed tense/aspect and syntactic features such as perfective `done`, stressed `BIN`, negative inversion, third-person singular `-s` absence, and demonstrative `them`. I left several real AAVE features blocked or review-only because they are high-risk without careful human validation.

## Source Strategy

I tightened the inventory so every active feature now points back to either Appendix A of the DART paper or one of the sociolinguistic sources already cited in the paper. I removed source hubs and survey pages from the JSON citation basis for now because the team needs the inventory to stand on the paper's own reference list.

The JSON now uses two main citation statuses:

| Citation status | Meaning |
|---|---|
| `appendix_a_direct` | The feature is explicitly listed in Appendix A of the DART paper and tied there to a cited source. |
| `paper_reference_expansion_needs_page_check` | The feature is an expansion candidate tied to one of the paper's cited sources, but the exact page/chapter still needs to be verified before final benchmark release. |

My thinking here is that the pipeline can move forward while the research appendix stays honest. We can generate demo candidates from the expanded inventory, but anything not directly listed in Appendix A should stay marked as needing page-level verification until the team checks the cited source.

## Paper Sources Used For This Expansion

These are the paper-cited sources now used as the citation basis in the active JSON inventories:

- Labov, 1972, *Language in the Inner City: Studies in the Black English Vernacular*
- Labov, 1998, *Phonological Variation and Change in North American English*
- Labov, Ash, and Boberg, 2006, *Atlas of North American English*
- Rickford and Rickford, 1999, *African American Vernacular English: Features, Evolution, Educational Implications*
- Dacon, 2022, *Towards a Deep Multi-Layered Dialectal Language Analysis: A Case Study of African-American English*
- Wolfram, 2004, *Urban Language and Education*
- Wolfram and Schilling, 2016, *American English: Dialects and Variation*
- Williams, 1992, *Linguistic Variation in the Southern Appalachian Mountains*
- Eckert, 2001, *Linguistic Variation as Social Practice*

## What This Should Improve In Generation

The first candidate demo proved that the pipeline works, but it also showed three quality issues:

- Some outputs were too similar to the anchor.
- Some outputs used awkward or forced dialect markers.
- Some outputs corrected the student's original wording, which is not allowed because the candidate should preserve the student's propositional content and approximate writing level.

The expanded inventory should help because the model has more safe feature choices per dialect family. That means it should not have to rely on one obvious marker like `ope`, `wicked`, `hella`, or `y'all` every time.

## Next Test

The next test should be another Stage 1 demo using the same six-anchor/six-dialect setup:

- A1 -> Southern American English, 3 candidates
- A2 -> Midwestern/North Central, 3 candidates
- A3 -> Northeastern/New England, 3 candidates
- A4 -> Western American English, 3 candidates
- A5 -> Appalachian English, 3 candidates
- A6 -> AAVE, 3 candidates

That gives us 18 candidates again, but now generated from the expanded feature inventory. The comparison question is simple:

> Do the new candidates show more visible dialect variation while preserving anchor meaning better than the previous demo?

## Expanded Inventory Demo Observations

I ran the 18-candidate demo after expanding the inventories. The demo confirms that the pipeline can use the expanded feature inventory, but it also shows why the next stage needs filtering and validation.

What improved:

- The candidates show more visible dialect variation than the first demo.
- The model has more than one feature option for several dialect families, so it is less dependent on one marker like `ope`, `wicked`, `hella`, or `reckon`.
- The rendered prompt jobs now include the expanded inventory directly in the generation prompt.

Issues still showing up:

- The model sometimes uses a feature that is not currently allowed in the inventory, such as `ain't` in Southern/AAVE candidates.
- The model sometimes uses a blocked or review-only grammatical pattern, such as AAVE zero copula in `while he on his journey`.
- The model sometimes corrects student errors, such as changing misspellings or cleaning up grammar, even though the prompt says not to improve the writing.
- Some candidates still shift register too much, especially when informal discourse markers are overused.

What this means:

The expanded inventory helped with variation, but we still need a stronger prefilter layer. The next useful improvement is to detect unsupported features, detect correction of original student errors, and flag candidates that use blocked features before they reach human validation.

## Remaining Caveat

This expansion should make the demo stronger, but it does not replace human validation. The feature inventory controls what the model is allowed to use, but the generated candidate still needs filtering and review before it becomes a validated DART variant.
