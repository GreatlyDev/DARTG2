# DART Student 2 Feature Inventory Matrix Draft

Date: 2026-05-17

Status: local research draft. Do not treat this as a finalized linguistic appendix until the DART paper text and source page references have been checked.

## Purpose

This document turns the current Student 2 JSON inventories into a reviewable feature matrix for Dr. Dacon, Professor White, and the validation team. It keeps the generation pipeline's current status separate from a more conservative appendix-facing recommendation.

The current repo inventories are source-aware drafts. Many features point either to DART Appendix A or to a source already named in the paper, but the exact page or chapter has not always been verified in this checkout. For appendix work, features with `paper_reference_expansion_needs_page_check` should remain review-only until a human confirms the source location.

## Status Definitions

| Status | Meaning |
|---|---|
| allowed/demo-safe | Suitable for controlled demo generation when the anchor meaning licenses the feature. Still requires human validation before final benchmark release. |
| review-only | Documented or plausible enough to track, but should not be used for production generation until source pages, dialect fit, register, and semantic conditions are confirmed. |
| high-risk/do-not-use | Too likely to create stereotype amplification, eye-dialect, semantic drift, register mismatch, or unintelligibility in written student-response rewrites. |

## Repository Baseline

| Dialect family | Total features | Currently allowed in JSON | Appendix-direct allowed | Allowed but needs page check |
|---|---:|---:|---:|---:|
| Southern American English | 15 | 10 | 5 | 5 |
| Midwestern/North Central | 13 | 10 | 5 | 5 |
| Northeastern/New England | 13 | 8 | 3 | 5 |
| Western American English | 12 | 10 | 5 | 5 |
| Appalachian English | 16 | 12 | 5 | 7 |
| African American English (AAE) | 17 | 7 | 5 | 2 |
| **Total** | **86** | **57** | **28** | **29** |

## Matrix

### Southern American English

| Feature label | Feature text or pattern | Type | Current JSON status | Recommended safety | Written rewrite suitability | Source citation | BibTeX key | Notes |
|---|---|---|---|---|---|---|---|---|
| southern_yall | y'all | lexical | allowed | allowed/demo-safe | Yes, only for second-person plural/address contexts | DART Appendix A; Wolfram 2004 | dartAppendixA; wolfram2004urban | Do not insert when the anchor has no addressee. |
| southern_all_yall | all y'all | lexical | allowed | review-only | Limited | Wolfram 2004; Wolfram and Schilling 2016 | wolfram2004urban; wolfram2016american | Needs page-level confirmation and plural group context. |
| southern_fixin_to | fixin' to | lexical | allowed | allowed/demo-safe | Yes, only for near-future meaning | DART Appendix A; Wolfram 2004 | dartAppendixA; wolfram2004urban | Do not add future intent if absent from anchor. |
| southern_reckon | reckon | lexical | allowed | allowed/demo-safe | Yes, if replacing think/suppose without changing stance | DART Appendix A; Wolfram 2004 | dartAppendixA; wolfram2004urban | Use sparingly; can sound forced in formal answers. |
| southern_right_intensifier | right as intensifier | lexical | allowed | review-only | Limited | Wolfram and Schilling 2016 | wolfram2016american | Needs page check; avoid comic rural voice. |
| southern_bless_your_heart | bless your heart | lexical | blocked | high-risk/do-not-use | No | DART Appendix A; Wolfram 2004 | dartAppendixA; wolfram2004urban | Pragmatically loaded and easy to misuse. |
| southern_perfective_done | perfective done | syntactic | allowed | allowed/demo-safe | Yes, only where completion/result is already present | DART Appendix A; Labov 1998 | dartAppendixA; labov1998phonological | Do not create completed aspect. |
| southern_double_modal | double modals | syntactic | allowed | allowed/demo-safe | Yes, only where uncertainty/ability already exists | DART Appendix A; Labov 1998 | dartAppendixA; labov1998phonological | Example forms like might could must preserve modality. |
| southern_personal_dative | personal dative | syntactic | allowed | review-only | Limited | Wolfram and Schilling 2016 | wolfram2016american | Needs page check; use only with clear subject involvement. |
| southern_a_prefixing | a-prefixing with -ing verbs | syntactic | allowed | review-only | Limited | Wolfram and Schilling 2016 | wolfram2016american | Needs page check and careful grammar constraints. |
| southern_aint | a'nt / ain't | orthographic | blocked | high-risk/do-not-use | No for current generation | DART Appendix A; Wolfram and Schilling 2016 | dartAppendixA; wolfram2016american | Keep blocked unless a separate orthographic condition is approved. |
| southern_alternative_one | alternative one | discourse | allowed | review-only | Rare | Wolfram and Schilling 2016 | wolfram2016american | Needs page check and an existing either/or contrast. |
| southern_what_all | what all / where all | discourse | blocked | high-risk/do-not-use | No for current anchors | Wolfram and Schilling 2016 | wolfram2016american | Likely to change sentence type or add a question. |
| southern_positive_anymore | positive anymore | discourse | blocked | high-risk/do-not-use | No for current generation | DART Appendix A; Labov, Ash, and Boberg 2006 | dartAppendixA; labov2006atlas | High semantic/aspect drift risk. |
| southern_pin_pen_spelling | pin-pen merger spelling | orthographic | blocked | high-risk/do-not-use | No | DART Appendix A; Wolfram and Schilling 2016 | dartAppendixA; wolfram2016american | Phonetic spelling risks caricature. |

