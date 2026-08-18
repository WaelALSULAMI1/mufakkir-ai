from __future__ import annotations

import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["SECRET_KEY"] = "unit-test-secret-key-not-for-production"
os.environ["APP_ENV"] = "development"
os.environ["MODEL_MODE"] = "disabled"

import _isolate_db  # noqa: F401  — isolate test DB before app import
from audit import write_audit
from database import LOCKOUT_LIMIT, clear_auth_failures, init_db, is_ip_locked, record_auth_failure


class HealthDisclosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from app import app

        cls.client = TestClient(app, raise_server_exceptions=False)

    def test_health_does_not_expose_internal_endpoints(self):
        response = self.client.get("/api/health")
        body = response.text.lower()
        self.assertIn(response.status_code, {200, 503})
        self.assertIn("ok", response.json())
        self.assertNotIn("http://", body)
        self.assertNotIn("8090", body)
        self.assertNotIn("qwen", body)
        self.assertNotIn("api_url", body)

    def test_about_page_does_not_expose_internal_terms(self):
        response = self.client.get("/about")
        body = response.text.lower()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("qwen", body)
        self.assertNotIn("cuda", body)
        self.assertNotIn("peft", body)
        self.assertNotIn("directory traversal", body)


class ResultAccessTests(unittest.TestCase):
    def test_result_is_limited_to_submitter_session(self):
        from fastapi.testclient import TestClient
        import app as app_module

        app_module.RATE_BUCKETS.clear()
        owner = TestClient(app_module.app, raise_server_exceptions=False)
        register = owner.get("/register")
        token = re.search(r'name="csrf_token" value="([^"]+)"', register.text)
        self.assertIsNotNone(token)
        created = owner.post(
            "/register",
            data={
                "csrf_token": token.group(1),
                "full_name": "موظف اختبار",
                "email": f"emp-{os.urandom(4).hex()}@jeddah.local",
                "password": "Employee123!",
            },
            follow_redirects=False,
        )
        self.assertEqual(created.status_code, 303)

        page = owner.get("/submit")
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        self.assertIsNotNone(token)
        submitted = owner.post(
            "/submit",
            data={
                "csrf_token": token.group(1),
                "department": "تقنية المعلومات",
                "title": "تعطل نظام المراسلات الداخلية",
                "problem": "النظام لا يفتح من الصباح ويؤثر على المراجعين في القسم.",
                "employee_suggestion": "",
                "resources": "",
                "constraints": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(submitted.status_code, 303)
        location = submitted.headers.get("location", "")
        self.assertTrue(re.fullmatch(r"/result/[0-9a-f]{32}", location))

        owner_view = owner.get(location)
        self.assertEqual(owner_view.status_code, 200)

        stranger = TestClient(app_module.app, raise_server_exceptions=False)
        stranger_view = stranger.get(location)
        self.assertEqual(stranger_view.status_code, 404)
        self.assertNotIn("تفاصيل التقييم", owner_view.text)
        self.assertNotIn("من 100", owner_view.text)

    def test_logged_in_employee_cannot_open_another_result(self):
        from fastapi.testclient import TestClient
        import app as app_module

        app_module.RATE_BUCKETS.clear()
        owner = TestClient(app_module.app, raise_server_exceptions=False)
        token = re.search(r'name="csrf_token" value="([^"]+)"', owner.get("/register").text)
        owner.post(
            "/register",
            data={
                "csrf_token": token.group(1),
                "full_name": "موظف أ",
                "email": f"a-{os.urandom(4).hex()}@jeddah.local",
                "password": "Employee123!",
            },
            follow_redirects=False,
        )
        page = owner.get("/submit")
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        submitted = owner.post(
            "/submit",
            data={
                "csrf_token": token.group(1),
                "department": "تقنية المعلومات",
                "title": "تعطل نظام المراسلات الداخلية",
                "problem": "النظام لا يفتح من الصباح ويؤثر على المراجعين في القسم.",
                "employee_suggestion": "",
                "resources": "",
                "constraints": "",
            },
            follow_redirects=False,
        )
        location = submitted.headers.get("location", "")
        other = TestClient(app_module.app, raise_server_exceptions=False)
        token = re.search(r'name="csrf_token" value="([^"]+)"', other.get("/register").text)
        other.post(
            "/register",
            data={
                "csrf_token": token.group(1),
                "full_name": "موظف ب",
                "email": f"b-{os.urandom(4).hex()}@jeddah.local",
                "password": "Employee123!",
            },
            follow_redirects=False,
        )
        self.assertEqual(other.get(location).status_code, 404)

    def test_short_csrf_token_is_forbidden_not_a_crash(self):
        from fastapi.testclient import TestClient
        import app as app_module

        app_module.RATE_BUCKETS.clear()
        client = TestClient(app_module.app, raise_server_exceptions=True)
        client.get("/login")
        response = client.post(
            "/login",
            data={
                "csrf_token": "x",
                "email": "nobody@jeddah.local",
                "password": "Employee123!",
                "role": "employee",
                "next": "/submit",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 403)

    def test_manager_login_mismatched_email_length_does_not_crash(self):
        from fastapi.testclient import TestClient
        import app as app_module

        app_module.RATE_BUCKETS.clear()
        client = TestClient(app_module.app, raise_server_exceptions=True)
        page = client.get("/login?role=manager")
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        self.assertIsNotNone(token)
        response = client.post(
            "/login",
            data={
                "csrf_token": token.group(1),
                "email": "a@b.c",
                "password": "Employee123!",
                "role": "manager",
                "next": "/manager",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 401)


class LockoutAndAuditTests(unittest.TestCase):
    def test_repeated_failures_lock_an_address(self):
        ip = "203.0.113.10"
        init_db()
        clear_auth_failures(ip)
        self.assertFalse(is_ip_locked(ip))
        for _ in range(LOCKOUT_LIMIT):
            record_auth_failure(ip)
        self.assertTrue(is_ip_locked(ip))
        clear_auth_failures(ip)
        self.assertFalse(is_ip_locked(ip))

    def test_audit_writes_allowed_events_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.log"
            with patch("audit.AUDIT_PATH", path):
                write_audit("login_failure", "203.0.113.10", "denied")
                write_audit("not-a-real-event", "bad\nip", "denied")
            text = path.read_text(encoding="utf-8")
            self.assertIn("login_failure", text)
            self.assertIn("unknown", text)
            self.assertNotIn("not-a-real-event", text)
            self.assertNotIn("\nip", text)


if __name__ == "__main__":
    unittest.main()
