import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from get_data.download import download


class DownloadTests(unittest.TestCase):
    def test_verified_cache_preserves_original_retrieval_time(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "source.xlsx"
            path.write_bytes(b"clearly synthetic cached test content")
            receipt = {"url": "https://example.org/test.xlsx", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "retrieved_at": "2026-10-17T12:00:00Z"}
            path.with_suffix(".xlsx.receipt.json").write_text(json.dumps(receipt))
            self.assertEqual(download(None, receipt["url"], path), receipt)
            path.write_bytes(b"corrupted")
            with self.assertRaisesRegex(ValueError, "verification"):
                download(None, receipt["url"], path)


if __name__ == "__main__":
    unittest.main()