### Midwestern/North Central

| Feature label | Feature text or pattern | Type | Current JSON status | Recommended safety | Written rewrite suitability | Source citation | BibTeX key | Notes |
|---|---|---|---|---|---|---|---|---|
| midwestern_ope | ope | lexical | allowed | allowed/demo-safe | Limited | DART Appendix A; Labov, Ash, and Boberg 2006 | dartAppendixA; labov2006atlas | Use only for mild surprise/repair; easy to overuse. |
| midwestern_you_guys | you guys | lexical | allowed | review-only | Yes, if addressee exists | Wolfram and Schilling 2016 | wolfram2016american | Needs page check and plural addressee context. |
| midwestern_pop | pop | lexical | allowed | allowed/demo-safe | Rare in educational anchors | DART Appendix A; Labov, Ash, and Boberg 2006 | dartAppendixA; labov2006atlas | Only if soda/soft drink is already mentioned. |
| midwestern_bubbler | bubbler | lexical | allowed | allowed/demo-safe | Rare | DART Appendix A; Labov, Ash, and Boberg 2006 | dartAppendixA; labov2006atlas | Only if water fountain is already present. |
| midwestern_kitty_corner | kitty-corner | lexical | allowed | review-only | Rare | Wolfram and Schilling 2016 | wolfram2016american | Needs page check; only for diagonal-location contexts. |
| midwestern_needs_cleaned | needs cleaned | syntactic | allowed | allowed/demo-safe | Yes, where need/passive meaning exists | DART Appendix A; Labov 1998; Yale Grammatical Diversity Project | dartAppendixA; labov1998phonological; yaleGrammaticalDiversity | Do not use unless the anchor has a needs-to-be/needs-ing meaning. |
| midwestern_wants_fixed | wants fixed | syntactic | allowed | review-only | Limited | Labov 1998; Wolfram and Schilling 2016; Yale Grammatical Diversity Project | labov1998phonological; wolfram2016american; yaleGrammaticalDiversity | Needs page check; same passive-participle constraint as needs cleaned. |
| midwestern_come_with | come with | syntactic | allowed | review-only | Rare | Wolfram and Schilling 2016 | wolfram2016american | Needs page check; only if accompaniment is already present. |
| midwestern_alls | alls construction | syntactic | allowed | review-only | Limited | Wolfram and Schilling 2016 | wolfram2016american | Needs page check; preserve all/only summary meaning. |
| midwestern_positive_anymore | positive anymore | discourse | blocked | high-risk/do-not-use | No for current generation | Labov, Ash, and Boberg 2006 | labov2006atlas | Aspect/time meaning is easy to alter. |
| midwestern_tag_right | tag question right | discourse | allowed | allowed/demo-safe | Limited | DART Appendix A; Wolfram and Schilling 2016 | dartAppendixA; wolfram2016american | Can weaken certainty; use only when it does not affect rubric meaning. |
| midwestern_dont_you_know | don't you know | discourse | blocked | high-risk/do-not-use | No | DART Appendix A; Wolfram and Schilling 2016 | dartAppendixA; wolfram2016american | High caricature risk. |
| midwestern_northern_cities_vowel_shift | Northern Cities Vowel Shift spelling | orthographic | blocked | high-risk/do-not-use | No | DART Appendix A; Labov, Ash, and Boberg 2006 | dartAppendixA; labov2006atlas | Phonological feature should not be eye-dialected. |

