#!/usr/bin/env python3
"""Reset a test-domain user password and clear 'must change at next logon'.

Requires LDAPS (636) and an account with reset-password rights on the target DC.

Example:
  export TARGET_LDAP_HOST=dc01.dltornado2.com
  export TARGET_LDAP_USER='DLTORNADO2\\admin'
  export TARGET_LDAP_PASSWORD='***'
  python reset_test_user_password.py --sam A01309 --password 'ChangeMe!2026'
"""

from __future__ import annotations

import argparse
import os
import ssl
import sys

from ldap3 import ALL, MODIFY_REPLACE, SUBTREE, Connection, Server, Tls
from ldap3.utils.conv import escape_filter_chars


def encode_ad_password(password: str) -> bytes:
    return f'"{password}"'.encode("utf-16-le")


def main() -> int:
    p = argparse.ArgumentParser(description="Reset test AD user password for MeetMemo login")
    p.add_argument("--host", default=os.environ.get("TARGET_LDAP_HOST", "dc01.dltornado2.com"))
    p.add_argument("--user", default=os.environ.get("TARGET_LDAP_USER"))
    p.add_argument("--password", default=os.environ.get("TARGET_LDAP_PASSWORD"))
    p.add_argument("--base-dn", default="OU=myse,DC=dltornado2,DC=com")
    p.add_argument("--sam", required=True, help="sAMAccountName, e.g. A01309")
    p.add_argument("--new-password", default=os.environ.get("DEFAULT_AD_PASSWORD", "ChangeMe!2026"))
    args = p.parse_args()

    if not args.user or not args.password:
        print("Set --user/--password or TARGET_LDAP_USER / TARGET_LDAP_PASSWORD", file=sys.stderr)
        return 1

    tls = Tls(validate=ssl.CERT_NONE)
    server = Server(args.host.replace("ldaps://", "").replace("ldap://", ""), port=636, use_ssl=True, tls=tls, get_info=ALL)
    conn = Connection(server, user=args.user, password=args.password, auto_bind=True)

    safe_sam = escape_filter_chars(args.sam)
    conn.search(args.base_dn, f"(sAMAccountName={safe_sam})", search_scope=SUBTREE, attributes=["distinguishedName"])
    if not conn.entries:
        print(f"User not found: {args.sam}", file=sys.stderr)
        return 1

    dn = conn.entries[0].entry_dn
    print(f"Resetting: {dn}")

    conn.modify(dn, {"unicodePwd": [(MODIFY_REPLACE, [encode_ad_password(args.new_password)])]})
    if conn.result["result"] != 0:
        print("unicodePwd failed:", conn.result, file=sys.stderr)
        return 1

    conn.modify(dn, {"pwdLastSet": [(MODIFY_REPLACE, ["-1"])]})
    if conn.result["result"] != 0:
        print("pwdLastSet failed:", conn.result, file=sys.stderr)
        return 1

    print("OK. User can sign in to MeetMemo with sam or mail + new password.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
