import json
from pathlib import Path
import unittest
from get_data.weather_values import heat_index_f

class HeatInterpretationTests(unittest.TestCase):
    def test_documented_missingness_cases_and_boundaries(self):
        cases=json.loads((Path(__file__).resolve().parents[1]/'generated/heat-index-cases.json').read_text())['cases']
        for row in cases:self.assertEqual(heat_index_f(row['temperature_f'],row['relative_humidity_pct']),row['heat_index_f'])
        self.assertAlmostEqual(heat_index_f(90,60),99.6777179,places=5)
        self.assertIsNotNone(heat_index_f(80,100));self.assertIsNotNone(heat_index_f(112,60))
        self.assertIsNone(heat_index_f(112.01,60));self.assertIsNone(heat_index_f(79.99,100))
        with self.assertRaises(ValueError):heat_index_f(90,101)
