"""Verify Auth0 API access tokens and check roles for Aryan's routes.

The browser must send an access token for this API, not its login ID token.
The Auth0 tenant must add the roles claim to access tokens too.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError

from api.schemas.hazard_report import validate_reporter_id


DEFAULT_ROLES_CLAIM = "https://planit-control/roles"
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    """Identity produced after the token's signature and claims validate."""

    sub: str
    roles: frozenset[str]


@dataclass(frozen=True)
class Auth0Config:
    issuer: str
    audience: str
    roles_claim: str = DEFAULT_ROLES_CLAIM

    def __post_init__(self) -> None:
        parsed = urlsplit(self.issuer)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path != "/"
            or parsed.query
            or parsed.fragment
            or any(character.isspace() for character in self.issuer)
        ):
            raise ValueError("AUTH0_ISSUER must be an HTTPS issuer ending in /")
        if not self.audience or any(character.isspace() for character in self.audience):
            raise ValueError("AUTH0_AUDIENCE must identify this API")
        if not self.roles_claim or any(character.isspace() for character in self.roles_claim):
            raise ValueError("AUTH0_ROLES_CLAIM must be a nonempty claim name")

    @classmethod
    def from_env(cls) -> Auth0Config:
        """Read issuer/domain, API audience, and optional roles claim.

        Missing settings raise an error; there is no demo-auth fallback. These
        values identify the Auth0 tenant and API, and contain no client secret.
        """
        issuer = os.environ.get("AUTH0_ISSUER", "").strip()
        if not issuer:
            domain = os.environ.get("AUTH0_DOMAIN", "").strip()
            if not domain or "/" in domain or ":" in domain:
                raise ValueError("Set AUTH0_ISSUER or the AUTH0_DOMAIN hostname")
            issuer = f"https://{domain}/"
        return cls(
            issuer=issuer,
            audience=os.environ.get("AUTH0_AUDIENCE", "").strip(),
            roles_claim=os.environ.get("AUTH0_ROLES_CLAIM", DEFAULT_ROLES_CLAIM).strip(),
        )


def require_roles(principal: Principal, *roles: str) -> None:
    """Require at least one permitted role from verified token claims."""
    if not principal.roles.intersection(roles):
        raise HTTPException(403, "Your account does not have permission for this action")


def _unauthorized() -> HTTPException:
    return HTTPException(
        401, "A valid API access token is required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def create_auth_dependency(config: Auth0Config | None):
    """Create a FastAPI dependency with a cached JWKS client.

    With None, every request fails with 503. Request data never chooses the
    issuer, allowed algorithm, audience, or signing-key server.
    """
    jwks = (
        PyJWKClient(f"{config.issuer}.well-known/jwks.json", timeout=5)
        if config is not None else None
    )

    def get_principal(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    ) -> Principal:
        if config is None or jwks is None:
            raise HTTPException(503, "Authentication is not configured")
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise _unauthorized()
        token = credentials.credentials
        if len(token) > 16384:
            raise _unauthorized()
        try:
            # This unverified header is only a rejection filter, never identity.
            header = jwt.get_unverified_header(token)
            if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
                raise _unauthorized()
            if not header["kid"] or len(header["kid"]) > 255:
                raise _unauthorized()
            signing_key = jwks.get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token, signing_key.key, algorithms=["RS256"],
                audience=config.audience, issuer=config.issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
                leeway=0,
            )
            subject = validate_reporter_id(claims["sub"])
            roles = claims.get(config.roles_claim, [])
            if not isinstance(roles, list) or any(not isinstance(role, str) for role in roles):
                raise _unauthorized()
            return Principal(sub=subject, roles=frozenset(roles))
        except PyJWKClientConnectionError:
            raise HTTPException(503, "Authentication verification is temporarily unavailable") from None
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            # Never return token content or cryptography/network details.
            raise _unauthorized() from None

    return get_principal
