from __future__ import annotations

import json
import os
import re
import unittest
from unittest.mock import patch

os.environ.setdefault("SECRET_KEY", "unit-test-secret-key-not-for-production")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("MODEL_MODE", "disabled")

import _isolate_db  # noqa: F401

from password_safety import hash_password

MANAGER_HASH = hash_password("AdminTest-123!")


def _csrf(text: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', text)
    if not match:
        raise AssertionError("missing csrf token")
    return match.group(1)


class AuthAndNotificationTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        import app as app_module

        self.app_module = app_module
        self.email_patch = patch.object(app_module, "MANAGER_EMAIL", "admin@jeddah.local")
        self.hash_patch = patch.object(app_module, "MANAGER_PASSWORD_HASH", MANAGER_HASH)
        self.email_patch.start()
        self.hash_patch.start()
        app_module.RATE_BUCKETS.clear()
        self.client = TestClient(app_module.app, raise_server_exceptions=False)
        self.employee_email = f"staff-{os.urandom(4).hex()}@jeddah.local"

    def tearDown(self):
        self.email_patch.stop()
        self.hash_patch.stop()

    def test_submit_requires_employee_login(self):
        response = self.client.get("/submit", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn("/login", response.headers.get("location", ""))

    def test_analyze_stream_has_no_fake_stages_when_model_disabled(self):
        token = _csrf(self.client.get("/register").text)
        created = self.client.post(
            "/register",
            data={
                "csrf_token": token,
                "full_name": "علي",
                "email": self.employee_email,
                "password": "Employee123!",
            },
            follow_redirects=False,
        )
        self.assertEqual(created.status_code, 303)
        page = self.client.get("/submit")
        response = self.client.post(
            "/api/analyze",
            headers={"Accept": "application/x-ndjson"},
            json={
                "csrf_token": _csrf(page.text),
                "department": "تقنية المعلومات",
                "title": "تعطل نظام المراسلات",
                "problem": "النظام لا يفتح من الصباح ويؤثر على المراجعين في القسم.",
                "employee_suggestion": "",
                "resources": "",
                "constraints": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("ndjson", response.headers.get("content-type", ""))
        events = [line for line in response.text.splitlines() if line.strip()]
        parsed = [json.loads(line) for line in events]
        self.assertTrue(parsed)
        self.assertFalse(any(item.get("stage") for item in parsed))
        final = parsed[-1]
        self.assertIn("redirect", final)
        self.assertRegex(final["redirect"], r"^/result/[0-9a-f]{32}$")

    def test_cannot_register_with_manager_email(self):
        token = _csrf(self.client.get("/register").text)
        response = self.client.post(
            "/register",
            data={
                "csrf_token": token,
                "full_name": "محاولة مدير",
                "email": "admin@jeddah.local",
                "password": "Employee123!",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("المدير", response.text)

    def test_employee_register_login_and_manager_decision_notify(self):
        token = _csrf(self.client.get("/register").text)
        created = self.client.post(
            "/register",
            data={
                "csrf_token": token,
                "full_name": "موظف الإشعارات",
                "email": self.employee_email,
                "password": "Employee123!",
            },
            follow_redirects=False,
        )
        self.assertEqual(created.status_code, 303)

        submit_page = self.client.get("/submit")
        submitted = self.client.post(
            "/submit",
            data={
                "csrf_token": _csrf(submit_page.text),
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
        result_path = submitted.headers.get("location", "")
        suggestion_id = result_path.rsplit("/", 1)[-1]

        logout_page = self.client.get("/")
        self.client.post("/logout", data={"csrf_token": _csrf(logout_page.text)}, follow_redirects=False)

        login_page = self.client.get("/login?role=manager")
        manager_login = self.client.post(
            "/login",
            data={
                "csrf_token": _csrf(login_page.text),
                "email": "admin@jeddah.local",
                "password": "AdminTest-123!",
                "role": "manager",
                "next": "/manager",
            },
            follow_redirects=False,
        )
        self.assertEqual(manager_login.status_code, 303)
        self.assertEqual(manager_login.headers.get("location"), "/manager")

        manager_result = self.client.get(f"/manager/result/{suggestion_id}")
        self.assertEqual(manager_result.status_code, 200)
        decided = self.client.post(
            f"/manager/result/{suggestion_id}/decision",
            data={
                "csrf_token": _csrf(manager_result.text),
                "decision": "adopted",
                "manager_note": "يعتمد كتجربة في قسم واحد.",
            },
            follow_redirects=False,
        )
        self.assertEqual(decided.status_code, 303)

        self.client.post("/logout", data={"csrf_token": _csrf(self.client.get("/").text)}, follow_redirects=False)
        employee_login = self.client.post(
            "/login",
            data={
                "csrf_token": _csrf(self.client.get("/login?role=employee").text),
                "email": self.employee_email,
                "password": "Employee123!",
                "role": "employee",
                "next": "/notifications",
            },
            follow_redirects=False,
        )
        self.assertEqual(employee_login.status_code, 303)
        inbox = self.client.get("/notifications")
        self.assertEqual(inbox.status_code, 200)
        self.assertIn("اُعتمد", inbox.text)
        self.assertIn("تحسين مسار المراجعين", inbox.text)
        mine = self.client.get("/my-suggestions")
        self.assertEqual(mine.status_code, 200)
        self.assertIn("تحسين مسار المراجعين", mine.text)
        self.assertIn("اُعتمد", mine.text)
        self.assertIn("يعتمد كتجربة في قسم واحد.", mine.text)

    def test_employee_sees_previous_suggestions_pending_review(self):
        token = _csrf(self.client.get("/register").text)
        self.client.post(
            "/register",
            data={
                "csrf_token": token,
                "full_name": "علي",
                "email": self.employee_email,
                "password": "Employee123!",
            },
            follow_redirects=False,
        )
        home = self.client.get("/")
        self.assertIn("account-menu", home.text)
        self.assertIn("اقتراحاتي السابقة", home.text)
        self.assertNotIn("header-logout", home.text)
        self.assertRegex(home.text, r"رقم الموظف م-[A-Z2-9]{6}")
        submit_page = self.client.get("/submit")
        submitted = self.client.post(
            "/submit",
            data={
                "csrf_token": _csrf(submit_page.text),
                "department": "تقنية المعلومات",
                "title": "مقترح علي السابق",
                "problem": "الازدحام صباحًا يعيق إنجاز المعاملات في القسم.",
                "employee_suggestion": "تنظيم مواعيد مسبقة",
                "resources": "",
                "constraints": "",
            },
            follow_redirects=False,
        )
        self.assertEqual(submitted.status_code, 303)
        mine = self.client.get("/my-suggestions")
        self.assertEqual(mine.status_code, 200)
        self.assertIn("مقترح علي السابق", mine.text)
        self.assertIn("يحتاج مراجعة المدير", mine.text)
        result_path = submitted.headers.get("location", "")
        result = self.client.get(result_path)
        self.assertEqual(result.status_code, 200)
        self.assertIn("يحتاج مراجعة المدير", result.text)

    def test_my_suggestions_requires_login(self):
        response = self.client.get("/my-suggestions", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertIn("/login", response.headers.get("location", ""))

    def test_employee_cannot_open_manager_dashboard(self):
        token = _csrf(self.client.get("/register").text)
        created = self.client.post(
            "/register",
            data={
                "csrf_token": token,
                "full_name": "علي",
                "email": self.employee_email,
                "password": "Employee123!",
            },
            follow_redirects=False,
        )
        self.assertEqual(created.status_code, 303)
        denied = self.client.get("/manager", follow_redirects=False)
        self.assertEqual(denied.status_code, 303)
        self.assertEqual(denied.headers.get("location"), "/")
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn("notice danger", home.text)
        self.assertIn("لا يمكنك دخول لوحة المدير", home.text)
        self.assertNotIn("ranking-list", home.text)
        self.assertIn("أفضل المقترحات", home.text)
        self.assertIn('href="/manager"', home.text)
        login_try = self.client.get("/login?role=manager", follow_redirects=False)
        self.assertEqual(login_try.status_code, 303)
        self.assertEqual(login_try.headers.get("location"), "/")

    def test_manager_opening_submit_sees_explanation_not_ranking(self):
        login_page = self.client.get("/login?role=manager")
        manager_login = self.client.post(
            "/login",
            data={
                "csrf_token": _csrf(login_page.text),
                "email": "admin@jeddah.local",
                "password": "AdminTest-123!",
                "role": "manager",
                "next": "/manager",
            },
            follow_redirects=False,
        )
        self.assertEqual(manager_login.status_code, 303)
        response = self.client.get("/submit", follow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn("تقديم المقترح من حساب الموظف", response.text)
        self.assertIn("هذا الحساب للمراجعة", response.text)
        self.assertIn("فتح لوحة المراجعة", response.text)
        self.assertNotIn("ranking-list", response.text)
        self.assertNotIn("data-loading-form", response.text)


if __name__ == "__main__":
    unittest.main()
