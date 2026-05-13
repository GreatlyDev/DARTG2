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
| African American English (AAE) | 9 | 5 | 17 | 7 |
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

### AAE

I expanded the AAE inventory with paper-source-backed tense/aspect and syntactic features such as perfective `done`, stressed `BIN`, negative inversion, third-person singular `-s` absence, and demonstrative `them`. I left several real AAE features blocked or review-only because they are high-risk without careful human validation.

## Source Strategy

I tightened the inventory so every active feature now points back to either Appendix A of the DART paper or one of the sociolinguistic sources already cited in the paper. I also kept source status visible so the team can distinguish features already listed in the DART appendix from features that still need source-page confirmation before final release.

The inventory uses two main source-status groups:

| Source status | Meaning |
|---|---|
| Listed in DART appendix | The feature is explicitly listed in Appendix A of the DART paper and tied there to a cited source. |
| Paper-cited source; confirm before final | The feature is an expansion candidate tied to one of the paper's cited sources, but the exact page/chapter still needs to be verified before final benchmark release. |

My thinking here is that the pipeline can move forward while the research appendix stays honest. We can generate demo candidates from the expanded inventory, but anything not directly listed in Appendix A should stay marked as needing page-level verification until the team checks the cited source.

## Paper Sources Used For This Expansion

These are the paper-cited sources now used as the citation basis in the active JSON inventories:

- Labov, 1972, *Language in the Inner City: Studies in the Black English Vernacular*
- Labov, 1998, *Phonological Variation and Change in North American English*
- Labov, Ash, and Boberg, 2006, *Atlas of North American English*
- Rickford, 1999, *African American Vernacular English: Features, Evolution, Educational Implications*
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
- A6 -> AAE, 3 candidates

That gives us 18 candidates again, but now generated from the expanded feature inventory. The comparison question is simple:

> Do the new candidates show more visible dialect variation while preserving anchor meaning better than the previous demo?

## Expanded Inventory Demo Observations

I ran the 18-candidate demo after expanding the inventories. The demo confirms that the pipeline can use the expanded feature inventory, but it also shows why the next stage needs filtering and validation.

What improved:

- The candidates show more visible dialect variation than the first demo.
- The model has more than one feature option for several dialect families, so it is less dependent on one marker like `ope`, `wicked`, `hella`, or `reckon`.
- The rendered prompt jobs now include the expanded inventory directly in the generation prompt.

Issues still showing up:

- The model sometimes uses a feature that is not currently allowed in the inventory, such as `ain't` in Southern/AAE candidates.
- The model sometimes uses a blocked or review-only grammatical pattern, such as AAE zero copula in `while he on his journey`.
- The model sometimes corrects student errors, such as changing misspellings or cleaning up grammar, even though the prompt says not to improve the writing.
- Some candidates still shift register too much, especially when informal discourse markers are overused.

What this means:

The expanded inventory helped with variation, but we still need a stronger prefilter layer. The next useful improvement is to detect unsupported features, detect correction of original student errors, and flag candidates that use blocked features before they reach human validation.

## Remaining Caveat

This expansion should make the demo stronger, but it does not replace human validation. The feature inventory controls what the model is allowed to use, but the generated candidate still needs filtering and review before it becomes a validated DART variant.

## Working BibTeX References

These are draft BibTeX entries for sources used in the feature inventory. The keys/details can be revised before the final appendix, but this gives the paper a direct BibTeX starting point.

```bibtex
@incollection{bernstein2003southern,
  author    = {Bernstein, Cynthia},
  title     = {Grammatical Features of Southern Speech: Y'all, Might Could, and Fixin To},
  booktitle = {English in the Southern United States},
  editor    = {Nagle, Stephen J. and Sanders, Sara L.},
  year      = {2003},
  publisher = {Cambridge University Press}
}

@book{labov1972language,
  author    = {Labov, William},
  title     = {Language in the Inner City: Studies in the Black English Vernacular},
  year      = {1972},
  publisher = {University of Pennsylvania Press}
}

@book{labov2006atlas,
  author    = {Labov, William and Ash, Sharon and Boberg, Charles},
  title     = {The Atlas of North American English: Phonetics, Phonology and Sound Change},
  year      = {2006},
  publisher = {Mouton de Gruyter}
}

@book{rickford1999african,
  author    = {Rickford, John R.},
  title     = {African American Vernacular English: Features, Evolution, Educational Implications},
  year      = {1999},
  publisher = {Blackwell}
}

@book{green2002african,
  author    = {Green, Lisa J.},
  title     = {African American English: A Linguistic Introduction},
  year      = {2002},
  publisher = {Cambridge University Press}
}

@book{wolfram2016american,
  author    = {Wolfram, Walt and Schilling, Natalie},
  title     = {American English: Dialects and Variation},
  edition   = {3},
  year      = {2016},
  publisher = {Wiley Blackwell}
}

@book{eckert2000linguistic,
  author    = {Eckert, Penelope},
  title     = {Linguistic Variation as Social Practice: The Linguistic Construction of Identity in Belten High},
  year      = {2000},
  publisher = {Blackwell}
}

@book{darcy2017like,
  author    = {D'Arcy, Alexandra},
  title     = {Discourse-Pragmatic Variation in Context: Eight Hundred Years of LIKE},
  year      = {2017},
  publisher = {John Benjamins}
}

@article{bucholtz2007hella,
  author  = {Bucholtz, Mary and Bermudez, Nancy and Fung, Victor and Edwards, Lisa and Vargas, Rosalva},
  title   = {Hella Nor Cal or Totally So Cal?: The Perceptual Dialectology of California},
  journal = {Journal of English Linguistics},
  year    = {2007},
  volume  = {35},
  number  = {4},
  pages   = {325--352}
}

@book{kurath1949word,
  author    = {Kurath, Hans},
  title     = {A Word Geography of the Eastern United States},
  year      = {1949},
  publisher = {University of Michigan Press}
}

@book{carver1987american,
  author    = {Carver, Craig M.},
  title     = {American Regional Dialects: A Word Geography},
  year      = {1987},
  publisher = {University of Michigan Press}
}

@book{wolfram1976appalachian,
  author    = {Wolfram, Walt and Christian, Donna},
  title     = {Appalachian Speech},
  year      = {1976},
  publisher = {Center for Applied Linguistics}
}

@misc{yalegrammaticaldiversity,
  author       = {{Yale Grammatical Diversity Project}},
  title        = {Yale Grammatical Diversity Project},
  howpublished = {\url{https://ygdp.yale.edu/}},
  note         = {Accessed for dialect feature documentation}
}

@misc{harvarddialectsurvey,
  author       = {Vaux, Bert and Golder, Scott},
  title        = {The Harvard Dialect Survey},
  howpublished = {\url{http://dialect.redlog.net/}},
  year         = {2003}
}

@misc{stanfordvoices,
  author       = {{Stanford Voices of California}},
  title        = {Voices of California},
  howpublished = {\url{https://voicesofcalifornia.stanford.edu/}},
  note         = {Accessed for California English documentation}
}
```
