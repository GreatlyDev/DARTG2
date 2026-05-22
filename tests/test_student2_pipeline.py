import json
import subprocess
import sys
import unittest
from pathlib import Path

from dart_pipeline.assignments import make_balanced_assignments, make_greedy_assignments
from dart_pipeline.generation import failed_candidate_ids, extract_output_text, generation_input, is_failed_candidate
from dart_pipeline.inventories import flatten_allowed_features, load_feature_inventory
from dart_pipeline.io_utils import write_jsonl
from dart_pipeline.prefilter import prefilter_candidate
from dart_pipeline.prompts import render_generation_prompt
from dart_pipeline.scoring import candidate_quality_score, score_candidate_row
from dart_pipeline.trace_generation import (
    build_trace_generation_input,
    detect_student_text_corrections,
    parse_model_json,
    traced_candidate_response,
)
from scripts.audit_ricky_candidate_quality import audit_rows
from scripts.retry_rejected_candidates import build_retry_prompt, parse_candidate_ids, target_candidate_ids
from scripts.repair_student_cleanup import repair_cleanup_text


class FeatureInventoryTests(unittest.TestCase):
    def test_inventory_loads_all_six_dialect_families(self):
        inventory = load_feature_inventory(Path('config/features.index.json'))

        self.assertEqual(
            set(inventory),
            {
                'Southern American English',
                'Midwestern/North Central',
                'Northeastern/New England',
                'Western American English',
                'Appalachian English',
                'African American English (AAE)',
            },
        )
        for family, config in inventory.items():
            self.assertEqual(config['dialect_family'], family)
            self.assertIn('primary_references', config)
            self.assertIn('features', config)
            self.assertTrue(all('id' in feature for feature in config['features']))
            self.assertGreater(len(flatten_allowed_features(config)), 0, family)

    def test_prompt_rendering_includes_anchor_and_inventory_constraints(self):
        inventory = load_feature_inventory(Path('config/features.index.json'))
        prompt = render_generation_prompt(
            template_path=Path('prompts/generation_v1.txt'),
            assignment_prompt='Explain why recycling matters.',
            anchor_response='Recycling matters because it reduces landfill waste.',
            dialect_family='Southern American English',
            feature_config=inventory['Southern American English'],
        )

        self.assertIn('Explain why recycling matters.', prompt)
        self.assertIn('Recycling matters because it reduces landfill waste.', prompt)
        self.assertIn('Southern American English', prompt)
        self.assertIn('Use only documented features', prompt)
        self.assertIn("Do not correct, normalize, smooth, or improve the student's spelling", prompt)
        self.assertIn('controlled dialect rewrite', prompt)
        self.assertIn('or one appended marker', prompt)
        self.assertIn('Use 2-5 approved target-dialect feature placements', prompt)
        self.assertIn('Prefer a mix of distinct approved feature entries', prompt)
        self.assertIn('Low-score and low-band responses must stay low-score/low-band', prompt)
        self.assertNotIn('{FEATURE_INVENTORY}', prompt)


class AssignmentTests(unittest.TestCase):
    def setUp(self):
        self.anchors = [
            {'anchor_id': 'A1', 'source_corpus': 'ASAP-AES', 'score_band': 'low', 'domain': 'explanation'},
            {'anchor_id': 'A2', 'source_corpus': 'ASAP-AES', 'score_band': 'low', 'domain': 'explanation'},
            {'anchor_id': 'B1', 'source_corpus': 'TOEFL11', 'score_band': 'mid', 'domain': 'argumentation'},
            {'anchor_id': 'C1', 'source_corpus': 'Synthetic', 'score_band': 'high', 'domain': 'description'},
        ]
        self.dialects = ['Southern American English', 'Appalachian English']

    def test_greedy_assignments_preserve_input_order_and_cycle_dialects(self):
        assignments = make_greedy_assignments(self.anchors, self.dialects, candidates_per_pair=3)

        self.assertEqual([row['anchor_id'] for row in assignments], ['A1', 'A2', 'B1', 'C1'])
        self.assertEqual([row['dialect_family'] for row in assignments], [
            'Southern American English',
            'Appalachian English',
            'Southern American English',
            'Appalachian English',
        ])
        self.assertTrue(all(row['target_candidates'] == 3 for row in assignments))
        self.assertTrue(all(row['assignment_strategy'] == 'greedy' for row in assignments))

    def test_balanced_assignments_mix_available_strata_before_repeating(self):
        assignments = make_balanced_assignments(self.anchors, self.dialects, candidates_per_pair=3)

        self.assertEqual(len(assignments), 4)
        self.assertEqual(assignments[0]['anchor_id'], 'A1')
        self.assertEqual(assignments[1]['anchor_id'], 'B1')
        self.assertEqual(assignments[2]['anchor_id'], 'C1')
        self.assertEqual(assignments[3]['anchor_id'], 'A2')
        self.assertTrue(all(row['assignment_strategy'] == 'balanced' for row in assignments))


