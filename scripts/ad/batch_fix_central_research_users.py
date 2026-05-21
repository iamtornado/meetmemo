#!/usr/bin/env python3
"""Batch-fix AD users under 中央研究院 OU for MeetMemo / test login.

For each user object in the subtree:
  - Clear "must change password at next logon" (pwdLastSet = -1)
  - Enable "Password never expires" (userAccountControl |= DONT_EXPIRE_PASSWD)

Requires LDAPS (636) and an account with modify rights on those users
(typically test-domain admin). Does not change passwords unless --set-password.

Examples:
  export TARGET_LDAP_HOST=dc01.dltornado2.com
  export TARGET_LDAP_USER='DLTORNADO2\\admin'
  export TARGET_LDAP_PASSWORD='***'

  python batch_fix_central_research_users.py --what-if
  python batch_fix_central_research_users.py
  python batch_fix_central_research_users.py --set-password --default-password 'ChangeMe!2026'
"""

from __future__ import annotations

import argparse
import os
import ssl
import sys
from dataclasses import dataclass

from ldap3 import ALL, MODIFY_REPLACE, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException

# Match sync_ai_tech_center.py test-domain layout
TARGET_DOMAIN_SUFFIX = "OU=IT,OU=myse,DC=dltornado2,DC=com"
DEFAULT_SEARCH_BASE = f"OU=中央研究院,{TARGET_DOMAIN_SUFFIX}"

# UF_DONT_EXPIRE_PASSWD
UAC_PASSWORD_NEVER_EXPIRES = 0x10000

USER_FILTER = "(&(objectCategory=person)(objectClass=user))"


def encode_ad_password(password: str) -> bytes:
    return f'"{password}"'.encode("utf-16-le")


def make_connection(host: str, user: str, password: str, *, port: int = 636) -> Connection:
    host = host.replace("ldap://", "").replace("ldaps://", "").strip()
    tls = Tls(validate=ssl.CERT_NONE)
    server = Server(host, port=port, use_ssl=True, tls=tls, get_info=ALL)
    return Connection(server, user=user, password=password, auto_bind=True, receive_timeout=60)


def pwd_must_change(pwd_last_set: object) -> bool:
    """True when AD expects a password change at next logon."""
    if pwd_last_set is None:
        return False
    if isinstance(pwd_last_set, int):
        return pwd_last_set == 0
    # ldap3 may return datetime for 0 / unset
    s = str(pwd_last_set)
    return s.startswith("1601-01-01")


@dataclass
class UserRow:
    dn: str
    sam: str
    uac: int
    pwd_last_set: object


def load_users(conn: Connection, base_dn: str) -> list[UserRow]:
    conn.search(
        base_dn,
        USER_FILTER,
        search_scope=SUBTREE,
        attributes=["sAMAccountName", "userAccountControl", "pwdLastSet"],
    )
    rows: list[UserRow] = []
    for entry in conn.entries:
        sam = entry.sAMAccountName.value if "sAMAccountName" in entry else "?"
        uac = int(entry.userAccountControl.value) if "userAccountControl" in entry else 0
        pwd_last = entry.pwdLastSet.value if "pwdLastSet" in entry else None
        rows.append(UserRow(dn=entry.entry_dn, sam=sam, uac=uac, pwd_last_set=pwd_last))
    return rows


def apply_fix(
    conn: Connection,
    row: UserRow,
    *,
    what_if: bool,
    set_password: bool,
    default_password: str,
) -> tuple[bool, bool, str | None]:
    """Returns (pwd_last_set_changed, uac_changed, error)."""
    new_uac = row.uac | UAC_PASSWORD_NEVER_EXPIRES
    need_uac = new_uac != row.uac
    need_pwd_last = pwd_must_change(row.pwd_last_set)

    if what_if:
        flags = []
        if need_pwd_last or set_password:
            flags.append("pwdLastSet=-1")
        if set_password:
            flags.append("unicodePwd=***")
        if need_uac:
            flags.append(f"userAccountControl={row.uac}->{new_uac}")
        if not flags:
            flags.append("(already OK)")
        print(f"  [what-if] {row.sam}: {', '.join(flags)}")
        return need_pwd_last, need_uac, None

    err: str | None = None

    if set_password:
        try:
            conn.modify(
                row.dn,
                {"unicodePwd": [(MODIFY_REPLACE, [encode_ad_password(default_password)])]},
            )
            if conn.result["result"] != 0:
                return False, False, f"unicodePwd: {conn.result['description']}"
        except LDAPException as exc:
            return False, False, f"unicodePwd: {exc}"

    if need_pwd_last or set_password:
        conn.modify(row.dn, {"pwdLastSet": [(MODIFY_REPLACE, ["-1"])]})
        if conn.result["result"] != 0:
            err = f"pwdLastSet: {conn.result['description']}"

    if need_uac:
        conn.modify(row.dn, {"userAccountControl": [(MODIFY_REPLACE, [str(new_uac)])]})
        if conn.result["result"] != 0:
            uac_err = f"userAccountControl: {conn.result['description']}"
            err = f"{err}; {uac_err}" if err else uac_err

    return need_pwd_last or set_password, need_uac, err


def main() -> int:
    p = argparse.ArgumentParser(
        description="Batch clear must-change-password and set password-never-expires "
        "for all users under 中央研究院 OU"
    )
    p.add_argument("--host", default=os.environ.get("TARGET_LDAP_HOST", "dc01.dltornado2.com"))
    p.add_argument("--user", default=os.environ.get("TARGET_LDAP_USER"))
    p.add_argument("--password", default=os.environ.get("TARGET_LDAP_PASSWORD"))
    p.add_argument("--port", type=int, default=636)
    p.add_argument(
        "--base-dn",
        default=DEFAULT_SEARCH_BASE,
        help=f"Search root (default: {DEFAULT_SEARCH_BASE})",
    )
    p.add_argument("--what-if", action="store_true", help="List planned changes only")
    p.add_argument(
        "--set-password",
        action="store_true",
        help="Also reset password to --default-password (requires reset-password ACL)",
    )
    p.add_argument(
        "--default-password",
        default=os.environ.get("DEFAULT_AD_PASSWORD", "ChangeMe!2026"),
    )
    args = p.parse_args()

    if not args.user or not args.password:
        print("Set --user/--password or TARGET_LDAP_USER / TARGET_LDAP_PASSWORD", file=sys.stderr)
        return 1

    print(f">>> Connect {args.host}:{args.port} (LDAPS) as {args.user}")
    try:
        conn = make_connection(args.host, args.user, args.password, port=args.port)
    except LDAPException as exc:
        print(f"Bind failed: {exc}", file=sys.stderr)
        return 1
    print("    OK")

    print(f">>> Search users under: {args.base_dn}")
    users = load_users(conn, args.base_dn)
    print(f"    Found {len(users)} user(s)")
    if not users:
        return 0

    ok = fail = skip = 0
    for row in sorted(users, key=lambda r: r.sam.lower()):
        print(f"[{row.sam}] {row.dn}")
        changed_pwd, changed_uac, error = apply_fix(
            conn,
            row,
            what_if=args.what_if,
            set_password=args.set_password,
            default_password=args.default_password,
        )
        if error:
            print(f"    FAIL: {error}")
            fail += 1
        elif changed_pwd or changed_uac or args.set_password:
            if not args.what_if:
                print("    OK")
            ok += 1
        else:
            print("    SKIP (already OK)")
            skip += 1

    mode = "what-if" if args.what_if else "applied"
    print(f">>> Done ({mode}): ok={ok} skip={skip} fail={fail} total={len(users)}")
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
