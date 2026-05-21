#!/usr/bin/env python3
"""
Sync「人工智能技术中心」OU subtree from production mywind.com.cn to test dltornado2.com.

Runs on Linux/macOS/Windows (no RSAT). Uses LDAP/LDAPS via ldap3.

Examples:
  pip install -r scripts/ad/requirements-ad-sync.txt

  # Dry-run
  python scripts/ad/sync_ai_tech_center.py --what-if \\
    --source-host dc01.mywind.com.cn --target-host dc01.dltornado2.com \\
    --source-user 'MYWIND\\syncuser' --target-user 'DLTORNADO2\\admin'

  # Or use env vars (recommended)
  export SOURCE_LDAP_HOST=dc01.mywind.com.cn
  export SOURCE_LDAP_USER='MYWIND\\syncuser'
  export SOURCE_LDAP_PASSWORD='***'
  export TARGET_LDAP_HOST=dc01.dltornado2.com
  export TARGET_LDAP_USER='DLTORNADO2\\admin'
  export TARGET_LDAP_PASSWORD='***'
  python scripts/ad/sync_ai_tech_center.py --what-if
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import ssl
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ldap3 import ALL, MODIFY_ADD, MODIFY_REPLACE, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException, LDAPSocketOpenError
from ldap3.utils.conv import escape_filter_chars

# --- Fixed DN paths ---
SOURCE_SEARCH_BASE = (
    "OU=人工智能技术中心,OU=中央研究院,OU=明阳智慧能源集团股份公司,DC=mywind,DC=com,DC=cn"
)
SOURCE_DOMAIN_SUFFIX = "OU=明阳智慧能源集团股份公司,DC=mywind,DC=com,DC=cn"
TARGET_DOMAIN_SUFFIX = "OU=IT,OU=myse,DC=dltornado2,DC=com"
TARGET_ROOT_OU = f"OU=中央研究院,{TARGET_DOMAIN_SUFFIX}"
AI_TECH_OU_DN = f"OU=人工智能技术中心,{TARGET_ROOT_OU}"
TARGET_UPN_SUFFIX = "dltornado2.com"

USER_ACCOUNT_DISABLED = 514
USER_ACCOUNT_NORMAL = 512


@dataclass
class LdapOu:
    dn: str
    name: str
    description: str | None = None


@dataclass
class LdapUser:
    dn: str
    sam: str
    upn: str | None
    display_name: str
    given_name: str | None
    surname: str | None
    mail: str | None
    title: str | None
    department: str | None
    description: str | None
    enabled: bool = True


@dataclass
class LdapGroup:
    dn: str
    name: str
    sam: str
    group_type: str | None
    description: str | None
    members: list[str] = field(default_factory=list)


def dn_depth(dn: str) -> int:
    return len([p for p in dn.split(",") if p])


def parent_dn(dn: str) -> str:
    return dn.split(",", 1)[1]


def rdn_value(dn: str) -> str:
    return dn.split(",", 1)[0].split("=", 1)[1]


def to_target_dn(source_dn: str) -> str:
    if not source_dn.endswith(SOURCE_DOMAIN_SUFFIX):
        raise ValueError(f"DN suffix mismatch: {source_dn}")
    return source_dn.replace(SOURCE_DOMAIN_SUFFIX, TARGET_DOMAIN_SUFFIX, 1)


def normalize_bind_user(user: str, netbios: str, upn_suffix: str) -> str:
    user = user.strip()
    if "\\" in user or "@" in user:
        return user
    return f"{netbios}\\{user}"


def encode_ad_password(password: str) -> bytes:
    return f'"{password}"'.encode("utf-16-le")


def make_server(host: str, use_ssl: bool, port: int | None) -> Server:
    host = host.replace("ldap://", "").replace("ldaps://", "").strip()
    if port is None:
        port = 636 if use_ssl else 389
    tls = None
    if use_ssl:
        tls = Tls(validate=ssl.CERT_NONE)
    return Server(host, port=port, use_ssl=use_ssl, tls=tls, get_info=ALL)


def connect_ldap(
    label: str,
    host: str,
    user: str,
    password: str,
    *,
    use_ssl: bool = False,
    port: int | None = None,
) -> Connection:
    server = make_server(host, use_ssl, port)
    print(f">>> Connect {label}: {host} (ssl={use_ssl}) as {user}")
    try:
        conn = Connection(server, user=user, password=password, auto_bind=True, receive_timeout=30)
    except LDAPSocketOpenError as exc:
        raise SystemExit(
            f"Cannot reach LDAP server {host}:{server.port}. "
            f"Check VPN/firewall and -SourceHost/-TargetHost. ({exc})"
        ) from exc
    except LDAPException as exc:
        raise SystemExit(
            f"LDAP bind failed for {label}. Use MYWIND\\user or user@domain.com. ({exc})"
        ) from exc
    print(f"    OK ({label})")
    return conn


def test_base(conn: Connection, base_dn: str, label: str) -> None:
    ok = conn.search(base_dn, "(objectClass=*)", search_scope="BASE", attributes=["distinguishedName"])
    if not ok or not conn.entries:
        raise SystemExit(f"Cannot read base DN for {label}: {base_dn}")
    print(f"    Base OK: {label} -> {conn.entries[0].entry_dn}")


def read_subtree(conn: Connection, *, skip_groups: bool) -> tuple[list[LdapOu], list[LdapUser], list[LdapGroup]]:
    print(f">>> [1/2] Read production subtree: {SOURCE_SEARCH_BASE}")

    conn.search(
        SOURCE_SEARCH_BASE,
        "(objectClass=organizationalUnit)",
        search_scope=SUBTREE,
        attributes=["name", "description", "distinguishedName"],
    )
    ous = [
        LdapOu(
            dn=e.entry_dn,
            name=str(e.name) if e.name else rdn_value(e.entry_dn),
            description=str(e.description) if e.description else None,
        )
        for e in conn.entries
    ]

    user_filter = "(&(objectCategory=person)(objectClass=user))"
    conn.search(
        SOURCE_SEARCH_BASE,
        user_filter,
        search_scope=SUBTREE,
        attributes=[
            "sAMAccountName",
            "userPrincipalName",
            "displayName",
            "givenName",
            "sn",
            "mail",
            "title",
            "department",
            "description",
            "userAccountControl",
        ],
    )
    users: list[LdapUser] = []
    for e in conn.entries:
        sam = str(e.sAMAccountName) if e.sAMAccountName else None
        if not sam:
            continue
        uac = int(e.userAccountControl.value) if e.userAccountControl else 0
        enabled = (uac & 2) == 0
        display = str(e.displayName) if e.displayName else sam
        users.append(
            LdapUser(
                dn=e.entry_dn,
                sam=sam,
                upn=str(e.userPrincipalName) if e.userPrincipalName else None,
                display_name=display,
                given_name=str(e.givenName) if e.givenName else None,
                surname=str(e.sn) if e.sn else None,
                mail=str(e.mail) if e.mail else None,
                title=str(e.title) if e.title else None,
                department=str(e.department) if e.department else None,
                description=str(e.description) if e.description else None,
                enabled=enabled,
            )
        )

    groups: list[LdapGroup] = []
    if not skip_groups:
        conn.search(
            SOURCE_SEARCH_BASE,
            "(objectClass=group)",
            search_scope=SUBTREE,
            attributes=["name", "sAMAccountName", "groupType", "description", "member"],
        )
        for e in conn.entries:
            # Use group Name (e.g. 7390_1202058); production sAMAccountName is often SID-like ($...).
            sam = re.sub(r"\s+", "", str(e.name))[:20]
            members = [str(m) for m in e.member] if e.member else []
            groups.append(
                LdapGroup(
                    dn=e.entry_dn,
                    name=str(e.name),
                    sam=sam,
                    group_type=str(e.groupType) if e.groupType else None,
                    description=str(e.description) if e.description else None,
                    members=members,
                )
            )

    print(f"    OUs: {len(ous)}  Users: {len(users)}  Groups: {len(groups)}")
    return ous, users, groups


def entry_exists(conn: Connection, dn: str) -> bool:
    return conn.search(dn, "(objectClass=*)", search_scope="BASE", attributes=["distinguishedName"]) and bool(
        conn.entries
    )


def find_user_by_sam(conn: Connection, sam: str) -> str | None:
    filt = f"(sAMAccountName={escape_filter_chars(sam)})"
    if conn.search(TARGET_DOMAIN_SUFFIX, filt, search_scope=SUBTREE, attributes=["distinguishedName"]):
        if conn.entries:
            return conn.entries[0].entry_dn
    return None


def find_group_by_sam(conn: Connection, sam: str) -> str | None:
    filt = f"(sAMAccountName={escape_filter_chars(sam)})"
    if conn.search(TARGET_DOMAIN_SUFFIX, filt, search_scope=SUBTREE, attributes=["distinguishedName"]):
        if conn.entries:
            return conn.entries[0].entry_dn
    return None


def ensure_ou_chain(conn: Connection, *, what_if: bool) -> None:
    for dn in (TARGET_ROOT_OU, AI_TECH_OU_DN):
        if entry_exists(conn, dn):
            continue
        print(f"[OU] Create {dn}")
        if what_if:
            continue
        conn.add(dn, object_class=["organizationalUnit"])


def create_child_ous(conn: Connection, ous: list[LdapOu], *, what_if: bool) -> None:
    skip = {TARGET_ROOT_OU, AI_TECH_OU_DN}
    for ou in sorted(ous, key=lambda o: dn_depth(o.dn)):
        target_dn = to_target_dn(ou.dn)
        if target_dn in skip or entry_exists(conn, target_dn):
            continue
        print(f"[OU] Create {target_dn}")
        if what_if:
            continue
        attrs: dict[str, Any] = {}
        if ou.description:
            attrs["description"] = ou.description
        conn.add(target_dn, object_class=["organizationalUnit"], attributes=attrs)


def create_users(
    conn: Connection,
    users: list[LdapUser],
    *,
    what_if: bool,
    sam_suffix: str,
    default_password: str,
    set_password: bool,
) -> dict[str, str]:
    """Returns map: source user DN -> target user DN."""
    dn_map: dict[str, str] = {}

    for u in users:
        sam = u.sam + sam_suffix
        target_parent = parent_dn(to_target_dn(u.dn))
        target_dn = f"CN={u.display_name},{target_parent}"

        existing = find_user_by_sam(conn, sam)
        if existing:
            print(f"[User] Skip existing: {sam}")
            dn_map[u.dn] = existing
            continue

        print(f"[User] Create {sam} ({u.display_name}) -> {target_parent}")
        if what_if:
            dn_map[u.dn] = target_dn
            continue

        attrs: dict[str, Any] = {
            "cn": u.display_name,
            "sAMAccountName": sam,
            "userPrincipalName": f"{sam}@{TARGET_UPN_SUFFIX}",
            "displayName": u.display_name,
            "userAccountControl": USER_ACCOUNT_DISABLED,
        }
        if u.given_name:
            attrs["givenName"] = u.given_name
        if u.surname:
            attrs["sn"] = u.surname
        if u.title:
            attrs["title"] = u.title
        if u.department:
            attrs["department"] = u.department
        if u.description:
            attrs["description"] = u.description
        if u.mail:
            attrs["mail"] = f"{sam}@{TARGET_UPN_SUFFIX}"
        else:
            attrs["mail"] = f"{sam}@{TARGET_UPN_SUFFIX}"

        try:
            conn.add(
                target_dn,
                object_class=["top", "person", "organizationalPerson", "user"],
                attributes=attrs,
            )
        except LDAPException as exc:
            target_dn = f"CN={sam},{target_parent}"
            attrs["cn"] = sam
            conn.add(
                target_dn,
                object_class=["top", "person", "organizationalPerson", "user"],
                attributes=attrs,
            )
            print(f"    (used CN={sam} due to: {exc})")

        if set_password:
            conn.modify(
                target_dn,
                {"unicodePwd": [(MODIFY_REPLACE, [encode_ad_password(default_password)])]},
            )
            # -1 clears "must change password at next logon" (0 would block simple LDAP bind / MeetMemo login)
            conn.modify(target_dn, {"pwdLastSet": [(MODIFY_REPLACE, ["-1"])]})
            uac = USER_ACCOUNT_NORMAL if u.enabled else USER_ACCOUNT_DISABLED
            conn.modify(target_dn, {"userAccountControl": [(MODIFY_REPLACE, [str(uac)])]})
        else:
            print("    WARN: password not set (use --set-password with LDAPS on target)")

        dn_map[u.dn] = target_dn

    return dn_map


def create_groups(
    conn: Connection,
    groups: list[LdapGroup],
    *,
    what_if: bool,
    sam_suffix: str,
) -> dict[str, str]:
    dn_map: dict[str, str] = {}
    for g in groups:
        sam = (g.sam[:20] if len(g.sam) > 20 else g.sam) + sam_suffix
        target_dn = to_target_dn(g.dn)
        parent = parent_dn(target_dn)

        existing = find_group_by_sam(conn, sam)
        if existing:
            print(f"[Group] Skip existing: {sam}")
            dn_map[g.dn] = existing
            continue

        print(f"[Group] Create {g.name} (sAMAccountName={sam})")
        if what_if:
            dn_map[g.dn] = target_dn
            continue

        attrs: dict[str, Any] = {
            "sAMAccountName": sam,
        }
        if g.description:
            attrs["description"] = g.description
        if g.group_type:
            attrs["groupType"] = int(g.group_type)

        conn.add(target_dn, object_class=["top", "group"], attributes=attrs)
        dn_map[g.dn] = target_dn
    return dn_map


def add_group_members(
    conn: Connection,
    groups: list[LdapGroup],
    user_dn_map: dict[str, str],
    group_dn_map: dict[str, str],
    *,
    what_if: bool,
) -> None:
    for g in groups:
        group_dn = group_dn_map.get(g.dn)
        if not group_dn:
            continue
        for member_dn in g.members:
            target_member = user_dn_map.get(member_dn)
            if not target_member:
                continue
            print(f"[Group] Add member -> {rdn_value(group_dn)}")
            if what_if:
                continue
            try:
                conn.modify(group_dn, {"member": [(MODIFY_ADD, [target_member])]})
            except LDAPException as exc:
                if "entryAlreadyExists" in str(exc) or "68" in str(exc):
                    continue
                print(f"    WARN: {exc}")


def write_subtree(
    conn: Connection,
    ous: list[LdapOu],
    users: list[LdapUser],
    groups: list[LdapGroup],
    *,
    what_if: bool,
    sam_suffix: str,
    default_password: str,
    set_password: bool,
    skip_groups: bool,
) -> None:
    print(f">>> [2/2] Write test domain: {TARGET_DOMAIN_SUFFIX}")
    if what_if:
        print("    WhatIf mode - no changes")

    ensure_ou_chain(conn, what_if=what_if)
    create_child_ous(conn, ous, what_if=what_if)
    user_dn_map = create_users(
        conn,
        users,
        what_if=what_if,
        sam_suffix=sam_suffix,
        default_password=default_password,
        set_password=set_password,
    )
    if skip_groups:
        return
    group_dn_map = create_groups(conn, groups, what_if=what_if, sam_suffix=sam_suffix)
    add_group_members(conn, groups, user_dn_map, group_dn_map, what_if=what_if)


def save_json(path: Path, ous: list[LdapOu], users: list[LdapUser], groups: list[LdapGroup]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "ous.json").write_text(
        json.dumps([o.__dict__ for o in ous], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (path / "users.json").write_text(
        json.dumps([u.__dict__ for u in users], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (path / "groups.json").write_text(
        json.dumps([g.__dict__ for g in groups], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"    JSON backup: {path}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sync AI Tech Center OU from mywind to dltornado2 via LDAP")
    p.add_argument("--what-if", action="store_true", help="Dry-run, do not write to test AD")
    p.add_argument("--skip-groups", action="store_true")
    p.add_argument("--sam-suffix", default=os.environ.get("SAM_ACCOUNT_SUFFIX", ""))
    p.add_argument("--default-password", default=os.environ.get("DEFAULT_AD_PASSWORD", "ChangeMe!2026"))
    p.add_argument("--set-password", action="store_true", help="Set initial password on test users (requires LDAPS)")
    p.add_argument("--save-json", default="", help="Backup read data to directory")

    p.add_argument("--source-host", default=os.environ.get("SOURCE_LDAP_HOST", "mywind.com.cn"))
    p.add_argument("--source-port", type=int, default=int(os.environ.get("SOURCE_LDAP_PORT", "389")))
    p.add_argument("--source-user", default=os.environ.get("SOURCE_LDAP_USER", ""))
    p.add_argument("--source-password", default=os.environ.get("SOURCE_LDAP_PASSWORD", ""))
    p.add_argument("--source-netbios", default=os.environ.get("SOURCE_NETBIOS", "MYWIND"))

    p.add_argument("--target-host", default=os.environ.get("TARGET_LDAP_HOST", "dltornado2.com"))
    p.add_argument("--target-port", type=int, default=int(os.environ.get("TARGET_LDAP_PORT", "389")))
    p.add_argument("--target-ldaps-port", type=int, default=int(os.environ.get("TARGET_LDAPS_PORT", "636")))
    p.add_argument("--target-user", default=os.environ.get("TARGET_LDAP_USER", ""))
    p.add_argument("--target-password", default=os.environ.get("TARGET_LDAP_PASSWORD", ""))
    p.add_argument("--target-netbios", default=os.environ.get("TARGET_NETBIOS", "DLTORNADO2"))
    return p.parse_args()


def prompt_secret(label: str, env_value: str) -> str:
    if env_value:
        return env_value
    return getpass.getpass(f"{label}: ")


def main() -> int:
    args = parse_args()

    source_user = args.source_user or input("Source LDAP user (MYWIND\\user): ").strip()
    target_user = args.target_user or input("Target LDAP user (DLTORNADO2\\user): ").strip()
    source_user = normalize_bind_user(source_user, args.source_netbios, "mywind.com.cn")
    target_user = normalize_bind_user(target_user, args.target_netbios, TARGET_UPN_SUFFIX)

    source_password = prompt_secret("Source LDAP password", args.source_password)
    target_password = prompt_secret("Target LDAP password", args.target_password)

    set_password = args.set_password
    if not args.what_if and not set_password:
        print("NOTE: users created without password unless you pass --set-password (needs LDAPS on target).")

    print("\nAD Sync (Python/LDAP): AI Tech Center")
    print(f"  Source: {args.source_host}")
    print(f"  Target: {args.target_host} -> myse\\IT\n")

    src = connect_ldap(
        "production",
        args.source_host,
        source_user,
        source_password,
        use_ssl=False,
        port=args.source_port,
    )
    test_base(src, SOURCE_SEARCH_BASE, "production")
    ous, users, groups = read_subtree(src, skip_groups=args.skip_groups)
    src.unbind()

    if args.save_json:
        save_json(Path(args.save_json), ous, users, groups)

    tgt = connect_ldap(
        "test",
        args.target_host,
        target_user,
        target_password,
        use_ssl=set_password,
        port=args.target_ldaps_port if set_password else args.target_port,
    )
    test_base(tgt, TARGET_DOMAIN_SUFFIX, "test")

    write_subtree(
        tgt,
        ous,
        users,
        groups,
        what_if=args.what_if,
        sam_suffix=args.sam_suffix,
        default_password=args.default_password,
        set_password=set_password and not args.what_if,
        skip_groups=args.skip_groups,
    )
    tgt.unbind()

    print("")
    if args.what_if:
        print("WhatIf done. Re-run without --what-if to apply.")
    else:
        print("Sync completed.")
        print(f"Test login: sAMAccountName{args.sam_suffix}@{TARGET_UPN_SUFFIX}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(130) from None