class GenerationTests(unittest.TestCase):
    def test_extract_output_text_uses_response_shortcut_when_available(self):
        response = {'output_text': '  Candidate text.  '}

        self.assertEqual(extract_output_text(response), 'Candidate text.')

    def test_extract_output_text_falls_back_to_output_content(self):
        response = {
            'output': [
                {
                    'type': 'message',
                    'content': [
                        {'type': 'output_text', 'text': 'First part.'},
                        {'type': 'output_text', 'text': 'Second part.'},
                    ],
                }
            ]
        }

        self.assertEqual(extract_output_text(response), 'First part.\nSecond part.')

    def test_generation_input_adds_candidate_attempt_note(self):
        job = {'generation_prompt': 'Base prompt.', 'candidate_index': 2}

        rendered = generation_input(job, total_candidates=3)

        self.assertIn('Base prompt.', rendered)
        self.assertIn('Candidate attempt: 2 of 3.', rendered)

    def test_failed_candidate_detection_catches_literal_fail_outputs(self):
        rows = [
            {'candidate_id': 'A1_Southern_1', 'candidate_response': 'Valid response.', 'generation_status': 'demo_unvalidated'},
            {'candidate_id': 'A1_Southern_2', 'candidate_response': 'FAIL', 'generation_status': 'demo_unvalidated'},
            {'candidate_id': 'A1_Southern_3', 'raw_output': 'FAIL', 'generation_status': 'demo_unvalidated'},
            {'candidate_id': 'A1_Southern_4', 'candidate_response': '', 'generation_status': 'model_fail'},
        ]

        self.assertFalse(is_failed_candidate(rows[0]))
        self.assertEqual(
            failed_candidate_ids(rows),
            {'A1_Southern_2', 'A1_Southern_3', 'A1_Southern_4'},
        )

    def test_generate_candidate_record_tracks_usage_tokens_and_estimated_cost(self):
        class FakeClient:
            model = 'gpt-4o'

            def create(self, prompt):
                return {
                    'id': 'resp_test',
                    'output_text': 'I reckon recycling matters.',
                    'usage': {'input_tokens': 1000, 'output_tokens': 100},
                }

        from dart_pipeline.generation import generate_candidate_record

        record = generate_candidate_record(
            {
                'job_id': 'A1_Southern_1',
                'anchor_id': 'A1',
                'dialect_family': 'Southern American English',
                'candidate_index': 1,
                'generation_prompt': 'Rewrite this.',
                'prompt_version': 'generation_v1',
            },
            FakeClient(),
            generation_status='demo_unvalidated',
        )

        self.assertEqual(record['tokens_in'], 1000)
        self.assertEqual(record['tokens_out'], 100)
        self.assertEqual(record['cost_usd'], 0.0035)

    def test_parse_model_json_handles_fenced_json(self):
        parsed, error = parse_model_json('```json\n{"southern_output": "I reckon it matters."}\n```')

        self.assertIsNone(error)
        self.assertEqual(parsed, {"southern_output": "I reckon it matters."})

    def test_traced_candidate_response_uses_family_output_key(self):
        row = {
            'dialect_family': 'southern',
            'parsed_output': {'southern_output': 'I reckon it matters.'},
            'raw_output': 'raw fallback',
        }

        self.assertEqual(traced_candidate_response(row), 'I reckon it matters.')

    def test_detect_student_text_corrections_flags_unlicensed_spelling_cleanup(self):
        anchor = 'I was being pationt so I cam text my friends on my snowmoble.'
        candidate = 'I was being patient so I can text my friends on my snowmobile.'
        result = detect_student_text_corrections(
            anchor,
            candidate,
            applied_features=[],
            known_student_forms={'pationt', 'cam', 'snowmoble'},
        )

        self.assertEqual(
            result,
            ['cam -> can', 'pationt -> patient', 'snowmoble -> snowmobile'],
        )

    def test_trace_generation_input_preserves_student_spelling_rule(self):
        prompt = build_trace_generation_input(
            template_path=Path('prompts/inventory_trace_v1.txt'),
            dialect_family='Southern American English',
            anchor_text='I was being pationt.',
            feature_config={'features': []},
        )

        self.assertIn('I was being pationt.', prompt)
        self.assertIn('Do not correct spelling, grammar, punctuation, capitalization, or wording', prompt)
        self.assertIn('Southern American English', prompt)


