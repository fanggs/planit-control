"""Synthetic geometry tests; no public requests or safety thresholds."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from get_data.rivers import EARTH_KM, RADIUS_KM, ROOT, collect_site, for_site, nearest, segment_distance_km

SITE = {"site_id": 621, "longitude": 0, "latitude": 0}


def feature(oid, coords, kind=1, name=None):
    return {"attributes": {"OBJECTID": oid, "featuretype": kind, "gnisidlabel": name},
            "geometry": {"paths": [coords]}}


class RiverTests(unittest.TestCase):
    def test_shipped_context_matches_all_monitored_coordinates_and_has_provenance(self):
        sites = json.loads((ROOT/"get_data/generated/sites.json").read_text())
        document = json.loads((ROOT/"get_data/generated/river-site-context.json").read_text())
        self.assertEqual({r["site_id"] for r in document["sites"]}, {s["site_id"] for s in sites})
        self.assertEqual(len(document["sites"]), len(sites))
        for site in sites:
            context = for_site(site)
            self.assertIn(context["status"], {"mapped", "no_mapped_river"})
            self.assertTrue(context["source_url"].startswith("https://3dhp.nationalmap.gov/"))
            self.assertTrue(context["retrieved_at"])
            self.assertTrue(all(len(value) == 64 for value in context["source_sha256"]))

    def test_distance_uses_line_interior_not_nearest_vertex(self):
        self.assertAlmostEqual(segment_distance_km([0, 0], [-1, 0], [1, 0]), 0)
        self.assertAlmostEqual(segment_distance_km([0, 1], [-1, 0], [1, 0]), EARTH_KM*3.141592653589793/180)

    def test_point_beyond_segment_uses_endpoint(self):
        self.assertAlmostEqual(segment_distance_km([2, 0], [0, 0], [1, 0]), EARTH_KM*3.141592653589793/180)
        self.assertAlmostEqual(segment_distance_km([0, 0], [0, 0], [0, 0]), 0)

    def test_canal_does_not_replace_nearest_river(self):
        rows = [feature(1, [[-.1, 0], [.1, 0]], kind=2), feature(2, [[-.1, .01], [.1, .01]])]
        found = nearest(SITE, rows)
        self.assertEqual(found[1], 2)
        self.assertGreater(found[0], 1)

    def test_unnamed_nearer_river_is_not_skipped_for_a_named_one(self):
        found = nearest(SITE, [feature(1, [[-.1, .01], [.1, .01]]),
                               feature(2, [[-.1, .02], [.1, .02]], name="Named river")])
        self.assertEqual(found[1], 1)

    def test_no_match_does_not_claim_no_rivers_anywhere(self):
        self.assertIsNone(nearest(SITE, [feature(1, [[-.1, 1], [.1, 1]])]))
        self.assertIsNone(nearest(SITE, []))
        with self.assertRaises(ValueError):
            nearest(SITE, [feature(1, [[0, float('nan')], [1, 0]])])

    def test_paginated_query_considers_later_pages_and_errors_are_not_no_match(self):
        bodies = [{"spatialReference": {"wkid": 4326}, "exceededTransferLimit": True,
                   "features": [feature(1, [[-.1, .02], [.1, .02]])]},
                  {"spatialReference": {"wkid": 4326}, "features": [feature(2, [[-.1, .01], [.1, .01]])]}]
        def fake_download(client, url, path, **kwargs):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(bodies.pop(0)))
            return {"url": url, "sha256": "a"*64, "retrieved_at": "2026-10-18T08:00:00Z"}
        with tempfile.TemporaryDirectory() as folder, patch('get_data.rivers.ROOT', Path(folder)), \
             patch('get_data.rivers.session'), patch('get_data.rivers.download', side_effect=fake_download):
            context = collect_site(SITE)
            self.assertAlmostEqual(context["distance_miles"], segment_distance_km([0, 0], [-.1, .01], [.1, .01])/1.609344)
            self.assertEqual(len(context["source_sha256"]), 2)
            bodies.append({"error": {"message": "Service unavailable"}})
            with self.assertRaises(ValueError):
                collect_site(SITE)

    def test_cache_cannot_follow_changed_plant_coordinates_or_bad_distance(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"context.json"
            self.assertEqual(for_site(SITE, path=path)["status"], "unavailable")
            row = dict(SITE, status="mapped", distance_miles=0, river_name="Test river")
            path.write_text(json.dumps({"sites": [row]}))
            self.assertEqual(for_site(SITE, path=path)["distance_miles"], 0)
            self.assertEqual(for_site(dict(SITE, longitude=1), path=path)["status"], "unavailable")
            row["distance_miles"] = RADIUS_KM
            path.write_text(json.dumps({"sites": [row]}))
            self.assertEqual(for_site(SITE, path=path)["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
