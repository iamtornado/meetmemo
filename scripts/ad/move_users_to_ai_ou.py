#!/usr/bin/env python3
"""Move misplaced test-domain users into AI Tech Center OU tree (per production location)."""

from __future__ import annotations

import os
import sys

from ldap3 import MODIFY_REPLACE, SUBTREE, Connection, Server

SOURCE_BASE = (
    "OU=人工智能技术中心,OU=中央研究院,OU=明阳智慧能源集团股份公司,DC=mywind,DC=com,DC=cn"
)
SOURCE_SUFFIX = "OU=明阳智慧能源集团股份公司,DC=mywind,DC=com,DC=cn"
TARGET_SUFFIX = "OU=IT,OU=myse,DC=dltornado2,DC=com"
TARGET_AI_BASE = f"OU=人工智能技术中心,OU=中央研究院,{TARGET_SUFFIX}"
DELIVERY_OU = f"OU=人工智能产品交付室,{TARGET_AI_BASE}"


def to_target_dn(source_dn: str) -> str:
    return source_dn.replace(SOURCE_SUFFIX, TARGET_SUFFIX, 1)


def parent_dn(dn: str) -> str:
    return dn.split(",", 1)[1]


def connect(host: str, user: str, password: str) -> Connection:
    return Connection(Server(host, port=389), user=user, password=password, auto_bind=True)


def main() -> int:
    dry = "--what-if" in sys.argv
    src_user = os.environ.get("SOURCE_LDAP_USER", "MYWIND\\116823")
    src_pass = os.environ.get("SOURCE_LDAP_PASSWORD")
    tgt_user = os.environ.get("TARGET_LDAP_USER", "DLTORNADO2\\tornadoami")
    tgt_pass = os.environ.get("TARGET_LDAP_PASSWORD")
    if not src_pass or not tgt_pass:
        print("export SOURCE_LDAP_PASSWORD and TARGET_LDAP_PASSWORD", file=sys.stderr)
        return 1

    src = connect("pdcserver.mywind.com.cn", src_user, src_pass)
    tgt = connect("dc-t.dltornado2.com", tgt_user, tgt_pass)

    src.search(
        SOURCE_BASE,
        "(&(objectCategory=person)(objectClass=user))",
        SUBTREE,
        attributes=["sAMAccountName", "displayName", "distinguishedName"],
    )
    prod_by_sam = {str(e.sAMAccountName): e.entry_dn for e in src.entries}

    tgt.search(
        f"OU=IT,{TARGET_SUFFIX}",
        "(&(objectCategory=person)(objectClass=user))",
        SUBTREE,
        attributes=["sAMAccountName", "distinguishedName"],
    )

    moved = 0
    for e in tgt.entries:
        sam = str(e.sAMAccountName)
        if sam not in prod_by_sam:
            continue
        current_dn = e.entry_dn
        if current_dn.lower().endswith(TARGET_AI_BASE.lower()) or DELIVERY_OU.lower() in current_dn.lower():
            continue

        target_parent = parent_dn(to_target_dn(prod_by_sam[sam]))
        rdn = current_dn.split(",", 1)[0]
        new_dn = f"{rdn},{target_parent}"

        if current_dn.lower() == new_dn.lower():
            continue

        print(f"[Move] {sam}: -> {target_parent}")
        if dry:
            moved += 1
            continue

        ok = tgt.modify_dn(current_dn, rdn, new_superior=target_parent)
        if not ok:
            print(f"  FAIL: {tgt.result}")
        else:
            moved += 1

    src.unbind()
    tgt.unbind()
    print(f"\n{'Would move' if dry else 'Moved'}: {moved} user(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
