from __future__ import annotations

import os
import re
import unittest

os.environ["SECRET_KEY"] = "unit-test-secret-key-not-for-production"
os.environ["APP_ENV"] = "development"
os.environ["MODEL_MODE"] = "disabled"

import _isolate_db  # noqa: F401

from injection_guard import (
    is_safe_app_redirect,
    is_safe_next_path,
    sanitize_analysis,
    sanitize_email,
    sanitize_text,
    wrap_untrusted_data,
)
from model_schema import SuggestionInput
from pydantic import ValidationError


class SanitizeTextTests(unittest.TestCase):
    def test_keeps_arabic_text(self):
        self.assertEqual(sanitize_text("مشكلة في النظام"), "مشكلة في النظام")

    def test_removes_markup_from_titles(self):
        self.assertEqual(sanitize_text("<b>عنوان</b> واضح"), "عنوان واضح")

    def test_removes_line_breaks_from_single_line_fields(self):
        self.assertEqual(sanitize_text("عنوان\r\nثاني", allow_newlines=False), "عنوان ثاني")

    def test_keeps_paragraphs_in_long_fields(self):
        text = sanitize_text("سطر أول\n\nسطر ثاني", allow_newlines=True)
        self.assertEqual(text, "سطر أول\n\nسطر ثاني")


class SchemaSanitizationTests(unittest.TestCase):
    def test_accepts_clean_suggestion(self):
        data = SuggestionInput(
            department="تقنية المعلومات",
            title="تعطل نظام المراسلات",
            problem="النظام لا يفتح من الصباح ويؤثر على المراجعين.",
        )
        self.assertEqual(data.title, "تعطل نظام المراسلات")

    def test_strips_markup_before_validation(self):
        data = SuggestionInput(
            department="تقنية المعلومات",
            title="<em>تعطل نظام المراسلات</em>",
            problem="النظام لا يفتح من الصباح ويؤثر على المراجعين.",
        )
        self.assertEqual(data.title, "تعطل نظام المراسلات")
        self.assertNotIn("<", data.title)

    def test_rejects_empty_title_after_cleanup(self):
        with self.assertRaises(ValidationError):
            SuggestionInput(
                department="تقنية المعلومات",
                title="<script></script>",
                problem="النظام لا يفتح من الصباح ويؤثر على المراجعين.",
            )


class RedirectAndEmailTests(unittest.TestCase):
    def test_result_redirect_must_be_local_hex_path(self):
        self.assertTrue(is_safe_app_redirect("/result/" + "a" * 32))
        self.assertFalse(is_safe_app_redirect("https://example.com/result/" + "a" * 32))
        self.assertFalse(is_safe_app_redirect("/manager"))

    def test_login_next_path_is_allowlisted(self):
        self.assertTrue(is_safe_next_path("/submit"))
        self.assertTrue(is_safe_next_path("/manager"))
        self.assertTrue(is_safe_next_path("/notifications"))
        self.assertTrue(is_safe_next_path("/my-suggestions"))
        self.assertFalse(is_safe_next_path("https://evil.example/login"))
        self.assertFalse(is_safe_next_path("//evil.example"))

    def test_email_must_be_plain_and_valid(self):
        self.assertEqual(sanitize_email("Admin@Jeddah.Local"), "admin@jeddah.local")
        self.assertEqual(sanitize_email("admin@jeddah.local\r\nCc: x"), "")


class AnalysisAndPromptTests(unittest.TestCase):
    def test_analysis_strings_are_cleaned(self):
        cleaned = sanitize_analysis({"problem_summary": "<i>نص</i> نظيف", "score": 12})
        self.assertEqual(cleaned["problem_summary"], "نص نظيف")
        self.assertEqual(cleaned["score"], 12)

    def test_user_data_is_wrapped_as_data(self):
        wrapped = wrap_untrusted_data("العنوان", "تعطل النظام")
        self.assertIn("<<<USER_DATA", wrapped)
        self.assertIn("تعطل النظام", wrapped)


class StoredDataRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        import app as app_module

        app_module.RATE_BUCKETS.clear()
        cls.client = TestClient(app_module.app, raise_server_exceptions=False)

    def test_special_characters_are_escaped_in_html(self):
        page = self.client.get("/register")
        token_match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        self.assertIsNotNone(token_match)
        self.client.post(
            "/register",
            data={
                "csrf_token": token_match.group(1),
                "full_name": "موظف اختبار",
                "email": f"esc-{os.urandom(4).hex()}@jeddah.local",
                "password": "Employee123!",
            },
            follow_redirects=False,
        )
        page = self.client.get("/submit")
        token_match = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
        self.assertIsNotNone(token_match)
        response = self.client.post(
            "/submit",
            data={
                "csrf_token": token_match.group(1),
                "department": "تقنية المعلومات",
                "title": 'مشكلة "عاجلة" & واضحة جدا',
                "problem": "النظام لا يفتح من الصباح ويؤثر على المراجعين في القسم.",
                "employee_suggestion": "",
                "resources": "",
                "constraints": "",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("&amp;", response.text)
        self.assertIn("&#34;", response.text)
        self.assertNotIn('مشكلة "عاجلة"', response.text)


if __name__ == "__main__":
    unittest.main()