### Northeastern/New England

| Feature label | Feature text or pattern | Type | Current JSON status | Recommended safety | Written rewrite suitability | Source citation | BibTeX key | Notes |
|---|---|---|---|---|---|---|---|---|
| northeastern_wicked | wicked | lexical | allowed | allowed/demo-safe | Yes, as an intensifier | DART Appendix A; Labov 1998 | dartAppendixA; labov1998phonological | The safest flexible New England feature, but avoid overuse. |
| northeastern_rotary | rotary | lexical | allowed | review-only | Rare | Labov, Ash, and Boberg 2006; DARE | labov2006atlas; dare1985regional | Needs page/entry check; only for traffic-circle contexts. |
| northeastern_tonic | tonic | lexical | allowed | review-only | Rare | Labov, Ash, and Boberg 2006; DARE | labov2006atlas; dare1985regional | Needs page/entry check; only if soda/soft drink appears. |
| northeastern_jimmies | jimmies | lexical | allowed | review-only | Rare | Labov, Ash, and Boberg 2006; DARE | labov2006atlas; dare1985regional | Needs page/entry check; only if sprinkles appear. |
| northeastern_youse | youse / yous | lexical | allowed | review-only | Limited | Wolfram and Schilling 2016 | wolfram2016american | Not New England-specific enough without review. |
| northeastern_packie | packie | lexical | blocked | high-risk/do-not-use | No | Labov, Ash, and Boberg 2006; DARE | labov2006atlas; dare1985regional | Register/context unsuitable for most educational anchors. |
| northeastern_pissah | pissah | lexical | blocked | high-risk/do-not-use | No | DART Appendix A; Labov 1998 | dartAppendixA; labov1998phonological | Inappropriate register and high caricature risk. |
| northeastern_down_the_shore | down the shore | syntactic | allowed | allowed/demo-safe | Rare | DART Appendix A; Labov, Ash, and Boberg 2006 | dartAppendixA; labov2006atlas | Only if shore/coastal travel is already present. |
| northeastern_down_cellar | down cellar | syntactic | allowed | review-only | Rare | Labov, Ash, and Boberg 2006; DARE | labov2006atlas; dare1985regional | Needs page/entry check; only if cellar/basement exists. |
| northeastern_pragmatic_deletion | pragmatic deletion | discourse | allowed | allowed/demo-safe | Limited | DART Appendix A; Labov, Ash, and Boberg 2006 | dartAppendixA; labov2006atlas | Do not remove rubric-relevant material. |
| northeastern_non_rhotic_spelling | non-rhotic spelling | orthographic | blocked | high-risk/do-not-use | No | DART Appendix A; Labov 1998 | dartAppendixA; labov1998phonological | Eye-dialect/caricature risk. |
| northeastern_intrusive_r_spelling | intrusive-r spellings | orthographic | blocked | high-risk/do-not-use | No | Labov 1998; Labov, Ash, and Boberg 2006 | labov1998phonological; labov2006atlas | Avoid phonetic spelling. |
| northeastern_broad_a_spelling | broad a spelling | orthographic | blocked | high-risk/do-not-use | No | DART Appendix A; Labov 1998 | dartAppendixA; labov1998phonological | Avoid accent-spelling parodies. |

