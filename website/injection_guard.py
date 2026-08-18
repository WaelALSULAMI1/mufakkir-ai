from __future__ import annotations

import re
from typing import Any

HTML_TAG_RE = re.compile(r"</?[a-zA-Z!?%][^>]{0,500}>", re.IGNORECASE)
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
CRLF_RE = re.compile(r"[\r\n]")
JS_URI_RE = re.compile(r"javascript\s*:", re.IGNORECASE)
SAFE_REDIRECT_RE = re.compile(r"^/result/[0-9a-f]{32}$")
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
MULTILINE_FIELDS = frozenset({"problem", "employee_suggestion", "resources", "constraints", "clarification_answer"})
FIELD_LIMITS = {
    "department": 100,
    "title": 180,
    "problem": 5000,
    "employee_suggestion": 5000,
    "resources": 2500,
    "constraints": 2500,
    "full_name": 80,
    "manager_note": 500,
    "clarification_question": 400,
    "clarification_answer": 1500,
    "clarification_why": 400,
}
SAFE_NEXT_PATHS = frozenset({"/", "/submit", "/manager", "/notifications", "/login", "/register", "/my-suggestions"})
SAFE_MANAGER_RESULT_RE = re.compile(r"^/manager/result/[0-9a-f]{32}$")


def sanitize_text(
    value: Any,
    *,
    allow_newlines: bool = False,
    max_length: int | None = None,
) -> str | None:
    """Treat user input as data: strip controls, markup, and header-break characters."""
    if value is None:
        return None
    text = str(value).replace("\x00", "")
    text = JS_URI_RE.sub("", text)
    if allow_newlines:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = CONTROL_RE.sub("", text)
        lines = [HTML_TAG_RE.sub("", line).strip() for line in text.split("\n")]
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    else:
        text = CRLF_RE.sub(" ", text)
        text = CONTROL_RE.sub("", text)
        text = HTML_TAG_RE.sub("", text)
        text = " ".join(text.split())
    if max_length is not None:
        text = text[:max_length]
    return text or None


def sanitize_field(field_name: str, value: Any) -> str | None:
    return sanitize_text(
        value,
        allow_newlines=field_name in MULTILINE_FIELDS,
        max_length=FIELD_LIMITS.get(field_name),
    )


def sanitize_analysis(value: Any, depth: int = 0) -> Any:
    if depth > 8:
        return None
    if isinstance(value, str):
        return sanitize_text(value, allow_newlines=True, max_length=5000) or ""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, list):
        return [sanitize_analysis(item, depth + 1) for item in value[:50]]
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in list(value.items())[:40]:
            cleaned[str(key)[:80]] = sanitize_analysis(item, depth + 1)
        return cleaned
    return None


def is_safe_app_redirect(url: str | None) -> bool:
    return bool(url) and bool(SAFE_REDIRECT_RE.fullmatch(url))


def is_safe_next_path(url: str | None) -> bool:
    if not url or len(url) > 120 or "\\" in url or ":" in url or "//" in url:
        return False
    if url in SAFE_NEXT_PATHS:
        return True
    return bool(SAFE_REDIRECT_RE.fullmatch(url) or SAFE_MANAGER_RESULT_RE.fullmatch(url))


def sanitize_email(value: str | None) -> str:
    text = sanitize_text(value, allow_newlines=False, max_length=120) or ""
    return text.lower() if EMAIL_RE.fullmatch(text) else ""


def wrap_untrusted_data(label: str, value: str) -> str:
    return f"{label}:\n<<<USER_DATA\n{value}\nUSER_DATA>>>"
