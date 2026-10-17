"""Main API Auth0 boundary and exact CORS origins, without network calls."""

from __future__ import annotations

import importlib
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from api.auth.hazard_auth import DEFAULT_ROLES_CLAIM


AUTH_ENV = {
    "AUTH0_DOMAIN": "planit-test.example",
    "AUTH0_AUDIENCE": "https://planit-test.example/api",
    "PLANIT_DATA": "sample",
}
DATA_URLS = (
    "/sites", "/sites/6045", "/alerts", "/briefings/6045",
    "/reports?site_id=6045",
)


def load_main():
    module = importlib.import_module("api.main")
    return importlib.reload(module)


class MainAuth0Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def token(self, roles: list[str]) -> str:
        return jwt.encode(
            {
                "iss": "https://planit-test.example/",
                "aud": AUTH_ENV["AUTH0_AUDIENCE"],
                "sub": "auth0|planit-tester",
                "exp": int(time.time()) + 120,
                DEFAULT_ROLES_CLAIM: roles,
            },
            self.signing_key,
            algorithm="RS256",
            headers={"kid": "test-key"},
        )

    def test_missing_or_invalid_auth_settings_fail_closed(self):
        for settings in ({"PLANIT_DATA": "sample"}, {
            "PLANIT_DATA": "sample", "AUTH0_DOMAIN": "wrong/path",
            "AUTH0_AUDIENCE": AUTH_ENV["AUTH0_AUDIENCE"],
        }):
            with self.subTest(settings=settings), patch.dict(os.environ, settings, clear=True):
                with TestClient(load_main().app) as client:
                    self.assertEqual(client.get("/health").status_code, 200)
                    for url in DATA_URLS:
                        response = client.get(url)
                        self.assertEqual(response.status_code, 503, url)
                        self.assertEqual(response.json()["error"]["code"], "error")

    def test_all_data_reads_require_signed_token_and_role(self):
        with patch.dict(os.environ, AUTH_ENV, clear=True), patch(
            "api.auth.hazard_auth.PyJWKClient"
        ) as jwks_factory:
            jwks_factory.return_value.get_signing_key_from_jwt.return_value = SimpleNamespace(
                key=self.signing_key.public_key()
            )
            with TestClient(load_main().app) as client:
                for url in DATA_URLS:
                    with self.subTest(url=url):
                        missing = client.get(url)
                        self.assertEqual(missing.status_code, 401)
                        self.assertEqual(missing.headers["www-authenticate"], "Bearer")
                        no_role = client.get(url, headers={"Authorization": f"Bearer {self.token([])}"})
                        self.assertEqual(no_role.status_code, 403)
                        crew = client.get(url, headers={"Authorization": f"Bearer {self.token(['crew'])}"})
                        # The placeholder site ID is absent from sample data, so
                        # detail/briefing may correctly return 404 after auth.
                        self.assertIn(crew.status_code, (200, 404))
                self.assertEqual(client.get("/health").status_code, 200)

    def test_cors_allows_only_documented_local_origins_by_default(self):
        with patch.dict(os.environ, AUTH_ENV, clear=True):
            with TestClient(load_main().app) as client:
                for origin in ("http://127.0.0.1:4174", "http://127.0.0.1:4175"):
                    response = client.options("/sites", headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "GET",
                        "Access-Control-Request-Headers": "Authorization",
                    })
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["access-control-allow-origin"], origin)
                for origin in ("http://localhost:4174", "http://127.0.0.1:9999", "https://unlisted.example"):
                    response = client.options("/sites", headers={
                        "Origin": origin, "Access-Control-Request-Method": "GET",
                    })
                    self.assertNotIn("access-control-allow-origin", response.headers)

    def test_production_origins_must_be_exact_https_origins(self):
        with patch.dict(os.environ, {"PLANIT_CORS_ORIGINS": "https://planit.example,https://app.planit.example"}, clear=True):
            self.assertEqual(load_main()._cors_origins(), ["https://planit.example", "https://app.planit.example"])
        for origin in (
            "", "http://localhost:4174", "http://127.0.0.1:8000",
            "https://*.planit.example", "https://planit.example/path",
            "https://planit.example/", "https://planit.example,",
            "https://planit.example:bad",
        ):
            with self.subTest(origin=origin), patch.dict(os.environ, {"PLANIT_CORS_ORIGINS": origin}, clear=True):
                with self.assertRaises(ValueError):
                    load_main()


if __name__ == "__main__":
    unittest.main()