### Western American English

| Feature label | Feature text or pattern | Type | Current JSON status | Recommended safety | Written rewrite suitability | Source citation | BibTeX key | Notes |
|---|---|---|---|---|---|---|---|---|
| western_hella | hella | lexical | allowed | allowed/demo-safe | Limited | DART Appendix A; Eckert 2000/2001; Bucholtz et al. 2007 | dartAppendixA; eckert2000linguistic; bucholtz2007hella | Visible but informal; avoid lowering register. |
| western_hecka | hecka | lexical | allowed | review-only | Limited | Eckert 2000/2001; Bucholtz et al. 2007 | eckert2000linguistic; bucholtz2007hella | Needs source confirmation and register review. |
| western_totally | totally | lexical | allowed | allowed/demo-safe | Yes, if emphasis does not change claim strength | DART Appendix A; Eckert 2000/2001; Bucholtz et al. 2007 | dartAppendixA; eckert2000linguistic; bucholtz2007hella | Can change certainty; use lightly. |
| western_for_sure | for sure | lexical | allowed | review-only | Limited | Eckert 2000/2001 | eckert2000linguistic | Needs page check; may strengthen claim. |
| western_you_guys | you guys | lexical | allowed | review-only | Yes, if addressee exists | Wolfram and Schilling 2016 | wolfram2016american | Generic regional feature; not strongly Western without context. |
| western_gonna | gonna | lexical | allowed | allowed/demo-safe | Yes, only for future meaning | DART Appendix A; Eckert 2000/2001 | dartAppendixA; eckert2000linguistic | Keep only where the anchor already encodes future. |
| western_kinda | kinda | lexical | allowed | review-only | Limited | Eckert 2000/2001; D'Arcy 2017 for discourse-pragmatic variation context | eckert2000linguistic; darcy2017like | Can weaken claims; needs careful use. |
| western_freeway_article | freeway article the 5 | syntactic | allowed | review-only | Rare | Eckert 2000/2001 | eckert2000linguistic | Only if a numbered freeway/highway already appears. |
| western_quotative_like | quotative like | syntactic | allowed | allowed/demo-safe | Limited | DART Appendix A; Eckert 2000/2001; D'Arcy 2017 | dartAppendixA; eckert2000linguistic; darcy2017like | Use only for reported speech/thought. |
| western_discourse_like | discourse marker like | discourse | allowed | allowed/demo-safe | Limited | DART Appendix A; Eckert 2000/2001; D'Arcy 2017 | dartAppendixA; eckert2000linguistic; darcy2017like | Avoid filler-like overuse. |
| western_uptalk | uptalk/question intonation | discourse | blocked | high-risk/do-not-use | No for written anchors | DART Appendix A; Eckert 2000/2001 | dartAppendixA; eckert2000linguistic | Prosodic feature, not suitable for plain written rewrites. |
| western_california_vowel_shift_spelling | California Vowel Shift spelling | orthographic | blocked | high-risk/do-not-use | No | DART Appendix A; Eckert 2000/2001 | dartAppendixA; eckert2000linguistic | Avoid phonetic spelling. |

### Appalachian English

