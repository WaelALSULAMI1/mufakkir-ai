from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "unit-test-secret-key-not-for-production")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("MODEL_MODE", "disabled")

import _isolate_db  # noqa: F401

from path_safety import (
    is_suggestion_id,
    load_static_allowlist,
    request_path_is_safe,
    safe_join,
)


class RequestPathSafetyTests(unittest.TestCase):
    def test_normal_pages_are_allowed(self):
        for path in (
            "/",
            "/submit",
            "/about",
            "/static/style.css",
            "/static/img/header_logo.png",
            "/static/fonts/ibm-plex-sans-arabic-400.woff2",
        ):
            self.assertTrue(request_path_is_safe(path), path)

    def test_parent_and_encoded_paths_are_rejected(self):
        for path in (
            "/static/../app.py",
            "/static/..\\app.py",
            "/static/%2e%2e/app.py",
            "/static/%2E%2E/%2e%2e/app.py",
            "/static/img/%2e%2e/%2e%2e/app.py",
            "/static/C:/Windows/win.ini",
            "/static//server/share/secret",
            "/static/style.css%00.png",
        ):
            self.assertFalse(request_path_is_safe(path), path)

    def test_empty_or_oversized_paths_are_rejected(self):
        self.assertFalse(request_path_is_safe(""))
        self.assertFalse(request_path_is_safe("/" + ("a" * 300)))


class SuggestionIdTests(unittest.TestCase):
    def test_accepts_hex_id(self):
        self.assertTrue(is_suggestion_id("a" * 32))
        self.assertTrue(is_suggestion_id("A" * 32))

    def test_rejects_non_hex_or_wrong_length(self):
        self.assertFalse(is_suggestion_id("../" + ("a" * 29)))
        self.assertFalse(is_suggestion_id("not-a-valid-id"))
        self.assertFalse(is_suggestion_id("a" * 31))


class SafeJoinTests(unittest.TestCase):
    def test_stays_inside_base_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowed = root / "style.css"
            allowed.write_text("body{}", encoding="utf-8")
            self.assertEqual(safe_join(root, "style.css"), allowed.resolve())
            self.assertIsNone(safe_join(root, "../secret.txt"))
            self.assertIsNone(safe_join(root, "..\\secret.txt"))
            self.assertIsNone(safe_join(root, "/style.css"))

    def test_allowlist_contains_only_safe_relative_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.js").write_text("ok", encoding="utf-8")
            images = root / "img"
            images.mkdir()
            (images / "logo.png").write_bytes(b"x")
            (root / ".hidden.css").write_text("no", encoding="utf-8")
            allowed = load_static_allowlist(root)
            self.assertEqual(allowed, frozenset({"app.js", "img/logo.png"}))


class AppStaticGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from app import app

        cls.client = TestClient(app, raise_server_exceptions=False)

    def test_known_static_file_is_served(self):
        response = self.client.get("/static/style.css")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/css", response.headers.get("content-type", ""))

    def test_arabic_font_is_served(self):
        response = self.client.get("/static/fonts/ibm-plex-sans-arabic-400.woff2")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.content), 1000)

    def test_hero_image_is_served(self):
        response = self.client.get("/static/img/hero_ai.png")
        self.assertEqual(response.status_code, 200)
        self.assertIn("image/png", response.headers.get("content-type", ""))
        self.assertGreater(len(response.content), 1000)

    def test_unknown_static_file_is_not_served(self):
        response = self.client.get("/static/missing.css")
        self.assertIn(response.status_code, {400, 404})

    def test_source_file_is_not_reachable_as_static(self):
        response = self.client.get("/static/app.py")
        self.assertIn(response.status_code, {400, 404})
        self.assertNotIn("from fastapi import FastAPI", response.text)


if __name__ == "__main__":
    unittest.main()