class FinalAnchorFormatTests(unittest.TestCase):
    def test_final_student1_csv_shape_uses_essay_id_text_and_dataset(self):
        anchors = [
            {
                'essay_id': '764',
                'dataset': 'ASAP-AES',
                'text': 'Student 1 final anchor text.',
                'score_band': 'HIGH',
            }
        ]
        assignments = make_greedy_assignments(anchors, ['Southern American English'], candidates_per_pair=3)

        self.assertEqual(assignments[0]['anchor_id'], '764')
        self.assertEqual(assignments[0]['source_corpus'], 'ASAP-AES')


class CandidateReportTests(unittest.TestCase):
    def test_render_candidate_report_groups_candidates_with_anchor_text(self):
        root = Path('data/test_tmp/candidate_report')
        anchors_path = root / 'anchors.jsonl'
        candidates_path = root / 'candidates.jsonl'
        output_path = root / 'report.md'
        write_jsonl(
            anchors_path,
            [
                {
                    'anchor_id': 'A1',
                    'anchor_response': 'Original student response.',
                    'score_band': 'low',
                    'normalized_score': '2.2',
                }
            ],
        )
        write_jsonl(
            candidates_path,
            [
                {
                    'candidate_id': 'A1_Southern_1',
                    'anchor_id': 'A1',
                    'dialect_family': 'Southern American English',
                    'candidate_index': 1,
                    'generation_status': 'demo_unvalidated',
                    'model': 'test-model',
                    'candidate_response': 'Generated candidate response.',
                }
            ],
        )

        subprocess.run(
            [
                sys.executable,
                'scripts/render_candidate_report.py',
                '--anchors',
                str(anchors_path),
                '--candidates',
                str(candidates_path),
                '--output',
                str(output_path),
            ],
            check=True,
        )

        report = output_path.read_text(encoding='utf-8')
        self.assertIn('# DART Candidate Variant Review Report', report)
        self.assertIn('Original student response.', report)
        self.assertIn('Generated candidate response.', report)
        self.assertIn('demo_unvalidated', report)

    def test_render_candidate_report_preserves_anchor_text_verbatim(self):
        root = Path('data/test_tmp/candidate_report_verbatim')
        anchors_path = root / 'anchors.jsonl'
        candidates_path = root / 'candidates.jsonl'
        output_path = root / 'report.md'
        anchor = 'it describs How the famialy let people in their house  and mybe it is nice.'
        write_jsonl(
            anchors_path,
            [
                {
                    'anchor_id': 'A1',
                    'anchor_response': anchor,
                    'score_band': 'low',
                }
            ],
        )
        write_jsonl(
            candidates_path,
            [
                {
                    'candidate_id': 'A1_Southern_1',
                    'anchor_id': 'A1',
                    'dialect_family': 'Southern American English',
                    'candidate_index': 1,
                    'generation_status': 'demo_unvalidated',
                    'model': 'gpt-4o',
                    'candidate_response': 'it describs How the famialy let folks in their house  and mybe it is nice.',
                }
            ],
        )

        subprocess.run(
            [
                sys.executable,
                'scripts/render_candidate_report.py',
                '--anchors',
                str(anchors_path),
                '--candidates',
                str(candidates_path),
                '--output',
                str(output_path),
            ],
            check=True,
        )

        report = output_path.read_text(encoding='utf-8')
        self.assertIn(anchor, report)
        self.assertNotIn('describes', report)
        self.assertNotIn('family let people', report)
        self.assertNotIn('maybe', report)

    def test_render_trace_comparison_flags_spelling_corrections(self):
        root = Path('data/test_tmp/trace_comparison')
        trace_path = root / 'trace.jsonl'
        output_path = root / 'comparison.md'
        write_jsonl(
            trace_path,
            [
                {
                    'anchor_id': 'A1',
                    'dialect_family': 'aae',
                    'anchor_text': 'I was being pationt so I cam text my friends.',
                    'parsed_output': {
                        'aae_output': 'I was being patient so I can text my friends.',
                        'applied_features': [],
                        'rejected_candidates': [{'id': 'aae_finna', 'reason': 'no near-future intent'}],
                        'notes': 'No allowed feature was licensed by this anchor.',
                    },
                    'detected_student_corrections': ['cam -> can', 'pationt -> patient'],
                    'generation_status': 'ok',
                }
            ],
        )

        subprocess.run(
            [
                sys.executable,
                'scripts/render_trace_comparison.py',
                '--traces',
                str(trace_path),
                '--output',
                str(output_path),
            ],
            check=True,
        )

        report = output_path.read_text(encoding='utf-8')
        self.assertIn('# DART Trace Comparison Report', report)
        self.assertIn('A1', report)
        self.assertIn('pationt -> patient', report)
        self.assertIn('aae_finna', report)

    def test_render_trace_comparison_can_compute_spelling_corrections(self):
        root = Path('data/test_tmp/trace_comparison_computed')
        trace_path = root / 'trace.jsonl'
        output_path = root / 'comparison.md'
        write_jsonl(
            trace_path,
            [
                {
                    'anchor_id': 'A1',
                    'dialect_family': 'aae',
                    'anchor_text': 'I was being pationt so I cam text my friends.',
                    'parsed_output': {
                        'aae_output': 'I was being patient so I can text my friends.',
                        'applied_features': [],
                        'rejected_candidates': [],
                    },
                    'generation_status': 'ok',
                }
            ],
        )

        subprocess.run(
            [
                sys.executable,
                'scripts/render_trace_comparison.py',
                '--traces',
                str(trace_path),
                '--output',
                str(output_path),
                '--known-student-forms',
                'pationt,cam',
            ],
            check=True,
        )

        report = output_path.read_text(encoding='utf-8')
        self.assertIn('cam -> can', report)
        self.assertIn('pationt -> patient', report)