| Feature label | Feature text or pattern | Type | Current JSON status | Recommended safety | Written rewrite suitability | Source citation | BibTeX key | Notes |
|---|---|---|---|---|---|---|---|---|
| appalachian_yall | y'all | lexical | allowed | review-only | Yes, if addressee exists | Wolfram and Schilling 2016 | wolfram2016american | Needs page check; overlaps Southern inventory. |
| appalachian_younse | you'uns / younse | lexical | allowed | allowed/demo-safe | Limited | DART Appendix A; Wolfram and Schilling 2016 | dartAppendixA; wolfram2016american | Use only for plural addressee; can be salient. |
| appalachian_afeared | afeared | lexical | allowed | allowed/demo-safe | Rare | DART Appendix A; Wolfram and Schilling 2016; DARE/DSME | dartAppendixA; wolfram2016american; dare1985regional; montgomery2004smoky | Only if fear is already present. |
| appalachian_poke | poke | lexical | allowed | allowed/demo-safe | Rare | DART Appendix A; Wolfram and Schilling 2016; DARE/DSME | dartAppendixA; wolfram2016american; dare1985regional; montgomery2004smoky | Only where bag is already mentioned. |
| appalachian_right_intensifier | right as intensifier | lexical | allowed | review-only | Limited | Wolfram and Schilling 2016 | wolfram2016american | Needs page check; avoid exaggerated rural voice. |
| appalachian_nary | nary | lexical | allowed | review-only | Limited | Wolfram and Schilling 2016; DARE/DSME | wolfram2016american; dare1985regional; montgomery2004smoky | Needs page/entry check; only for existing negation/absence. |
| appalachian_hollow | holler / hollow | lexical | blocked | high-risk/do-not-use | No for current generation | DART Appendix A; Wolfram and Schilling 2016; DARE/DSME | dartAppendixA; wolfram2016american; dare1985regional; montgomery2004smoky | Would add setting details unless the anchor already has them. |
| appalachian_a_prefixing | a-prefixing | syntactic | allowed | allowed/demo-safe | Limited | DART Appendix A; Williams 1992; Wolfram and Christian 1976; Yale Grammatical Diversity Project | dartAppendixA; williams1992appalachian; wolfram1976appalachian; yaleGrammaticalDiversity | Must obey grammatical constraints on -ing forms. |
| appalachian_perfective_done | perfective done | syntactic | allowed | review-only | Yes, if completion exists | Wolfram and Schilling 2016 | wolfram2016american | Needs page check; overlaps Southern/AAE. |
| appalachian_double_modal | double modals | syntactic | allowed | review-only | Yes, if modality exists | Williams 1992; Wolfram and Schilling 2016 | williams1992appalachian; wolfram2016american | Needs page check and modal meaning preservation. |
| appalachian_personal_dative | personal dative | syntactic | allowed | review-only | Limited | Wolfram and Schilling 2016 | wolfram2016american | Needs page check. |
| appalachian_demonstrative_them | demonstrative them | syntactic | allowed | review-only | Limited | Wolfram and Schilling 2016 | wolfram2016american | Needs page check; may be perceived as error by graders. |
| appalachian_used_to_could | buffered modal used to could | syntactic | blocked | high-risk/do-not-use | No for current generation | DART Appendix A; Williams 1992 | dartAppendixA; williams1992appalachian | Strong semantic drift risk. |
| appalachian_hit_generic | hit generic object | orthographic | blocked | high-risk/do-not-use | No | DART Appendix A; Wolfram and Schilling 2016 | dartAppendixA; wolfram2016american | Requires expert linguistic review. |
| appalachian_em | 'em | orthographic | allowed | allowed/demo-safe | Limited | DART Appendix A; Wolfram and Schilling 2016 | dartAppendixA; wolfram2016american | Use only where them already appears or is directly implied. |
| appalachian_narrative_present | narrative present | discourse | blocked | high-risk/do-not-use | No for current generation | DART Appendix A; Labov, Ash, and Boberg 2006 | dartAppendixA; labov2006atlas | Changes tense framing too easily. |

### African American English (AAE)

