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
        self.assertIn("Do not correct the student's spelling", prompt)
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


if __name__ == '__main__':
    unittest.main()




