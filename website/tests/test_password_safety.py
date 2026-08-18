from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from password_safety import hash_password, migrate_env_file, verify_password


class PasswordHashTests(unittest.TestCase):
    def test_hash_verifies_same_password(self):
        stored = hash_password("SafePass#2026", iterations=100000)
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        self.assertTrue(verify_password("SafePass#2026", stored))

    def test_wrong_password_is_rejected(self):
        stored = hash_password("SafePass#2026", iterations=100000)
        self.assertFalse(verify_password("WrongPass#2026", stored))

    def test_same_password_gets_unique_salt(self):
        first = hash_password("SafePass#2026", iterations=100000)
        second = hash_password("SafePass#2026", iterations=100000)
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("SafePass#2026", first))
        self.assertTrue(verify_password("SafePass#2026", second))

    def test_invalid_stored_value_is_rejected(self):
        self.assertFalse(verify_password("SafePass#2026", "plaintext-password"))
        self.assertFalse(verify_password("SafePass#2026", ""))

    def test_constant_time_equals_handles_different_lengths(self):
        from password_safety import constant_time_equals

        self.assertTrue(constant_time_equals("admin@jeddah.local", "admin@jeddah.local"))
        self.assertFalse(constant_time_equals("a", "admin@jeddah.local"))
        self.assertFalse(constant_time_equals(None, "x"))


class EnvMigrationTests(unittest.TestCase):
    def test_replaces_plaintext_password_with_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("MANAGER_EMAIL=admin@jeddah.local\nMANAGER_PASSWORD=TempPass#2026\n", encoding="utf-8")
            self.assertTrue(migrate_env_file(env_path))
            text = env_path.read_text(encoding="utf-8")
            self.assertIn("MANAGER_PASSWORD_HASH=pbkdf2_sha256$", text)
            self.assertNotIn("MANAGER_PASSWORD=", text)
            stored = text.split("MANAGER_PASSWORD_HASH=", 1)[1].strip()
            self.assertTrue(verify_password("TempPass#2026", stored))


if __name__ == "__main__":
    unittest.main()
