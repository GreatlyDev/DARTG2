import json
import tempfile
import unittest
from pathlib import Path

from dart_pipeline.assignments import make_balanced_assignments, make_greedy_assignments
from dart_pipeline.inventories import flatten_allowed_features, load_feature_inventory
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


if __name__ == '__main__':
    unittest.main()




