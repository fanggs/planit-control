"""Tests use clearly synthetic generators plus the shipped real catalog."""
import copy
from datetime import date
import json
from pathlib import Path
import random
import tempfile
import unittest
from zipfile import ZipFile

from openpyxl import Workbook

from get_data.eia import county_key, discover_latest, group_plants, read_counties, read_operating
from get_data.sites import DEMO_PLANTS, REGIONS, enrich_plants, select_sites, validate_sites

GENERATED = Path(__file__).resolve().parents[1] / "generated"


def generator(**overrides):
    return {"Plant ID": 123, "Plant Name": "Synthetic Test Plant", "Plant State": "FL",
            "County": "Miami Dade", "Entity Name": "Test Utility", "Generator ID": "A",
            "Technology": "Test Technology", "Status": "(OP) Operating",
            "Latitude": 25.4, "Longitude": -80.3, **overrides}


class EIATests(unittest.TestCase):
    def test_discovers_newest_published_link_not_page_order(self):
        html = '<a href="xls/july_generator2026.xlsx">XLS</a><a href="xls/august_generator2026.xlsx">XLS</a><a href="xls/january_generator2027.xlsx">XLS</a>'
        url, vintage = discover_latest(html, as_of=date(2026, 10, 17))
        self.assertTrue(url.endswith("august_generator2026.xlsx"))
        self.assertEqual(vintage, "2026-08")

    def test_discovery_rejects_missing_or_external_links(self):
        for html in ("maintenance", '<a href="https://example.org/august_generator2026.xlsx">XLS</a>'):
            with self.subTest(html=html), self.assertRaises(ValueError):
                discover_latest(html)

    def test_groups_generators_once_and_summarizes_types(self):
        rows, counts, rejected = group_plants([generator(), generator(**{"Generator ID": "B", "Technology": "Second Technology"})])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["site_id"], 123)
        self.assertEqual(rows[0]["plant_type"], "Second Technology; Test Technology")
        self.assertEqual(counts["generator_rows"], 2)
        self.assertEqual(rejected, [])

    def test_excludes_standby_and_out_of_service_generators(self):
        for status in ("(SB) Standby/Backup: available for service but not normally used", "(OA) Out of service", "(OS) Out of service"):
            with self.subTest(status=status):
                rows, _, _ = group_plants([generator(**{"Status": status})])
                self.assertEqual(rows, [])

    def test_duplicate_generator_is_not_double_counted(self):
        rows, _, rejected = group_plants([generator(), generator()])
        self.assertEqual(rows, [])
        self.assertEqual(rejected[0]["reason"], "duplicate_or_missing_generator_id")

    def test_conflicting_plant_identity_or_location_is_rejected(self):
        for changes in ({"Plant Name": "Different"}, {"Plant State": "GA"}, {"Latitude": 26}):
            with self.subTest(changes=changes):
                rows, _, rejected = group_plants([generator(), generator(**{"Generator ID": "B", **changes})])
                self.assertFalse(rows)
                self.assertEqual(len(rejected), 1)

    def test_missing_and_nonfinite_coordinates_are_rejected(self):
        for value in (None, "", float("nan"), float("inf"), 100):
            with self.subTest(value=value):
                rows, _, rejected = group_plants([generator(**{"Latitude": value})])
                self.assertFalse(rows)
                self.assertEqual(len(rejected), 1)

    def test_fractional_or_missing_plant_id_is_rejected(self):
        for value in (None, -1, 12.5, True):
            with self.subTest(value=value):
                rows, counts, _ = group_plants([generator(**{"Plant ID": value})])
                self.assertFalse(rows)
                self.assertEqual(counts["invalid_id_rows"], 1)

    def test_county_normalization_is_exact_not_fuzzy(self):
        self.assertEqual(county_key("Miami-Dade County"), county_key("Miami Dade"))
        self.assertEqual(county_key("St. Louis County"), county_key("Saint Louis"))
        self.assertNotEqual(county_key("St. Louis city"), county_key("St. Louis County"))

    def test_census_county_codes_keep_leading_zero(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "counties.zip"
            with ZipFile(path, "w") as archive:
                archive.writestr("counties.txt", "USPS|GEOID|NAME\nAL|01001|Autauga County\n")
            self.assertEqual(read_counties(path), {("AL", "autauga"): "01001"})

    def test_unknown_county_is_rejected_instead_of_guessed(self):
        plants, _, _ = group_plants([generator()])
        rows, rejected = enrich_plants(plants, {})
        self.assertEqual(rows, [])
        self.assertEqual(rejected[0]["reason"], "county_not_matched_to_2026_census")

    def test_workbook_header_scan_and_vintage_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "test.xlsx"
            book = Workbook()
            sheet = book.active
            sheet.title = "Operating"
            sheet.append(["Inventory of Operating Generators as of August 2026"])
            sheet.append([None])
            sheet.append(list(generator()))
            sheet.append(list(generator().values()))
            book.save(path)
            book.close()
            self.assertEqual(read_operating(path, "2026-08")[0]["Plant ID"], 123)
            with self.assertRaises(ValueError):
                read_operating(path, "2026-07")


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.rows = json.loads((GENERATED / "sites.json").read_text())

    def test_real_catalog_meets_contract(self):
        validate_sites(self.rows)
        self.assertEqual(len(self.rows), 60)
        self.assertEqual(len({r["hazard_region"] for r in self.rows}), 6)
        self.assertTrue(set(DEMO_PLANTS).issubset({r["site_id"] for r in self.rows}))

    def test_selection_independent_of_input_order(self):
        expected = select_sites(self.rows)
        random.Random(9).shuffle(self.rows)
        self.assertEqual(expected, select_sites(self.rows))

    def test_selection_spreads_sites_instead_of_taking_first_ids(self):
        candidates = []
        expected = set()
        for region_index, region in enumerate(REGIONS):
            for offset in range(12):
                site_id = 100000 + region_index * 100 + offset
                candidates.append({"site_id": site_id, "hazard_region": region,
                                   "latitude": 40.0, "longitude": -110.0 + offset})
                if offset in (0, 11):
                    expected.add(site_id)
        chosen = select_sites(candidates, per_region=2, demo_plants={})
        self.assertEqual({row["site_id"] for row in chosen}, expected)

    def test_missing_demo_plant_fails_even_if_region_has_enough_candidates(self):
        rows = copy.deepcopy(self.rows)
        next(row for row in rows if row["site_id"] == 621)["site_id"] = 999999
        with self.assertRaisesRegex(ValueError, "621"):
            select_sites(rows)

    def test_rejects_duplicate_site_ids_and_missing_provenance(self):
        for field, value in (("site_id", self.rows[1]["site_id"]), ("source_url", None), ("timezone", ""), ("county_fips", "1001"), ("latitude", float("nan")), ("is_monitored", False)):
            rows = copy.deepcopy(self.rows)
            rows[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_sites(rows)

    def test_region_definitions_do_not_overlap(self):
        states = [state for region in REGIONS.values() for state in region]
        self.assertEqual(len(states), len(set(states)))
        self.assertEqual(len(states), 49)  # contiguous 48 states plus DC


if __name__ == "__main__":
    unittest.main()
