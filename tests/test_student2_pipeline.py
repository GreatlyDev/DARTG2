import json
import subprocess
import sys
import unittest
from pathlib import Path

from dart_pipeline.assignments import make_balanced_assignments, make_greedy_assignments
from dart_pipeline.generation import extract_output_text, generation_input
from dart_pipeline.inventories import flatten_allowed_features, load_feature_inventory
from dart_pipeline.io_utils import write_jsonl
from dart_pipeline.prompts import render_generation_prompt


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
                'African American Vernacular English (AAVE)',
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
        self.assertIn('# Stage 1 Demo Candidates', report)
        self.assertIn('Original student response.', report)
        self.assertIn('Generated candidate response.', report)
        self.assertIn('demo_unvalidated', report)


if __name__ == '__main__':
    unittest.main()




