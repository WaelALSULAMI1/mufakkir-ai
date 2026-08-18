from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from pathlib import Path

SCHEME = "pbkdf2_sha256"
ITERATIONS = 260000
MAX_PASSWORD_LENGTH = 256
HASH_RE = re.compile(rf"^{SCHEME}\$(\d+)\$([0-9a-f]+)\$([0-9a-f]+)$")


def hash_password(password: str, *, iterations: int = ITERATIONS) -> str:
    if not password or len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError("كلمة المرور غير صالحة.")
    if iterations < 100000 or iterations > 1_000_000:
        raise ValueError("عدد دورات التهشير غير صالح.")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations)
    return f"{SCHEME}${iterations}${salt}${digest.hex()}"


def constant_time_equals(left: str | None, right: str | None) -> bool:
    left_digest = hashlib.sha256((left or "").encode("utf-8")).digest()
    right_digest = hashlib.sha256((right or "").encode("utf-8")).digest()
    return hmac.compare_digest(left_digest, right_digest)


def verify_password(password: str, stored_hash: str) -> bool:
    if not password or len(password) > MAX_PASSWORD_LENGTH:
        return False
    match = HASH_RE.fullmatch(stored_hash or "")
    if not match:
        return False
    iterations = int(match.group(1))
    if iterations < 100000 or iterations > 1_000_000:
        return False
    try:
        salt = bytes.fromhex(match.group(2))
        expected = bytes.fromhex(match.group(3))
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def load_password_hash() -> str:
    stored = (os.getenv("MANAGER_PASSWORD_HASH") or "").strip()
    if HASH_RE.fullmatch(stored):
        return stored
    legacy = os.getenv("MANAGER_PASSWORD") or ""
    if legacy:
        return hash_password(legacy)
    raise RuntimeError("MANAGER_PASSWORD_HASH غير مضبوط. شغّل python hash_manager_password.py ثم حدّث ملف .env")


def migrate_env_file(env_path: Path, *, default_password: str | None = None) -> bool:
    if not env_path.is_file():
        return False
    text = env_path.read_text(encoding="utf-8")
    password_match = re.search(r"^MANAGER_PASSWORD=(.*)$", text, flags=re.MULTILINE)
    hash_match = re.search(r"^MANAGER_PASSWORD_HASH=(.*)$", text, flags=re.MULTILINE)
    if hash_match and HASH_RE.fullmatch(hash_match.group(1).strip()):
        if password_match:
            text = re.sub(r"^MANAGER_PASSWORD=.*$\n?", "", text, flags=re.MULTILINE)
            env_path.write_text(text, encoding="utf-8")
            return True
        return False
    password = ""
    if password_match:
        password = password_match.group(1).strip().strip('"').strip("'")
    if not password:
        password = default_password or ""
    if not password:
        return False
    hashed = hash_password(password)
    if hash_match:
        text = re.sub(r"^MANAGER_PASSWORD_HASH=.*$", f"MANAGER_PASSWORD_HASH={hashed}", text, flags=re.MULTILINE)
    elif password_match:
        text = re.sub(r"^MANAGER_PASSWORD=.*$", f"MANAGER_PASSWORD_HASH={hashed}", text, flags=re.MULTILINE)
    else:
        text = text.rstrip() + f"\nMANAGER_PASSWORD_HASH={hashed}\n"
    text = re.sub(r"^MANAGER_PASSWORD=.*$\n?", "", text, flags=re.MULTILINE)
    env_path.write_text(text, encoding="utf-8")
    return True