| Feature label | Feature text or pattern | Type | Current JSON status | Recommended safety | Written rewrite suitability | Source citation | BibTeX key | Notes |
|---|---|---|---|---|---|---|---|---|
| aae_finna | finna | lexical | allowed | allowed/demo-safe | Limited | DART Appendix A; Rickford 1999 | dartAppendixA; rickford1999african | Only for near-future/prospective meaning. |
| aae_hisself | hisself | lexical | allowed | allowed/demo-safe | Limited | DART Appendix A; Rickford 1999 | dartAppendixA; rickford1999african | Only where reflexive pronoun already exists. |
| aae_kinfolk | kinfolk | lexical | allowed | allowed/demo-safe | Rare | DART Appendix A; Rickford 1999 | dartAppendixA; rickford1999african | Do not add family relationships. |
| aae_tryna | tryna | lexical | blocked | high-risk/do-not-use | No for current generation | Rickford 1999 | rickford1999african | Orthographic/reduced form needs review before use. |
| aae_asked_lexical | axed | lexical | blocked | high-risk/do-not-use | No | DART Appendix A; Rickford 1999 | dartAppendixA; rickford1999african | High racialized eye-dialect/phonological marking risk. |
| aae_habitual_be | habitual be | syntactic | allowed | allowed/demo-safe | Yes, only for habitual aspect | DART Appendix A; Labov 1972; Green 2002 | dartAppendixA; labov1972language; green2002african | Do not replace all is/are forms. |
| aae_perfective_done | perfective done | syntactic | allowed | review-only | Yes, if completion/result exists | Rickford 1999; Labov 1972; Green 2002 | rickford1999african; labov1972language; green2002african | Needs page check; semantic condition must be explicit. |
| aae_stressed_bin | stressed BIN | syntactic | blocked | high-risk/do-not-use | No for current generation | Rickford 1999; Labov 1972; Green 2002 | rickford1999african; labov1972language; green2002african | Remote-past meaning is easy to misuse. |
| aae_stressed_stay | stressed STAY | syntactic | blocked | high-risk/do-not-use | No for current generation | Rickford 1999; Dacon 2022 | rickford1999african; dacon2022towards | Needs expert review and repeated/frequent action context. |
| aae_zero_copula | zero/null copula | syntactic | blocked | high-risk/do-not-use | No for current generation | DART Appendix A; Labov 1972; Green 2002 | dartAppendixA; labov1972language; green2002african | High risk if grammatical environments are not controlled. |
| aae_negative_concord | negative concord | syntactic | blocked | high-risk/do-not-use | No for current generation | DART Appendix A; Labov 1972; Green 2002 | dartAppendixA; labov1972language; green2002african | Polarity and grader-bias risk. |
| aae_negative_inversion | negative inversion | syntactic | blocked | high-risk/do-not-use | No for current generation | Labov 1972; Rickford 1999 | labov1972language; rickford1999african | Too likely to change emphasis/readability. |
| aae_third_s_absence | third-person singular -s absence | syntactic | blocked | high-risk/do-not-use | No for current generation | Rickford 1999; Green 2002 | rickford1999african; green2002african | Likely to be treated as an error by graders without careful condition design. |
| aae_demonstrative_them | demonstrative them | syntactic | allowed | review-only | Limited | Rickford 1999; Green 2002 | rickford1999african; green2002african | Needs page check; use only with plural noun phrases. |
| aae_subject_contact_relatives | subject contact relatives | syntactic | blocked | high-risk/do-not-use | No for current generation | Rickford 1999 | rickford1999african | May reduce clarity in student responses. |
| aae_topic_chaining | topic chaining | discourse | allowed | allowed/demo-safe | Limited | DART Appendix A; Labov, Ash, and Boberg 2006 | dartAppendixA; labov2006atlas | Do not remove reasoning while shortening. |
| aae_eye_dialect_spellings | thang/dis/dat spellings | orthographic | blocked | high-risk/do-not-use | No | DART Appendix A; Rickford 1999; Dacon 2022 | dartAppendixA; rickford1999african; dacon2022towards | Keep blocked to avoid racialized caricature. |

## Preliminary Answers To Team Questions

### Which existing features are most defensible right now?

The strongest appendix-facing candidates are the currently allowed features marked `appendix_a_direct` and not high-risk:

- Southern: `y'all`, `fixin' to`, `reckon`, `perfective done`, `double modals`
- Midwestern/North Central: `ope`, `pop`, `bubbler`, `needs cleaned`, `tag question right`
- Northeastern/New England: `wicked`, `down the shore`, `pragmatic deletion`
- Western: `hella`, `totally`, `gonna`, `quotative like`, `discourse marker like`
- Appalachian: `you'uns / younse`, `afeared`, `poke`, `a-prefixing`, `'em`
- AAE: `finna`, `hisself`, `kinfolk`, `habitual be`, `topic chaining`