class PrefilterTests(unittest.TestCase):
    def test_prefilter_rejects_probable_student_spelling_cleanup(self):
        result = prefilter_candidate(
            anchor_response='I was being pationt so I cam text my friends.',
            candidate_text='I was being patient so I can text my friends.',
            feature_config={'features': []},
            length_tolerance=1.0,
            min_detected_features=0,
        )

        self.assertFalse(result.passed_prefilter)
        self.assertIn('student_text_correction', result.rejection_reasons)
        self.assertEqual(result.student_text_corrections, ['cam -> can', 'pationt -> patient'])

    def test_prefilter_does_not_flag_allowed_dialect_marker_as_cleanup(self):
        result = prefilter_candidate(
            anchor_response='I think the author is going to show hope.',
            candidate_text='I reckon the author is gonna show hope.',
            feature_config={
                'features': [
                    {'feature': 'reckon', 'allowed_for_generation': True},
                    {'feature': 'gonna', 'allowed_for_generation': True},
                ]
            },
            length_tolerance=1.0,
            min_detected_features=0,
        )

        self.assertNotIn('student_text_correction', result.rejection_reasons)
        self.assertEqual(result.student_text_corrections, [])

    def test_prefilter_detects_feature_surface_markers_from_inventory_labels(self):
        result = prefilter_candidate(
            anchor_response='The author wants the reader to see the connection.',
            candidate_text='The author wants the reader to see the connection, right?',
            feature_config={
                'features': [
                    {
                        'id': 'midwestern_tag_right',
                        'feature': 'tag question right',
                        'allowed_for_generation': True,
                    },
                ]
            },
            length_tolerance=1.0,
            min_detected_features=1,
        )

        self.assertTrue(result.passed_prefilter)
        self.assertEqual(result.detected_features, ['right'])

    def test_prefilter_can_accept_one_documented_feature_for_weak_anchor_pair(self):
        result = prefilter_candidate(
            anchor_response='I was being pationt when I was waiting.',
            candidate_text='Ope, I was being pationt when I was waiting.',
            feature_config={
                'features': [
                    {
                        'id': 'midwestern_ope',
                        'feature': 'ope',
                        'allowed_for_generation': True,
                    },
                ]
            },
            length_tolerance=1.0,
            min_detected_features=1,
        )

        self.assertTrue(result.passed_prefilter)
        self.assertEqual(result.detected_features, ['ope'])

    def test_prefilter_uses_explicit_detection_markers(self):
        result = prefilter_candidate(
            anchor_response='The character was very happy.',
            candidate_text='The character was mad happy.',
            feature_config={
                'features': [
                    {
                        'id': 'northeastern_mad_intensifier',
                        'feature': 'mad as intensifier',
                        'detection_markers': ['mad'],
                        'allowed_for_generation': True,
                    },
                ]
            },
            length_tolerance=1.0,
            min_detected_features=1,
        )

        self.assertTrue(result.passed_prefilter)
        self.assertEqual(result.detected_features, ['mad'])

    def test_prefilter_detects_aae_habitual_be_pattern(self):
        result = prefilter_candidate(
            anchor_response='The students are working after school.',
            candidate_text='The students be working after school.',
            feature_config={
                'features': [
                    {
                        'id': 'aae_habitual_be',
                        'feature': 'habitual be',
                        'allowed_for_generation': True,
                    },
                ]
            },
            length_tolerance=1.0,
            min_detected_features=1,
        )

        self.assertTrue(result.passed_prefilter)
        self.assertEqual(result.detected_features, ['habitual be'])
        self.assertEqual(result.feature_realization_count, 1)

    def test_prefilter_does_not_detect_markers_inside_other_words(self):
        result = prefilter_candidate(
            anchor_response='The passage mentions Madison and a popular activity.',
            candidate_text='The passage mentions Madison and a popular activity.',
            feature_config={
                'features': [
                    {
                        'id': 'northeastern_mad_intensifier',
                        'feature': 'mad as intensifier',
                        'detection_markers': ['mad'],
                        'allowed_for_generation': True,
                    },
                    {
                        'id': 'midwestern_pop',
                        'feature': 'pop',
                        'detection_markers': ['pop'],
                        'allowed_for_generation': True,
                    },
                ]
            },
            length_tolerance=1.0,
            min_detected_features=0,
        )

        self.assertEqual(result.detected_features, [])
        self.assertEqual(result.feature_realization_count, 0)

    def test_prefilter_counts_multiple_feature_realizations(self):
        result = prefilter_candidate(
            anchor_response='I think the students are working and the computers are helping.',
            candidate_text='I reckon the students be working and the computers be helping.',
            feature_config={
                'features': [
                    {
                        'id': 'southern_reckon',
                        'feature': 'reckon',
                        'allowed_for_generation': True,
                    },
                    {
                        'id': 'aae_habitual_be',
                        'feature': 'habitual be',
                        'allowed_for_generation': True,
                    },
                ]
            },
            length_tolerance=1.0,
            min_detected_features=3,
        )

        self.assertTrue(result.passed_prefilter)
        self.assertEqual(result.feature_realization_count, 3)

    def test_prefilter_script_uses_anchor_file_and_candidate_response(self):
        root = Path('data/test_tmp/prefilter_script')
        anchors_path = root / 'anchors.jsonl'
        candidates_path = root / 'candidates.jsonl'
        output_path = root / 'prefiltered.jsonl'
        write_jsonl(
            anchors_path,
            [
                {
                    'anchor_id': 'A1',
                    'anchor_response': 'I was being pationt so I cam text my friends.',
                }
            ],
        )
        write_jsonl(
            candidates_path,
            [
                {
                    'candidate_id': 'A1_AAE_1',
                    'anchor_id': 'A1',
                    'dialect_family': 'African American English (AAE)',
                    'candidate_response': 'I was being patient so I can text my friends.',
                }
            ],
        )

        subprocess.run(
            [
                sys.executable,
                'scripts/prefilter_candidates.py',
                '--anchors',
                str(anchors_path),
                '--candidates',
                str(candidates_path),
                '--output',
                str(output_path),
                '--length-tolerance',
                '1.0',
                '--min-features',
                '0',
            ],
            check=True,
        )

        result = json.loads(output_path.read_text(encoding='utf-8').splitlines()[0])
        self.assertFalse(result['passed_prefilter'])
        self.assertIn('student_text_correction', result['rejection_reasons'])
        self.assertEqual(result['student_text_corrections'], ['cam -> can', 'pationt -> patient'])


