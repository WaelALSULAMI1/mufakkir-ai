from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

from password_safety import hash_password, migrate_env_file


def main() -> int:
    parser = argparse.ArgumentParser(description="تهشير كلمة مرور المدير بـ PBKDF2-SHA256.")
    parser.add_argument("password", nargs="?", help="كلمة المرور الجديدة")
    parser.add_argument("--migrate", action="store_true", help="حوّل MANAGER_PASSWORD في .env إلى هاش واحذف النص الواضح")
    parser.add_argument("--ensure-demo", action="store_true", help="إذا لم يوجد هاش، أنشئ كلمة مرور عشوائية لمرة واحدة")
    args = parser.parse_args()

    if args.migrate:
        generated = None
        default_password = None
        if args.ensure_demo:
            generated = secrets.token_urlsafe(16)
            default_password = generated
        changed = migrate_env_file(Path(".env"), default_password=default_password)
        if changed and generated:
            print("Created a one-time manager password. Save it now; it is not stored in plaintext:")
            print(generated)
        elif changed:
            print("Manager password hashed and plaintext removed.")
        else:
            print("No plaintext password to convert, or hash already exists.")
        return 0

    if not args.password:
        print("Usage: python hash_manager_password.py \"new-password\"")
        print("   or: python hash_manager_password.py --migrate")
        return 1

    print("MANAGER_PASSWORD_HASH=" + hash_password(args.password))
    print("Put this line in .env and delete MANAGER_PASSWORD if present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
