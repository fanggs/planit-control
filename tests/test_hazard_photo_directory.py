"""Storage setup must never change permissions on unrelated existing paths."""

import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from api.services.hazard_photo_service import PrivatePhotoStore


class PhotoDirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="planit-directory-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def test_new_dedicated_directory_is_private_and_can_be_reopened(self):
        directory = self.base / "new-private-directory"
        store = PrivatePhotoStore(directory)
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        self.assertEqual(PrivatePhotoStore(directory).root, store.root)

    def test_existing_shared_directory_is_rejected_without_changing_it(self):
        directory = self.base / "unrelated-existing-data"
        directory.mkdir()
        directory.chmod(0o755)
        marker = directory / "keep.txt"
        marker.write_text("Existing team data", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "permissions 0700"):
            PrivatePhotoStore(directory)
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o755)
        self.assertEqual(marker.read_text(encoding="utf-8"), "Existing team data")

    def test_existing_private_directory_must_belong_to_api_user(self):
        directory = self.base / "owned-by-someone-else"
        directory.mkdir(mode=0o700)
        with patch("api.services.hazard_photo_service.os.geteuid", return_value=os.geteuid() + 1):
            with self.assertRaisesRegex(ValueError, "owned by the API user"):
                PrivatePhotoStore(directory)
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)

    def test_symlink_and_regular_file_are_rejected_without_modification(self):
        directory = self.base / "target"
        directory.mkdir(mode=0o700)
        link = self.base / "link"
        link.symlink_to(directory, target_is_directory=True)
        with self.assertRaises(ValueError):
            PrivatePhotoStore(link)
        self.assertTrue(link.is_symlink())
        regular_file = self.base / "existing-file"
        regular_file.write_text("Keep me", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must be a directory"):
            PrivatePhotoStore(regular_file)
        self.assertEqual(regular_file.read_text(encoding="utf-8"), "Keep me")


if __name__ == "__main__":
    unittest.main()
