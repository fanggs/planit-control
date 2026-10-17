"""Orphan cleanup must be old-only, dry-run by default, and never touch reports."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

from api.services.hazard_photo_cleanup import clean_old_unattached_photos
from api.services.hazard_photo_service import PrivatePhotoStore


def photo_bytes() -> bytes:
    output = io.BytesIO()
    with Image.new("RGB", (2, 2), "blue") as image:
        image.save(output, format="PNG")
    return output.getvalue()


class PhotoCleanupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="planit-photo-cleanup-")
        self.addCleanup(temporary.cleanup)
        self.store = PrivatePhotoStore(Path(temporary.name) / "private")
        self.now = datetime(2026, 10, 17, tzinfo=timezone.utc)
        self.attached: set[str] = set()
        self.is_attached = lambda _session, key: key in self.attached

    def age(self, key, days=2):
        timestamp = (self.now - timedelta(days=days)).timestamp()
        for suffix in ("bin", "json"):
            os.utime(self.store.root / f"{key}.{suffix}", (timestamp, timestamp))

    def plan(self, **options):
        return clean_old_unattached_photos(
            self.store, None, now=self.now, attached=self.is_attached, **options,
        )

    def test_dry_run_then_apply_removes_only_old_unattached_pair(self):
        orphan = self.store.save(photo_bytes(), "auth0|crew")
        linked = self.store.save(photo_bytes(), "auth0|crew")
        recent = self.store.save(photo_bytes(), "auth0|crew")
        self.age(orphan)
        self.age(linked)
        self.attached.add(linked)
        self.assertEqual(self.plan(), [orphan])
        self.assertTrue((self.store.root / f"{orphan}.bin").exists())
        with self.assertRaisesRegex(ValueError, "Stop all report/photo API workers"):
            self.plan(apply=True)
        self.assertEqual(self.plan(apply=True, api_stopped=True), [orphan])
        for suffix in ("bin", "json"):
            self.assertFalse((self.store.root / f"{orphan}.{suffix}").exists())
            self.assertTrue((self.store.root / f"{linked}.{suffix}").exists())
            self.assertTrue((self.store.root / f"{recent}.{suffix}").exists())

    def test_invalid_age_and_incomplete_sidecar_are_never_removed(self):
        orphan = self.store.save(photo_bytes(), "auth0|crew")
        self.age(orphan)
        with self.assertRaisesRegex(ValueError, "at least 24 hours"):
            self.plan(minimum_age=timedelta(minutes=1))
        (self.store.root / f"{orphan}.json").write_text("damaged", encoding="utf-8")
        self.assertEqual(self.plan(apply=True, api_stopped=True), [])
        self.assertTrue((self.store.root / f"{orphan}.bin").exists())

    def test_attachment_recheck_preserves_photo_if_report_appears(self):
        key = self.store.save(photo_bytes(), "auth0|crew")
        self.age(key)
        checks = 0

        def becomes_attached(_session, _key):
            nonlocal checks
            checks += 1
            return checks > 1

        self.assertEqual(clean_old_unattached_photos(
            self.store, None, now=self.now, attached=becomes_attached,
            apply=True, api_stopped=True,
        ), [])
        self.assertTrue((self.store.root / f"{key}.bin").exists())


if __name__ == "__main__":
    unittest.main()
