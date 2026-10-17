import copy
import unittest

from db.validation import validate_batch, validate_score


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.row = {"site_id": 1, "source_name": "EIA", "source_url": "https://www.eia.gov/file.xlsx", "retrieved_at": "2026-10-17T12:00:00Z"}
        self.score = {"score": 3.0, "baseline": 4.0, "horizon_hours": 24,
                      "scored_at": "2026-10-17T12:00:00Z", "inputs_observed_at": "2026-10-17T11:00:00Z",
                      "model_version": "experimental-test", "factors": [{"hazard_type": "heat", "contribution": -1.0}]}

    def test_signed_explanation(self):
        validate_score(self.score)

    def test_reject_unexplained_score(self):
        self.score["score"] = 7
        with self.assertRaises(ValueError):
            validate_score(self.score)

    def test_reject_nonfinite_boolean_missing_out_of_range(self):
        for value in (float("nan"), float("inf"), True, None, -1, 11):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_score(dict(self.score, score=value))

    def test_reject_invalid_factor(self):
        for factor in ({"hazard_type": "fake", "contribution": -1}, {"hazard_type": "heat", "contribution": float("nan")}):
            with self.subTest(factor=factor), self.assertRaises(ValueError):
                validate_score(dict(self.score, factors=[factor]))

    def test_empty_batch(self):
        with self.assertRaises(ValueError):
            validate_batch([], ["site_id"])

    def test_missing_required_field(self):
        with self.assertRaises(ValueError):
            validate_batch([self.row], ["county_fips"])

    def test_optional_null_not_zero(self):
        row = dict(self.row, heat_index_f=None)
        validate_batch([row], ["site_id"])
        self.assertIsNone(row["heat_index_f"])

    def test_provenance_required(self):
        for field in ("source_name", "source_url", "retrieved_at"):
            row = copy.deepcopy(self.row)
            row[field] = None
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_batch([row], ["site_id"])

    def test_timezone_required(self):
        self.row["retrieved_at"] = "2026-10-17T12:00:00"
        with self.assertRaises(ValueError):
            validate_batch([self.row], ["site_id"])


if __name__ == "__main__":
    unittest.main()
