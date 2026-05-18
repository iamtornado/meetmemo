from __future__ import annotations

import logging
from typing import Any

from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.jose import JsonWebKey, JsonWebToken

from app.auth.base import AuthProvider
from app.config import settings

logger = logging.getLogger(__name__)


class OIDCProvider(AuthProvider):
    """OpenID Connect authentication provider (Azure AD / Entra ID)."""

    def __init__(self):
        self._jwks: dict | None = None
        self._config: dict | None = None

    @property
    def enabled(self) -> bool:
        return settings.OIDC_ENABLED and bool(settings.OIDC_CLIENT_ID)

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Generate the OIDC authorization URL."""
        if not self.enabled:
            return ""

        return (
            f"{self._get_config().get('authorization_endpoint', '')}"
            f"?client_id={settings.OIDC_CLIENT_ID}"
            f"&response_type=code"
            f"&redirect_uri={redirect_uri}"
            f"&scope={settings.OIDC_SCOPE.replace(' ', '%20')}"
            f"&state={state}"
        )

    async def exchange_code(self, code: str, redirect_uri: str) -> dict | None:
        """Exchange authorization code for tokens."""
        if not self.enabled:
            return None

        try:
            config = self._get_config()
            async with AsyncOAuth2Client(
                client_id=settings.OIDC_CLIENT_ID,
                client_secret=settings.OIDC_CLIENT_SECRET,
            ) as client:
                token = await client.fetch_token(
                    url=config.get("token_endpoint", ""),
                    code=code,
                    redirect_uri=redirect_uri,
                )
                return token
        except Exception as e:
            logger.error(f"OIDC token exchange error: {e}")
            return None

    def verify_id_token(self, id_token: str) -> dict | None:
        """Verify the ID token and return claims."""
        try:
            config = self._get_config()
            jwks = self._fetch_jwks(config.get("jwks_uri", ""))
            if not jwks:
                return None

            key_set = JsonWebKey.import_key_set(jwks)
            jwt = JsonWebToken(["RS256", "RS384", "RS512"])
            claims = jwt.decode(id_token, key_set)
            claims.validate()
            return claims
        except Exception as e:
            logger.error(f"OIDC token verification error: {e}")
            return None

    async def authenticate(self, identifier: str, password: str) -> dict | None:
        return None  # OIDC uses redirect-based flow

    async def get_user_info(self, identifier: str) -> dict | None:
        return None

    async def get_user_groups(self, identifier: str) -> list[str]:
        return []  # Groups come from ID token claims

    def _get_config(self) -> dict:
        if not self._config and settings.OIDC_DISCOVERY_URL:
            try:
                import httpx
                resp = httpx.get(settings.OIDC_DISCOVERY_URL, timeout=10)
                if resp.status_code == 200:
                    self._config = resp.json()
            except Exception as e:
                logger.error(f"Failed to fetch OIDC config: {e}")
        return self._config or {}

    def _fetch_jwks(self, jwks_uri: str) -> dict | None:
        if self._jwks:
            return self._jwks
        try:
            import httpx
            resp = httpx.get(jwks_uri, timeout=10)
            if resp.status_code == 200:
                self._jwks = resp.json()
                return self._jwks
        except Exception as e:
            logger.error(f"Failed to fetch JWKS: {e}")
        return None


oidc_provider = OIDCProvider()
