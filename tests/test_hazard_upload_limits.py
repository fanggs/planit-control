"""Exercise real streamed multipart bodies, including misleading size headers."""

import asyncio
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from api.auth.hazard_auth import Principal
from api.routes.hazard_photos import MAX_PHOTO_REQUEST_BYTES, create_photo_router
from api.services.hazard_photo_service import MAX_PHOTO_BYTES, PrivatePhotoStore


BOUNDARY = "planit-test-boundary"


def multipart_file(data: bytes, name: str = "file") -> bytes:
    return (
        f"--{BOUNDARY}\r\n"
        f'Content-Disposition: form-data; name="{name}"; filename="image.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode() + data + b"\r\n"


ENDING = f"--{BOUNDARY}--\r\n".encode()


class PhotoUploadLimitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="planit-upload-limit-")
        self.addCleanup(self.temporary.cleanup)
        self.store = PrivatePhotoStore(Path(self.temporary.name) / "private")
        self.app = FastAPI()
        self.app.include_router(create_photo_router(
            get_db=lambda: None,
            get_principal=lambda: Principal("auth0|uploader", frozenset({"crew"})),
            store=self.store,
            is_photo_attached=lambda db, key: False,
        ))
        image_stream = io.BytesIO()
        with Image.new("RGB", (2, 2)) as image:
            image.save(image_stream, format="PNG")
        self.image = image_stream.getvalue()

    def streamed_request(self, chunks, *, declared_length=None):
        """Call ASGI directly so the test client cannot combine body chunks."""
        headers = [(b"content-type", f"multipart/form-data; boundary={BOUNDARY}".encode())]
        if declared_length is not None:
            headers.append((b"content-length", str(declared_length).encode()))
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "scheme": "http", "method": "POST", "path": "/photos",
            "raw_path": b"/photos", "query_string": b"", "root_path": "",
            "headers": headers, "client": ("127.0.0.1", 1234),
            "server": ("127.0.0.1", 8000),
        }
        messages = []
        chunk_index = 0

        async def receive():
            nonlocal chunk_index
            if chunk_index >= len(chunks):
                return {"type": "http.disconnect"}
            chunk = chunks[chunk_index]
            chunk_index += 1
            return {"type": "http.request", "body": chunk, "more_body": chunk_index < len(chunks)}

        async def send(message):
            messages.append(message)

        asyncio.run(self.app(scope, receive, send))
        status = next(message["status"] for message in messages if message["type"] == "http.response.start")
        body = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
        return status, json.loads(body), chunk_index

    def test_declared_oversized_body_is_rejected_without_reading_or_saving(self):
        with patch.object(self.store, "save", wraps=self.store.save) as save:
            status, body, reads = self.streamed_request([b"unused"], declared_length=MAX_PHOTO_REQUEST_BYTES + 1)
        self.assertEqual((status, reads), (413, 0))
        self.assertEqual(body["error"]["code"], "payload_too_large")
        save.assert_not_called()

    def test_stream_limit_covers_missing_false_and_invalid_content_length(self):
        oversized = multipart_file(b"x" * MAX_PHOTO_REQUEST_BYTES) + ENDING
        chunks = [oversized[index:index + 128 * 1024] for index in range(0, len(oversized), 128 * 1024)]
        for length in (None, 1, -1, "not-a-number"):
            with self.subTest(content_length=length), patch.object(self.store, "save", wraps=self.store.save) as save:
                status, body, _ = self.streamed_request(chunks, declared_length=length)
                self.assertEqual(status, 413)
                self.assertEqual(set(body), {"error"})
                save.assert_not_called()
        self.assertEqual(list(self.store.root.iterdir()), [])

    def test_oversized_extra_file_cannot_hide_behind_valid_selected_image(self):
        body = multipart_file(self.image) + multipart_file(b"x" * MAX_PHOTO_REQUEST_BYTES, "ignored") + ENDING
        with patch.object(self.store, "save", wraps=self.store.save) as save:
            status, _, _ = self.streamed_request([body], declared_length=1)
        self.assertEqual(status, 413)
        save.assert_not_called()

    def test_spooled_files_close_when_stream_exceeds_limit(self):
        real_spooled_file = tempfile.SpooledTemporaryFile
        opened = []

        def track_file(*args, **kwargs):
            file = real_spooled_file(*args, **kwargs)
            opened.append(file)
            return file

        # Start a part and exceed the in-memory spool threshold before the
        # final chunk breaches our total limit. Cleanup must include disk files.
        first = multipart_file(b"x" * (2 * 1024 * 1024))[:-2]
        with patch("starlette.formparsers.SpooledTemporaryFile", side_effect=track_file):
            status, _, _ = self.streamed_request([first, b"x" * MAX_PHOTO_REQUEST_BYTES, ENDING])
        self.assertEqual(status, 413)
        self.assertTrue(opened)
        self.assertTrue(all(file.closed for file in opened))

    def test_valid_maximum_image_keeps_room_for_multipart_overhead(self):
        # PNG readers allow trailing bytes; this preserves a valid image while
        # exercising the exact byte boundary without a huge random fixture.
        image = self.image + b"\x00" * (MAX_PHOTO_BYTES - len(self.image))
        body = multipart_file(image) + ENDING
        self.assertGreater(len(body), MAX_PHOTO_BYTES)
        self.assertLess(len(body), MAX_PHOTO_REQUEST_BYTES)
        with patch.object(self.store, "save", wraps=self.store.save) as save:
            status, response, _ = self.streamed_request([body])
        self.assertEqual(status, 201)
        save.assert_called_once()
        self.assertEqual(len(self.store.read(response["photo_key"]).data), MAX_PHOTO_BYTES)

    def test_image_limit_remains_stricter_than_request_limit(self):
        with TestClient(self.app) as client, patch.object(self.store, "save", wraps=self.store.save) as save:
            response = client.post("/photos", files={"file": ("large.png", b"x" * (MAX_PHOTO_BYTES + 1), "image/png")})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"]["code"], "photo_too_large")
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
