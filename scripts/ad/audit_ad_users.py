#!/usr/bin/env python3
"""Compare production vs test users under AI Tech Center OU subtree."""

from __future__ import annotations

import os
import sys

from ldap3 import SUBTREE, Connection, Server

SOURCE_BASE = (
    "OU=人工智能技术中心,OU=中央研究院,OU=明阳智慧能源集团股份公司,DC=mywind,DC=com,DC=cn"
)
TARGET_AI_BASE = "OU=人工智能技术中心,OU=中央研究院,OU=IT,OU=myse,DC=dltornado2,DC=com"
TARGET_DOMAIN = "OU=myse,DC=dltornado2,DC=com"
DELIVERY_OU = "OU=人工智能产品交付室," + TARGET_AI_BASE


def connect(host: str, user: str, password: str) -> Connection:
    return Connection(Server(host, port=389), user=user, password=password, auto_bind=True)


def fetch_users(conn: Connection, base: str) -> dict[str, tuple[str, str]]:
    conn.search(
        base,
        "(&(objectCategory=person)(objectClass=user))",
        SUBTREE,
        attributes=["sAMAccountName", "displayName", "distinguishedName"],
    )
    out: dict[str, tuple[str, str]] = {}
    for e in conn.entries:
        sam = str(e.sAMAccountName)
        out[sam] = (str(e.displayName), e.entry_dn)
    return out


def main() -> int:
    src_user = os.environ.get("SOURCE_LDAP_USER", "MYWIND\\116823")
    src_pass = os.environ.get("SOURCE_LDAP_PASSWORD")
    tgt_user = os.environ.get("TARGET_LDAP_USER", "DLTORNADO2\\tornadoami")
    tgt_pass = os.environ.get("TARGET_LDAP_PASSWORD")
    if not src_pass or not tgt_pass:
        print("export SOURCE_LDAP_PASSWORD and TARGET_LDAP_PASSWORD first", file=sys.stderr)
        return 1

    src = connect("pdcserver.mywind.com.cn", src_user, src_pass)
    tgt = connect("dc-t.dltornado2.com", tgt_user, tgt_pass)

    prod = fetch_users(src, SOURCE_BASE)
    test_subtree = fetch_users(tgt, TARGET_AI_BASE)
    test_domain = fetch_users(tgt, TARGET_DOMAIN)

    print(f"Production users under AI Tech Center: {len(prod)}")
    print(f"Test users under same subtree:        {len(test_subtree)}")
    print()

    missing = sorted(set(prod) - set(test_subtree))
    if missing:
        print(f"=== Not under test AI subtree ({len(missing)}) ===")
        for sam in missing:
            disp, dn = prod[sam]
            print(f"  {sam:12} {disp}")
            if sam in test_domain:
                _, tdn = test_domain[sam]
                print(f"    -> exists elsewhere: {tdn}")
            else:
                print("    -> NOT in test domain at all")

    in_parent = [s for s, (_, dn) in test_subtree.items() if DELIVERY_OU not in dn]
    in_delivery = [s for s, (_, dn) in test_subtree.items() if DELIVERY_OU in dn]
    print()
    print(f"=== Test users in 人工智能技术中心 (direct): {len(in_parent)} ===")
    for sam in sorted(in_parent):
        print(f"  {sam:12} {test_subtree[sam][0]}")
    print(f"=== Test users in 人工智能产品交付室: {len(in_delivery)} ===")
    for sam in sorted(in_delivery):
        print(f"  {sam:12} {test_subtree[sam][0]}")

    src.unbind()
    tgt.unbind()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
