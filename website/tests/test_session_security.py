from __future__ import annotations

import os
import re
import unittest
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "unit-test-secret-key-not-for-production")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("MODEL_MODE", "disabled")

import _isolate_db  # noqa: F401

from session_security import SESSION_ABSOLUTE_SECONDS, SESSION_IDLE_SECONDS, now_ts


def _csrf(text: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text)
    if not match:
        raise AssertionError("missing csrf token")
    return match.group(1)


def _register_employee(client, name: str = "علي") -> None:
    token = _csrf(client.get("/register").text)
    created = client.post(
        "/register",
        data={
            "csrf_token": token,
            "full_name": name,
            "email": f"staff-{os.urandom(4).hex()}@jeddah.local",
            "password": "Employee123!",
        },
        follow_redirects=False,
    )
    if created.status_code != 303:
        raise AssertionError(created.text)


class SessionCookieTests(unittest.TestCase):
    def setUp(self):
        import app as app_module

        app_module.RATE_BUCKETS.clear()
    def test_login_cookie_is_httponly_and_samesite_lax(self):
        from fastapi.testclient import TestClient
        from app import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/register",
            data={
                "csrf_token": _csrf(client.get("/register").text),
                "full_name": "علي",
                "email": f"staff-{os.urandom(4).hex()}@jeddah.local",
                "password": "Employee123!",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        cookie = (response.headers.get("set-cookie") or "").lower()
        self.assertIn("jeddah_session=", cookie)
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)
        self.assertNotIn("secure", cookie)

    def test_stolen_cookie_from_another_browser_is_rejected(self):
        from fastapi.testclient import TestClient
        from app import app

        owner = TestClient(app, raise_server_exceptions=False, headers={"user-agent": "Mozilla/5.0 OfficePC"})
        _register_employee(owner)
        mine = owner.get("/my-suggestions")
        self.assertEqual(mine.status_code, 200)

        stolen = TestClient(app, raise_server_exceptions=False, headers={"user-agent": "Mozilla/5.0 Attacker"})
        stolen.cookies.update(owner.cookies)
        hijacked = stolen.get("/my-suggestions", follow_redirects=False)
        self.assertEqual(hijacked.status_code, 303)
        self.assertIn("/login", hijacked.headers.get("location", ""))
        self.assertEqual(owner.get("/my-suggestions").status_code, 200)

    def test_idle_session_expires(self):
        from fastapi.testclient import TestClient
        from app import app

        client = TestClient(app, raise_server_exceptions=False)
        _register_employee(client)
        later = now_ts() + SESSION_IDLE_SECONDS + 5
        with patch("session_security.now_ts", return_value=later):
            expired = client.get("/my-suggestions", follow_redirects=False)
        self.assertEqual(expired.status_code, 303)
        self.assertIn("/login", expired.headers.get("location", ""))

    def test_absolute_session_expires(self):
        from fastapi.testclient import TestClient
        from app import app

        client = TestClient(app, raise_server_exceptions=False)
        _register_employee(client)
        later = now_ts() + SESSION_ABSOLUTE_SECONDS + 5
        with patch("session_security.now_ts", return_value=later):
            expired = client.get("/submit", follow_redirects=False)
        self.assertEqual(expired.status_code, 303)
        self.assertIn("/login", expired.headers.get("location", ""))


class PublicCodeTests(unittest.TestCase):
    def setUp(self):
        import app as app_module

        app_module.RATE_BUCKETS.clear()
    def test_employee_and_suggestion_get_readable_codes(self):
        from fastapi.testclient import TestClient
        from app import app

        client = TestClient(app, raise_server_exceptions=False)
        _register_employee(client, "علي")
        home = client.get("/")
        self.assertRegex(home.text, r"رقم الموظف م-[A-Z2-9]{6}")
        submitted = client.post(
            "/submit",
            data={
                "csrf_token": _csrf(client.get("/submit").text),
                "department": "تقنية المعلومات",
                "title": "تحسين مسار المراجعين",
                "problem": "الازدحام صباحًا يعيق إنجاز المعاملات في القسم.",
                "employee_suggestion": "تنظيم مواعيد مسبقة",
                "resources": "",
                "constraints": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(submitted.status_code, 303)
        result = client.get(submitted.headers.get("location", ""))
        self.assertRegex(result.text, r"رقم المقترح <strong[^>]*>ق-[A-Z2-9]{6}</strong>")
        mine = client.get("/my-suggestions")
        self.assertRegex(mine.text, r"ق-[A-Z2-9]{6}")


if __name__ == "__main__":
    unittest.main()