class ScoringAndCurationTests(unittest.TestCase):
    def test_score_candidate_row_adds_similarity_and_cleanup_flags(self):
        row = {
            'anchor_response': 'I was being pationt so I cam text my friends.',
            'candidate_response': 'I was being patient so I can text my friends.',
            'generation_status': 'demo_unvalidated',
        }

        scored = score_candidate_row(row)

        self.assertIn('similarity_scores', scored)
        self.assertGreater(scored['composite_change_score'], 0)
        self.assertEqual(scored['student_text_corrections'], ['cam -> can', 'pationt -> patient'])
        self.assertIn('student_text_correction', scored['rejection_reasons'])
        self.assertFalse(scored['passed_quality_filter'])

    def test_score_candidate_row_does_not_flag_allowed_demonstrative_them(self):
        row = {
            'anchor_response': 'The hills are short.',
            'candidate_response': 'Them hills are short.',
            'generation_status': 'demo_unvalidated',
            'rejection_reasons': ['student_text_correction'],
        }

        scored = score_candidate_row(
            row,
            min_word_count=1,
            allowed_feature_markers={'them'},
        )

        self.assertEqual(scored['student_text_corrections'], [])
        self.assertTrue(scored['passed_quality_filter'])

    def test_candidate_quality_score_rejects_cleanup_even_when_other_metrics_pass(self):
        row = score_candidate_row(
            {
                'anchor_response': 'I was being pationt so I cam text my friends.',
                'candidate_response': 'I reckon I was being patient so I can text my friends.',
                'generation_status': 'demo_unvalidated',
            },
            min_change=0.01,
            max_length_delta=1.0,
            min_word_count=1,
        )

        usable, reasons = candidate_quality_score(row)

        self.assertFalse(usable)
        self.assertIn('student_text_correction', reasons)

    def test_candidate_with_documented_feature_can_pass_quality_filter(self):
        row = score_candidate_row(
            {
                'anchor_response': 'The author wants the reader to see the connection.',
                'candidate_response': 'The author wants the reader to see the connection, right?',
                'generation_status': 'demo_unvalidated',
            },
            min_word_count=1,
        )

        self.assertTrue(row['passed_quality_filter'])
        self.assertEqual(row['rejection_reasons'], [])

    def test_exact_match_still_fails_quality_filter(self):
        row = score_candidate_row(
            {
                'anchor_response': 'The author wants the reader to see the connection.',
                'candidate_response': 'The author wants the reader to see the connection.',
                'generation_status': 'demo_unvalidated',
            },
            min_word_count=1,
        )

        self.assertFalse(row['passed_quality_filter'])
        self.assertIn('insufficient_change', row['rejection_reasons'])

    def test_score_candidates_script_reattaches_anchor_text_before_scoring(self):
        root = Path('data/test_tmp/score_candidates_script')
        anchors_path = root / 'anchors.jsonl'
        candidates_path = root / 'prefiltered.jsonl'
        output_path = root / 'scored.jsonl'
        write_jsonl(
            anchors_path,
            [
                {
                    'anchor_id': 'A1',
                    'anchor_response': 'I was being pationt so I cam text my friends.',
                }
            ],
        )
        write_jsonl(
            candidates_path,
            [
                {
                    'candidate_id': 'A1_AAE_1',
                    'anchor_id': 'A1',
                    'dialect_family': 'African American English (AAE)',
                    'candidate_response': 'I was being patient so I can text my friends.',
                    'generation_status': 'demo_unvalidated',
                    'rejection_reasons': ['student_text_correction'],
                }
            ],
        )

        subprocess.run(
            [
                sys.executable,
                'scripts/score_candidates.py',
                '--anchors',
                str(anchors_path),
                '--candidates',
                str(candidates_path),
                '--output',
                str(output_path),
                '--min-change',
                '0.01',
                '--max-length-delta',
                '1.0',
                '--min-word-count',
                '1',
            ],
            check=True,
        )

        result = json.loads(output_path.read_text(encoding='utf-8').splitlines()[0])
        self.assertEqual(result['anchor_response'], 'I was being pationt so I cam text my friends.')
        self.assertEqual(result['student_text_corrections'], ['cam -> can', 'pationt -> patient'])
        self.assertFalse(result['passed_quality_filter'])

    def test_retry_prompt_names_cleanup_violations_and_requires_anchor_preservation(self):
        prompt = build_retry_prompt(
            {
                'generation_prompt': 'Base prompt text.',
            },
            {
                'candidate_id': 'A1_AAE_1',
                'candidate_response': 'I was being patient so I can text my friends.',
                'rejection_reasons': ['student_text_correction'],
                'student_text_corrections': ['cam -> can', 'pationt -> patient'],
            },
        )

        self.assertIn('Base prompt text.', prompt)
        self.assertIn('pationt -> patient', prompt)
        self.assertIn('cam -> can', prompt)
        self.assertIn('Start again from the anchor response', prompt)
        self.assertIn('Do not correct, normalize, smooth, or improve', prompt)

    def test_target_candidate_ids_filters_by_rejection_reason(self):
        rows = [
            {'candidate_id': 'A', 'rejection_reasons': ['student_text_correction']},
            {'candidate_id': 'B', 'rejection_reasons': ['insufficient_change']},
            {'candidate_id': 'C', 'passed_quality_filter': True, 'rejection_reasons': []},
        ]

        self.assertEqual(target_candidate_ids(rows, {'student_text_correction'}), {'A'})
        self.assertEqual(target_candidate_ids(rows, {'student_text_correction', 'insufficient_change'}), {'A', 'B'})

    def test_audit_flags_single_detected_feature_for_targeted_retry(self):
        rows = [
            {
                'anchor_id': 'A1',
                'candidate_id': 'A1_Western_1',
                'candidate_index': 1,
                'dialect_family': 'Western American English',
                'anchor_response': 'I think the answer is clear and the story matters.',
                'candidate_response': 'I think the answer is clear for sure and the story matters.',
                'detected_features': ['for sure'],
                'passed_quality_filter': True,
                'rejection_reasons': [],
            }
        ]

        audited = audit_rows(rows, duplicate_threshold=0.985)

        self.assertFalse(audited[0]['passed_quality_filter'])
        self.assertIn('single_detected_feature', audited[0]['rejection_reasons'])

    def test_audit_flags_common_feature_only_for_targeted_retry(self):
        rows = [
            {
                'anchor_id': 'A1',
                'candidate_id': 'A1_Western_1',
                'candidate_index': 1,
                'dialect_family': 'Western American English',
                'anchor_response': 'I am going to explain the reason because the passage shows the plan.',
                'candidate_response': 'I am gonna explain the reason because the passage for sure shows the plan.',
                'detected_features': ['gonna', 'for sure'],
                'passed_quality_filter': True,
                'rejection_reasons': [],
            }
        ]

        audited = audit_rows(rows, duplicate_threshold=0.985)

        self.assertFalse(audited[0]['passed_quality_filter'])
        self.assertIn('common_feature_only', audited[0]['rejection_reasons'])

    def test_retry_prompt_for_feature_diversity_rejections_preserves_meaning_first(self):
        prompt = build_retry_prompt(
            {
                'generation_prompt': 'Base prompt text.',
                'candidate_index': 2,
            },
            {
                'candidate_id': 'A1_Western_2',
                'candidate_index': 2,
                'candidate_response': 'I am gonna explain the reason because the passage for sure shows the plan.',
                'detected_features': ['gonna', 'for sure'],
                'rejection_reasons': ['common_feature_only', 'single_detected_feature', 'surface_change_below_minimum'],
                'student_text_corrections': [],
            },
        )

        self.assertIn('FEATURE DIVERSITY RETRY', prompt)
        self.assertIn('Prefer a rewrite with at least two distinct approved feature placements', prompt)
        self.assertIn('5%-25% surface-change band', prompt)
        self.assertIn('Do not force a second feature', prompt)
        self.assertIn('semantic drift', prompt)

    def test_audit_flags_surface_change_below_dacon_minimum(self):
        anchor_words = [f'word{chr(97 + i % 26)}{chr(97 + i // 26)}' for i in range(50)]
        candidate_words = list(anchor_words)
        candidate_words[0] = 'reckon'
        rows = [
            {
                'anchor_id': 'A1',
                'candidate_id': 'A1_Southern_1',
                'candidate_index': 1,
                'dialect_family': 'Southern American English',
                'anchor_response': ' '.join(anchor_words),
                'candidate_response': ' '.join(candidate_words),
                'detected_features': ['reckon', "y'all"],
                'feature_realization_count': 2,
                'passed_quality_filter': True,
                'rejection_reasons': [],
            }
        ]

        audited = audit_rows(rows, duplicate_threshold=0.985)

        self.assertFalse(audited[0]['passed_quality_filter'])
        self.assertIn('surface_change_below_minimum', audited[0]['rejection_reasons'])
        self.assertLess(audited[0]['surface_change_ratio'], 0.05)

    def test_audit_flags_surface_change_above_dacon_upper_bound(self):
        anchor_words = [f'word{chr(97 + i % 26)}{chr(97 + i // 26)}' for i in range(30)]
        candidate_words = [f'new{chr(97 + i % 26)}{chr(97 + i // 26)}' for i in range(30)]
        rows = [
            {
                'anchor_id': 'A1',
                'candidate_id': 'A1_Western_1',
                'candidate_index': 1,
                'dialect_family': 'Western American English',
                'anchor_response': ' '.join(anchor_words),
                'candidate_response': ' '.join(candidate_words),
                'detected_features': ['for sure', 'gonna', 'like'],
                'feature_realization_count': 3,
                'passed_quality_filter': True,
                'rejection_reasons': [],
            }
        ]

        audited = audit_rows(rows, duplicate_threshold=0.985)

        self.assertFalse(audited[0]['passed_quality_filter'])
        self.assertIn('surface_change_above_upper_bound', audited[0]['rejection_reasons'])
        self.assertGreater(audited[0]['surface_change_ratio'], 0.25)

    def test_audit_prefers_three_features_for_long_anchors(self):
        anchor_words = [f'word{chr(97 + i % 26)}{chr(97 + i // 26)}' for i in range(90)]
        candidate_words = list(anchor_words)
        for index in range(10):
            candidate_words[index] = f'change{chr(97 + index)}'
        rows = [
            {
                'anchor_id': 'A1',
                'candidate_id': 'A1_Southern_1',
                'candidate_index': 1,
                'dialect_family': 'Southern American English',
                'anchor_response': ' '.join(anchor_words),
                'candidate_response': ' '.join(candidate_words),
                'detected_features': ['reckon', "y'all"],
                'feature_realization_count': 2,
                'passed_quality_filter': True,
                'rejection_reasons': [],
            }
        ]

        audited = audit_rows(rows, duplicate_threshold=0.985)

        self.assertFalse(audited[0]['passed_quality_filter'])
        self.assertIn('long_anchor_low_feature_count', audited[0]['rejection_reasons'])

    def test_parse_candidate_ids_trims_allowlist_values(self):
        self.assertEqual(parse_candidate_ids(' A, B ,,C '), {'A', 'B', 'C'})
        self.assertEqual(parse_candidate_ids(None), set())

    def test_repair_cleanup_text_reverts_only_detected_cleanup_span(self):
        anchor = 'I have no control over ther car but I can try.'
        candidate = 'I have no control over the car but I can try, right?'

        repaired, repairs = repair_cleanup_text(anchor, candidate, ['ther -> the'])

        self.assertEqual(repaired, 'I have no control over ther car but I can try, right?')
        self.assertEqual(repairs, ['ther -> the'])


if __name__ == '__main__':
    unittest.main()




