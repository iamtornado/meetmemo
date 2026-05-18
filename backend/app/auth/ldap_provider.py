from __future__ import annotations

import logging
from typing import Any

import ldap3

from app.auth.base import AuthProvider
from app.config import settings

logger = logging.getLogger(__name__)


class LDAPProvider(AuthProvider):
    """LDAP/Active Directory authentication provider."""

    @property
    def enabled(self) -> bool:
        return settings.LDAP_ENABLED

    async def authenticate(self, identifier: str, password: str) -> dict | None:
        if not self.enabled:
            return None

        try:
            server = ldap3.Server(settings.LDAP_SERVER, get_info=ldap3.ALL)
            conn = ldap3.Connection(server, user=settings.LDAP_BIND_DN, password=settings.LDAP_BIND_PASSWORD)

            if not conn.bind():
                logger.warning("LDAP bind failed")
                return None

            # Search for user
            search_filter = settings.LDAP_USER_SEARCH_FILTER.format(identifier)
            conn.search(
                search_base=settings.LDAP_BASE_DN,
                search_filter=search_filter,
                attributes=["*"],
            )

            if len(conn.entries) == 0:
                return None

            user_dn = conn.entries[0].entry_dn
            user_attrs = conn.entries[0].entry_attributes_as_dict

            # Verify password by binding as the user
            user_conn = ldap3.Connection(server, user=user_dn, password=password)
            if not user_conn.bind():
                return None

            return {
                "dn": user_dn,
                "uid": user_attrs.get("sAMAccountName", [identifier])[0],
                "mail": user_attrs.get("mail", [f"{identifier}@unknown"])[0],
                "display_name": user_attrs.get("displayName", [identifier])[0],
                "groups": await self.get_user_groups(user_dn),
            }

        except Exception as e:
            logger.error(f"LDAP authentication error: {e}")
            return None

    async def get_user_info(self, identifier: str) -> dict | None:
        return None  # Not used standalone

    async def get_user_groups(self, user_dn: str) -> list[str]:
        if not self.enabled:
            return []

        try:
            server = ldap3.Server(settings.LDAP_SERVER)
            conn = ldap3.Connection(server, user=settings.LDAP_BIND_DN, password=settings.LDAP_BIND_PASSWORD)
            if not conn.bind():
                return []

            group_filter = settings.LDAP_GROUP_MEMBER_FILTER.format(user_dn)
            conn.search(
                search_base=settings.LDAP_BASE_DN,
                search_filter=f"(&(objectClass=group){group_filter})",
                attributes=["cn"],
            )

            return [entry.cn.value for entry in conn.entries if hasattr(entry, "cn")]

        except Exception as e:
            logger.error(f"LDAP group lookup error: {e}")
            return []


ldap_provider = LDAPProvider()