These still need paper/source page confirmation before publication, but they are the best starting set for a conservative appendix.

### Which should remain review-only?

Features that are currently allowed in JSON but marked `paper_reference_expansion_needs_page_check` should stay review-only for the research appendix until page-level citations are confirmed. This includes several useful generation features such as Southern `all y'all`, Northeastern `rotary`, Western `for sure`, Appalachian `double modals`, and AAE `perfective done`.

### Which are unsafe or high-risk?

The highest-risk categories are:

- phonetic/eye-dialect spellings: non-rhotic spelling, broad-a spelling, California vowel-shift spelling, Northern Cities vowel-shift spelling, thang/dis/dat spellings, axed
- features that can alter tense/aspect/modality: positive anymore, narrative present, stressed BIN, used to could
- features with strong stereotype or register risk: bless your heart, pissah, don't you know, packie
- AAE features requiring precise grammatical licensing: zero copula, negative concord, negative inversion, third-person singular -s absence

### Which dialect families are currently weakest?

Northeastern/New England is weakest for broad written student-response rewriting. Most safe features are narrow lexical substitutions that only fit specific anchor topics, and the phonological features are correctly blocked.

Western is also fragile because many visible features are informal discourse markers or intensifiers. These can make student writing sound less serious if overused.

AAE is well documented, but many of its most recognizable grammatical features are high-risk in this benchmark setting unless tightly constrained and human-reviewed.

### What gaps are preventing stronger generated variants?

- Several dialect families rely on lexical items that only fit rare anchor topics.
- Orthographic and phonological features are mostly unsafe for written rewriting.
- The pipeline currently treats all `allowed_for_generation` features as eligible, even when `citation_status` says `needs_page_check`.
- The prompt asks for 2-4 features, but some anchor/dialect pairs naturally license only one safe feature.
- The prefilter layer does not yet robustly detect unsupported features, blocked features, or original-student-error correction.

### What should be added to the appendix?

The appendix should include:

- this feature matrix, or a cleaned version of it
- a separate table of blocked/high-risk features and why they are excluded
- source/BibTeX entries for every cited feature source
- a note that generated variants remain unvalidated until semantic equivalence, dialect authenticity, and stereotype-risk checks pass
- a page/entry-level source audit column before final publication

## Draft BibTeX

These entries are a working bibliography scaffold. Replace `dartAppendixA` with the official DART paper BibTeX entry when available.

