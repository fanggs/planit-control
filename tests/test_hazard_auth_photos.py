"""Offline security/integration checks for auth and private hazard photos."""

from __future__ import annotations

import io
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from jwt.exceptions import PyJWKClientConnectionError
from PIL import Image
from sqlalchemy.exc import SQLAlchemyError

from api.auth.hazard_auth import (
    DEFAULT_ROLES_CLAIM, Auth0Config, Principal, create_auth_dependency, require_roles,
)
from api.routes.hazard_errors import HazardRoute
from api.routes.hazard_photos import create_photo_router
from api.services.hazard_photo_service import (
    MAX_PHOTO_BYTES, InvalidPhoto, PhotoNotFound, PhotoTooLarge, PrivatePhotoStore,
)


def image_bytes(image_format: str = "PNG", size: tuple[int, int] = (4, 4)) -> bytes:
    stream = io.BytesIO()
    with Image.new("RGB", size, color="green") as image:
        image.save(stream, format=image_format)
    return stream.getvalue()


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.config = Auth0Config("https://planit-test.example/", "https://planit-api.example")

    def setUp(self):
        # Only key discovery is mocked. PyJWT still verifies real RSA signatures
        # and issuer/audience/expiry/subject claims for every request.
        self.jwks_patch = patch("api.auth.hazard_auth.PyJWKClient")
        factory = self.jwks_patch.start()
        self.addCleanup(self.jwks_patch.stop)
        self.jwks = factory.return_value
        self.jwks.get_signing_key_from_jwt.return_value = SimpleNamespace(key=self.signing_key.public_key())
        self.client = self.client_for(create_auth_dependency(self.config))
        self.addCleanup(self.client.close)

    @staticmethod
    def client_for(dependency):
        app = FastAPI()
        router = APIRouter(route_class=HazardRoute)

        @router.get("/protected")
        def protected(principal: Principal = Depends(dependency)):
            require_roles(principal, "crew", "supervisor")
            return {"sub": principal.sub}

        app.include_router(router)
        return TestClient(app)

    def token(self, updates=None, *, remove=(), key=None, algorithm="RS256"):
        claims = {
            "sub": "auth0|aryan", "iss": self.config.issuer,
            "aud": self.config.audience, "exp": int(time.time()) + 120,
            DEFAULT_ROLES_CLAIM: ["crew"],
        }
        claims.update(updates or {})
        for claim in remove:
            claims.pop(claim, None)
        return jwt.encode(claims, key or self.signing_key, algorithm=algorithm, headers={"kid": "test-key"})

    def request(self, token):
        return self.client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    def test_valid_access_token(self):
        self.assertEqual(self.request(self.token()).json(), {"sub": "auth0|aryan"})

    def test_signature_issuer_audience_expiry_are_enforced(self):
        invalid_tokens = [
            self.token(key=self.other_key),
            self.token({"iss": "https://other-tenant.example/"}),
            self.token({"aud": "frontend-client-id"}),
            self.token({"exp": int(time.time()) - 1}),
            self.token({"sub": "auth0|bad subject"}),
            self.token(remove=("exp",)),
            self.token(remove=("sub",)),
        ]
        for token in invalid_tokens:
            with self.subTest(token=token[-12:]):
                response = self.request(token)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json()["error"]["code"], "unauthorized")
                self.assertNotIn(token, response.text)

    def test_missing_or_wrong_bearer_and_algorithms_are_rejected(self):
        self.assertEqual(self.client.get("/protected").status_code, 401)
        self.assertEqual(self.client.get("/protected", headers={"Authorization": "Basic abc"}).status_code, 401)
        self.assertEqual(self.request("not-a-token").status_code, 401)
        hs_token = self.token(key="a-long-test-only-shared-key-for-hs256", algorithm="HS256")
        self.assertEqual(self.request(hs_token).status_code, 401)

    def test_roles_are_taken_only_from_validated_role_list(self):
        for role in ("crew", "supervisor"):
            self.assertEqual(self.request(self.token({DEFAULT_ROLES_CLAIM: [role]})).status_code, 200)
        self.assertEqual(self.request(self.token(remove=(DEFAULT_ROLES_CLAIM,))).status_code, 403)
        self.assertEqual(self.request(self.token({DEFAULT_ROLES_CLAIM: ["admin"]})).status_code, 403)
        self.assertEqual(self.request(self.token({DEFAULT_ROLES_CLAIM: "supervisor"})).status_code, 401)

    def test_jwks_failure_and_missing_configuration_fail_closed(self):
        self.jwks.get_signing_key_from_jwt.side_effect = PyJWKClientConnectionError("private network details")
        response = self.request(self.token())
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private network details", response.text)
        with self.client_for(create_auth_dependency(None)) as client:
            self.assertEqual(client.get("/protected").status_code, 503)

    def test_environment_configuration_and_https_issuer(self):
        with patch.dict(os.environ, {"AUTH0_DOMAIN": "tenant.us.auth0.com", "AUTH0_AUDIENCE": "api-id"}, clear=True):
            self.assertEqual(Auth0Config.from_env().issuer, "https://tenant.us.auth0.com/")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError):
                Auth0Config.from_env()
        for issuer in ("http://tenant.example/", "https://tenant.example/path/", "https://user@tenant.example/"):
            with self.assertRaises(ValueError):
                Auth0Config(issuer, "api-id")


class PhotoStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="planit-photos-")
        self.addCleanup(self.temporary.cleanup)
        self.store = PrivatePhotoStore(Path(self.temporary.name) / "private")
        self.data = image_bytes()

    def test_actual_image_formats_private_permissions_and_reopen(self):
        for image_format, content_type in (("PNG", "image/png"), ("JPEG", "image/jpeg")):
            data = image_bytes(image_format)
            key = self.store.save(data, "auth0|uploader")
            self.assertRegex(key, r"^[A-Za-z0-9_-]+$")
            photo = PrivatePhotoStore(self.store.root).read(key)
            self.assertEqual((photo.data, photo.content_type, photo.uploader_id), (data, content_type, "auth0|uploader"))
            self.assertTrue(self.store.verify_photo(None, key, "auth0|uploader", 6045))
            self.assertFalse(self.store.verify_photo(None, key, "auth0|another", 6045))
            self.assertEqual(stat.S_IMODE(self.store.root.stat().st_mode), 0o700)
            for extension in ("bin", "json"):
                self.assertEqual(stat.S_IMODE((self.store.root / f"{key}.{extension}").stat().st_mode), 0o600)

    def test_invalid_images_sizes_and_dimensions(self):
        for data in (b"", b"<svg>not a photo</svg>", self.data[:30], image_bytes("GIF"), image_bytes(size=(10001, 1))):
            with self.assertRaises(InvalidPhoto):
                self.store.save(data, "auth0|uploader")
        with self.assertRaises(PhotoTooLarge):
            self.store.save(b"x" * (MAX_PHOTO_BYTES + 1), "auth0|uploader")
        self.assertEqual(list(self.store.root.iterdir()), [])

    def test_key_traversal_missing_metadata_tampering_and_symlinks(self):
        for key in ("../secret", "/tmp/photo", "https://example.test/image", "not-created"):
            with self.assertRaises(PhotoNotFound):
                self.store.read(key)
        key = self.store.save(self.data, "auth0|uploader")
        metadata_path = self.store.root / f"{key}.json"
        metadata_path.write_text("invalid JSON", encoding="utf-8")
        self.assertFalse(self.store.verify_photo(None, key, "auth0|uploader", 6045))
        key = self.store.save(self.data, "auth0|uploader")
        binary_path = self.store.root / f"{key}.bin"
        binary_path.write_bytes(b"modified")
        with self.assertRaises(PhotoNotFound):
            self.store.read(key)
        binary_path.unlink()
        binary_path.symlink_to(metadata_path)
        with self.assertRaises(PhotoNotFound):
            self.store.read(key)

    def test_public_root_and_publicly_readable_files_are_rejected(self):
        repo = Path(__file__).resolve().parents[1]
        with self.assertRaises(ValueError):
            PrivatePhotoStore(repo / "page" / "private-test-photos")
        with self.assertRaises(ValueError):
            PrivatePhotoStore(repo)
        key = self.store.save(self.data, "auth0|uploader")
        (self.store.root / f"{key}.json").chmod(0o644)
        with self.assertRaises(PhotoNotFound):
            self.store.read(key)


class PhotoRouteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="planit-photo-routes-")
        self.addCleanup(self.temporary.cleanup)
        self.store = PrivatePhotoStore(Path(self.temporary.name) / "private")
        self.principal = Principal("auth0|uploader", frozenset({"crew"}))
        self.attached: set[str] = set()
        app = FastAPI()
        app.include_router(create_photo_router(
            get_db=lambda: None, get_principal=lambda: self.principal,
            store=self.store, is_photo_attached=lambda db, key: key in self.attached,
        ))
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def upload(self, data=None, *, filename="../../untrusted-name.png", content_type="image/png"):
        return self.client.post("/photos", files={"file": (filename, image_bytes() if data is None else data, content_type)})

    def test_upload_preview_and_attached_photo_permissions(self):
        response = self.upload(content_type="application/octet-stream")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.json()), {"photo_key"})
        key = response.json()["photo_key"]
        preview = self.client.get(f"/photos/{key}")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.content, image_bytes())
        self.assertEqual(preview.headers["content-type"], "image/png")
        self.assertEqual(preview.headers["cache-control"], "private, no-store")
        self.assertEqual(preview.headers["x-content-type-options"], "nosniff")
        self.principal = Principal("auth0|other", frozenset({"crew"}))
        self.assertEqual(self.client.get(f"/photos/{key}").status_code, 404)
        self.attached.add(key)
        self.assertEqual(self.client.get(f"/photos/{key}").status_code, 200)
        self.principal = Principal("auth0|supervisor", frozenset({"supervisor"}))
        self.assertEqual(self.client.get(f"/photos/{key}").status_code, 200)
        self.assertEqual(self.upload().status_code, 201)

    def test_roles_validation_limits_and_error_envelope(self):
        self.principal = Principal("auth0|unknown", frozenset())
        self.assertEqual(self.upload().status_code, 403)
        self.assertEqual(self.client.get("/photos/anything").status_code, 403)
        self.principal = Principal("auth0|uploader", frozenset({"crew"}))
        for response, expected in (
            (self.upload(b"not-an-image"), 415),
            (self.upload(b"x" * (MAX_PHOTO_BYTES + 1)), 413),
            (self.client.post("/photos"), 422),
            (self.client.get("/photos/nonexistent"), 404),
        ):
            self.assertEqual(response.status_code, expected)
            self.assertEqual(set(response.json()), {"error"})
            self.assertIn("message", response.json()["error"])

    def test_storage_failure_returns_service_unavailable(self):
        with patch.object(self.store, "_write_private", side_effect=OSError("disk private detail")):
            response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("disk private detail", response.text)

    def test_database_lookup_failure_is_private_service_error(self):
        key = self.store.save(image_bytes(), "auth0|another-uploader")
        app = FastAPI()

        def unavailable(db, photo_key):
            raise SQLAlchemyError("private SQL and query parameters")

        app.include_router(create_photo_router(
            get_db=lambda: None, get_principal=lambda: self.principal,
            store=self.store, is_photo_attached=unavailable,
        ))
        with TestClient(app) as client:
            response = client.get(f"/photos/{key}")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(set(response.json()), {"error"})
        self.assertNotIn("private SQL", response.text)

    def test_invalid_attachment_callbacks_cannot_grant_access(self):
        async def async_lookup(db, key):
            return True

        class AsyncLookup:
            async def __call__(self, db, key):
                return True

        for callback in (async_lookup, AsyncLookup()):
            with self.assertRaises(ValueError):
                create_photo_router(
                    get_db=lambda: None, get_principal=lambda: self.principal,
                    store=self.store, is_photo_attached=callback,
                )
        key = self.store.save(image_bytes(), "auth0|other-uploader")
        for callback, expected in (
            (lambda db, key: "truthy-but-not-a-boolean", 404),
            (lambda db, key: async_lookup(db, key), 503),
        ):
            app = FastAPI()
            app.include_router(create_photo_router(
                get_db=lambda: None, get_principal=lambda: self.principal,
                store=self.store, is_photo_attached=callback,
            ))
            with TestClient(app) as client:
                self.assertEqual(client.get(f"/photos/{key}").status_code, expected)


if __name__ == "__main__":
    unittest.main()
