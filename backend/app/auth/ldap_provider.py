from __future__ import annotations

import logging
from typing import Any

import ldap3
from ldap3.utils.conv import escape_filter_chars

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

            # Try multiple search strategies to find the user
            # identifier could be sAMAccountName, userPrincipalName, or mail
            search_filters = [
                settings.LDAP_USER_SEARCH_FILTER.format(identifier),
            ]

            # If the identifier contains @, also try matching by mail
            if "@" in identifier:
                search_filters.insert(0, f"(mail={identifier})")
                search_filters.insert(0, f"(userPrincipalName={identifier})")
            else:
                # Without @, also try appending the default domain
                ldap_domain = settings.LDAP_DOMAIN
                if ldap_domain:
                    search_filters.insert(0, f"(userPrincipalName={identifier}@{ldap_domain})")
                    search_filters.insert(0, f"(mail={identifier}@{ldap_domain})")

            user_entry = None
            for search_filter in search_filters:
                conn.search(
                    search_base=settings.LDAP_BASE_DN,
                    search_filter=search_filter,
                    attributes=["*"],
                )
                if len(conn.entries) > 0:
                    user_entry = conn.entries[0]
                    logger.info(f"Found user with filter: {search_filter}")
                    break

            if user_entry is None:
                return None

            user_dn = user_entry.entry_dn
            user_attrs = user_entry.entry_attributes_as_dict

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

            safe_dn = escape_filter_chars(user_dn)
            group_filter = settings.LDAP_GROUP_MEMBER_FILTER.format(safe_dn)
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