```bibtex
@misc{dartAppendixA,
  author = {{DART project team}},
  title = {DART EMNLP Paper, Appendix A: Dialect Feature Inventory},
  year = {2026},
  note = {Local project source; replace with official paper BibTeX entry before final appendix}
}

@incollection{bernstein2003southern,
  author = {Bernstein, Cynthia},
  title = {Grammatical Features of Southern Speech: Yall, Might Could, and Fixin To},
  booktitle = {English in the Southern United States},
  editor = {Nagle, Stephen J. and Sanders, Sara L.},
  pages = {106--118},
  year = {2003},
  publisher = {Cambridge University Press},
  address = {Cambridge}
}

@book{labov1972language,
  author = {Labov, William},
  title = {Language in the Inner City: Studies in the Black English Vernacular},
  year = {1972},
  publisher = {University of Pennsylvania Press},
  address = {Philadelphia}
}

@book{labov1998phonological,
  author = {Labov, William},
  title = {Phonological Variation and Change in North American English},
  year = {1998},
  note = {Verify bibliographic details against the DART paper reference list before final use}
}

@book{labov2006atlas,
  author = {Labov, William and Ash, Sharon and Boberg, Charles},
  title = {The Atlas of North American English: Phonetics, Phonology and Sound Change},
  year = {2006},
  publisher = {Mouton de Gruyter}
}

@book{rickford1999african,
  author = {Rickford, John R.},
  title = {African American Vernacular English: Features, Evolution, Educational Implications},
  year = {1999},
  publisher = {Blackwell},
  address = {Malden, MA}
}

@book{green2002african,
  author = {Green, Lisa J.},
  title = {African American English: A Linguistic Introduction},
  year = {2002},
  publisher = {Cambridge University Press},
  address = {Cambridge}
}

@book{wolfram1976appalachian,
  author = {Wolfram, Walt and Christian, Donna},
  title = {Appalachian Speech},
  year = {1976},
  publisher = {Center for Applied Linguistics},
  address = {Arlington, VA}
}

@book{wolfram2016american,
  author = {Wolfram, Walt and Schilling, Natalie},
  title = {American English: Dialects and Variation},
  edition = {3},
  year = {2016},
  publisher = {Wiley Blackwell}
}

@book{eckert2000linguistic,
  author = {Eckert, Penelope},
  title = {Linguistic Variation as Social Practice: The Linguistic Construction of Identity in Belten High},
  year = {2000},
  publisher = {Blackwell}
}

@book{darcy2017like,
  author = {D'Arcy, Alexandra},
  title = {Discourse-Pragmatic Variation in Context: Eight Hundred Years of LIKE},
  year = {2017},
  publisher = {John Benjamins},
  address = {Amsterdam and Philadelphia},
  doi = {10.1075/slcs.187}
}

@article{bucholtz2007hella,
  author = {Bucholtz, Mary and Bermudez, Nancy and Fung, Victor and Edwards, Lisa and Vargas, Rosalva},
  title = {Hella Nor Cal or Totally So Cal?: The Perceptual Dialectology of California},
  journal = {Journal of English Linguistics},
  year = {2007},
  volume = {35},
  number = {4},
  pages = {325--352},
  doi = {10.1177/0075424207307780}
}

@book{kurath1949word,
  author = {Kurath, Hans},
  title = {A Word Geography of the Eastern United States},
  year = {1949},
  publisher = {University of Michigan Press}
}

@book{carver1987american,
  author = {Carver, Craig M.},
  title = {American Regional Dialects: A Word Geography},
  year = {1987},
  publisher = {University of Michigan Press}
}

@book{dare1985regional,
  editor = {Cassidy, Frederic G. and Hall, Joan Houston},
  title = {Dictionary of American Regional English},
  year = {1985},
  publisher = {Belknap Press of Harvard University Press},
  address = {Cambridge, MA},
  note = {Six-volume reference work, 1985--2013}
}

@book{montgomery2004smoky,
  author = {Montgomery, Michael B. and Hall, Joseph S.},
  title = {Dictionary of Smoky Mountain English},
  year = {2004},
  publisher = {University of Tennessee Press},
  address = {Knoxville}
}

@inproceedings{dacon2022towards,
  author = {Dacon, Jamell},
  title = {Towards a Deep Multi-layered Dialectal Language Analysis: A Case Study of African-American English},
  booktitle = {Proceedings of the Second Workshop on Bridging Human-Computer Interaction and Natural Language Processing},
  year = {2022},
  publisher = {Association for Computational Linguistics}
}

@misc{yaleGrammaticalDiversity,
  author = {{Yale Grammatical Diversity Project}},
  title = {Yale Grammatical Diversity Project: English in North America},
  howpublished = {\url{https://ygdp.yale.edu/}},
  note = {Consulted for grammatical feature documentation}
}

@misc{harvardDialectSurvey,
  author = {Vaux, Bert and Golder, Scott},
  title = {The Harvard Dialect Survey},
  year = {2003},
  howpublished = {\url{http://dialect.redlog.net/}}
}

@misc{stanfordVoicesCalifornia,
  author = {{Stanford Voices of California}},
  title = {Voices of California},
  howpublished = {\url{https://voicesofcalifornia.stanford.edu/}},
  note = {Consulted for California English documentation}
}
```
