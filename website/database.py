from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from injection_guard import sanitize_analysis, sanitize_field
from path_safety import is_suggestion_id

try:
    from zoneinfo import ZoneInfo
    DISPLAY_TZ = ZoneInfo("Asia/Riyadh")
except Exception:
    DISPLAY_TZ = timezone(timedelta(hours=3))

LOCKOUT_LIMIT = 5
LOCKOUT_WINDOW_SECONDS = 15 * 60
IP_RE = re.compile(r"^[A-Za-z0-9.:-]{1,64}$")
PUBLIC_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
EMPLOYEE_CODE_PREFIX = "م-"
SUGGESTION_CODE_PREFIX = "ق-"
MONTHS_AR = (
    "",
    "يناير",
    "فبراير",
    "مارس",
    "أبريل",
    "مايو",
    "يونيو",
    "يوليو",
    "أغسطس",
    "سبتمبر",
    "أكتوبر",
    "نوفمبر",
    "ديسمبر",
)

BASE_DIR = Path(__file__).resolve().parent
_env_db = (os.getenv("JEDDAH_DB_PATH") or "").strip()
DB_PATH = Path(_env_db) if _env_db else BASE_DIR / "data" / "suggestions.db"


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA trusted_schema = OFF")
    conn.execute("PRAGMA cell_size_check = ON")
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if column not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def generate_public_code(prefix: str) -> str:
    body = "".join(secrets.choice(PUBLIC_CODE_ALPHABET) for _ in range(6))
    return f"{prefix}{body}"


def _allocate_public_code(conn: sqlite3.Connection, table: str, prefix: str) -> str:
    if table not in {"users", "suggestions"}:
        raise ValueError("جدول غير مسموح.")
    for _ in range(16):
        code = generate_public_code(prefix)
        exists = conn.execute(f"SELECT 1 FROM {table} WHERE public_code = ?", (code,)).fetchone()
        if not exists:
            return code
    raise RuntimeError("تعذر توليد رمز مرجعي.")


def _backfill_public_codes(conn: sqlite3.Connection, table: str, prefix: str) -> None:
    if table not in {"users", "suggestions"}:
        raise ValueError("جدول غير مسموح.")
    rows = conn.execute(
        f"SELECT id FROM {table} WHERE public_code IS NULL OR public_code = ''"
    ).fetchall()
    for row in rows:
        conn.execute(
            f"UPDATE {table} SET public_code = ? WHERE id = ?",
            (_allocate_public_code(conn, table, prefix), row["id"]),
        )


def init_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS suggestions (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                department TEXT NOT NULL,
                title TEXT NOT NULL,
                problem TEXT NOT NULL,
                employee_suggestion TEXT,
                resources TEXT,
                constraints TEXT,
                status TEXT NOT NULL,
                score INTEGER,
                analysis_json TEXT
            )
            """
        )
        _ensure_column(conn, "suggestions", "owner_user_id", "TEXT")
        _ensure_column(conn, "suggestions", "manager_decision", "TEXT")
        _ensure_column(conn, "suggestions", "manager_note", "TEXT")
        _ensure_column(conn, "suggestions", "decided_at", "TEXT")
        _ensure_column(conn, "suggestions", "public_code", "TEXT")
        _ensure_column(conn, "suggestions", "clarifications_json", "TEXT")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_suggestions_department_score "
            "ON suggestions(department, score DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_suggestions_owner "
            "ON suggestions(owner_user_id, created_at DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        _ensure_column(conn, "users", "public_code", "TEXT")
        _backfill_public_codes(conn, "users", EMPLOYEE_CODE_PREFIX)
        _backfill_public_codes(conn, "suggestions", SUGGESTION_CODE_PREFIX)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_public_code ON users(public_code)")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_suggestions_public_code ON suggestions(public_code)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                user_id TEXT NOT NULL,
                suggestion_id TEXT NOT NULL,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT,
                is_read INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_notifications_user "
            "ON notifications(user_id, created_at DESC)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_failures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_auth_failures_ip_time "
            "ON auth_failures(ip, created_at)"
        )


def save_suggestion(record: dict) -> None:
    if not is_suggestion_id(record["id"]):
        raise ValueError("معرف المقترح غير صالح.")
    analysis = record.get("analysis")
    analysis_json = None
    if isinstance(analysis, dict):
        analysis_json = json.dumps(sanitize_analysis(analysis), ensure_ascii=False)
    with _connect() as conn:
        public_code = record.get("public_code") or _allocate_public_code(conn, "suggestions", SUGGESTION_CODE_PREFIX)
        conn.execute(
            """
            INSERT INTO suggestions (
                id, created_at, department, title, problem,
                employee_suggestion, resources, constraints,
                status, score, analysis_json, owner_user_id, public_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["id"],
                record["created_at"],
                sanitize_field("department", record["department"]),
                sanitize_field("title", record["title"]),
                sanitize_field("problem", record["problem"]),
                sanitize_field("employee_suggestion", record.get("employee_suggestion")),
                sanitize_field("resources", record.get("resources")),
                sanitize_field("constraints", record.get("constraints")),
                record["status"],
                record.get("score"),
                analysis_json,
                record.get("owner_user_id"),
                public_code,
            ),
        )


def get_suggestion(suggestion_id: str) -> dict | None:
    if not is_suggestion_id(suggestion_id):
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM suggestions WHERE id = ?", (suggestion_id,)
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    raw_analysis = item.get("analysis_json")
    parsed = None
    if raw_analysis:
        try:
            parsed = json.loads(raw_analysis)
        except (json.JSONDecodeError, TypeError, ValueError):
            parsed = None
    item["analysis"] = humanize_analysis(sanitize_analysis(parsed)) if isinstance(parsed, dict) else None
    raw_clarifications = item.get("clarifications_json")
    parsed_clarifications = None
    if raw_clarifications:
        try:
            parsed_clarifications = json.loads(raw_clarifications)
        except (json.JSONDecodeError, TypeError, ValueError):
            parsed_clarifications = None
    if isinstance(parsed_clarifications, list):
        item["clarifications"] = sanitize_analysis(parsed_clarifications)
    else:
        item["clarifications"] = []
    owner = get_user_by_id(str(item["owner_user_id"])) if item.get("owner_user_id") else None
    item["owner_public_code"] = owner.get("public_code") if owner else None
    item["owner_full_name"] = owner.get("full_name") if owner else None
    item["display_title"] = proposal_headline(item)
    item["created_display"] = format_created_display(item.get("created_at") or "")
    return item


def save_clarifications(suggestion_id: str, items: list[dict]) -> bool:
    if not is_suggestion_id(suggestion_id):
        return False
    cleaned: list[dict] = []
    for item in items[:12]:
        question = sanitize_field("clarification_question", item.get("question"))
        if not question:
            continue
        cleaned.append(
            {
                "question": question,
                "why": sanitize_field("clarification_why", item.get("why")) or "",
                "answer": sanitize_field("clarification_answer", item.get("answer")) or "",
            }
        )
    with _connect() as conn:
        exists = conn.execute("SELECT 1 FROM suggestions WHERE id = ?", (suggestion_id,)).fetchone()
        if not exists:
            return False
        conn.execute(
            "UPDATE suggestions SET clarifications_json = ? WHERE id = ?",
            (json.dumps(cleaned, ensure_ascii=False), suggestion_id),
        )
    return True


_SIMILAR_STOP = frozenset(
    {
        "في", "من", "على", "إلى", "الى", "عن", "هذا", "هذه", "ذلك", "التي", "الذي",
        "مع", "أو", "او", "و", "لا", "ما", "أن", "ان", "إن", "كان", "يكون", "تم",
        "هناك", "بين", "بعد", "قبل", "غير", "كل", "بعض", "عند", "حتى", "قد",
    }
)


def _similar_tokens(text: str) -> set[str]:
    cleaned = re.sub(r"[^\w\u0600-\u06FF]+", " ", str(text or ""))
    return {token for token in cleaned.split() if len(token) >= 3 and token not in _SIMILAR_STOP}


def _short_text(text: str, limit: int = 90) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) > limit:
        return compact[: limit - 1] + "…"
    return compact


def _first_line(text: str) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    return raw.splitlines()[0].strip()


def _recommendation_decision(item: dict) -> str:
    analysis = item.get("analysis")
    if isinstance(analysis, dict):
        rec = analysis.get("recommendation")
        if isinstance(rec, dict):
            decision = str(rec.get("decision") or "").strip()
            if decision:
                return decision
    raw = item.get("analysis_json")
    if not raw:
        return ""
    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError, ValueError):
        return ""
    if not isinstance(payload, dict):
        return ""
    rec = payload.get("recommendation")
    if not isinstance(rec, dict):
        return ""
    return str(rec.get("decision") or "").strip()


_ALT_REF_RE = re.compile(r"(?:تجربة\s+)?البديل(?:\s+رقم)?\s*([1-4١-٤])")
_AR_DIGITS = str.maketrans("١٢٣٤", "1234")


def _alt_index(token: str) -> int:
    return int(str(token).translate(_AR_DIGITS))


def _plain_alt_name(alt: dict, index: int) -> str:
    name = str(alt.get("name") or "").strip().rstrip(".")
    if name and not _ALT_REF_RE.search(name):
        return name
    idea = str(alt.get("idea") or "").strip()
    if idea:
        return idea.split(".", 1)[0][:70].rstrip(" .")
    return name or f"الخيار {index}"


def _replace_alt_refs(text: str, names: dict[int, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        return names.get(_alt_index(match.group(1)), match.group(0))

    return _ALT_REF_RE.sub(repl, text)


def humanize_analysis(analysis: dict | None) -> dict | None:
    if not isinstance(analysis, dict):
        return analysis
    alternatives = analysis.get("alternatives")
    names: dict[int, str] = {}
    if isinstance(alternatives, list):
        for index, alt in enumerate(alternatives, start=1):
            if isinstance(alt, dict):
                names[index] = _plain_alt_name(alt, index)
                alt["name"] = names[index]

    def walk(value):
        if isinstance(value, str):
            return _replace_alt_refs(value, names) if names else value
        if isinstance(value, list):
            return [walk(item) for item in value]
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        return value

    return walk(analysis)


_PROBLEM_TITLE_RE = re.compile(
    r"مشكل|خطأ|خطا|تعطل|تخطف|يتاخر|لا تعمل|^الطابعه$|^الطابعة$",
    re.IGNORECASE,
)


def _looks_like_problem_title(title: str) -> bool:
    text = str(title or "").strip()
    if not text:
        return True
    return bool(_PROBLEM_TITLE_RE.search(text))


def _usable_proposal_line(text: str) -> str:
    line = _first_line(text)
    if not line:
        return ""
    if line in {"يُختبر", "يختبر"} or line.startswith("تجربة البديل"):
        return ""
    return line


def proposal_headline(item: dict) -> str:
    title = str(item.get("title") or "").strip()
    if title and not _looks_like_problem_title(title):
        return title
    suggestion_line = _usable_proposal_line(item.get("employee_suggestion") or "")
    if suggestion_line:
        return _short_text(suggestion_line, 90)
    decision = _usable_proposal_line(_recommendation_decision(item))
    if decision:
        return _short_text(decision, 90)
    return title


def similar_suggestions(suggestion_id: str, department: str, title: str, problem: str, limit: int = 3) -> list[dict]:
    source = _similar_tokens(f"{title} {problem}")
    if not source:
        return []
    limit = max(1, min(int(limit), 5))
    scored: list[tuple[int, dict]] = []
    for item in list_department_suggestions(department, limit=80):
        if item.get("id") == suggestion_id:
            continue
        other = _similar_tokens(f"{item.get('title') or ''} {item.get('problem') or ''}")
        overlap = len(source & other)
        if overlap >= 2:
            scored.append((overlap, item))
    scored.sort(key=lambda pair: (-pair[0], str(pair[1].get("created_at") or "")))
    return [item for _score, item in scored[:limit]]


def top_suggestions(department: str, limit: int = 5, allowed: list[str] | None = None) -> list[dict]:
    department = sanitize_field("department", department) or ""
    if allowed is not None and department not in allowed:
        return []
    if not department:
        return []
    limit = max(1, min(int(limit), 20))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, department, title, status, score, public_code, manager_decision,
                   problem, employee_suggestion, analysis_json
            FROM suggestions
            WHERE department = ? AND status = 'analyzed' AND score IS NOT NULL
            ORDER BY score DESC, created_at ASC
            LIMIT ?
            """,
            (department, limit),
        ).fetchall()
    return _annotate_review([dict(row) for row in rows])


def list_pending_review(department: str, limit: int = 80, allowed: list[str] | None = None) -> list[dict]:
    department = sanitize_field("department", department) or ""
    if allowed is not None and department not in allowed:
        return []
    if not department:
        return []
    limit = max(1, min(int(limit), 120))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, department, title, status, score, public_code, manager_decision,
                   problem, employee_suggestion, analysis_json
            FROM suggestions
            WHERE department = ?
              AND (manager_decision IS NULL OR manager_decision = '')
            ORDER BY CASE WHEN status = 'analyzed' THEN 0 ELSE 1 END, created_at ASC
            LIMIT ?
            """,
            (department, limit),
        ).fetchall()
    return _annotate_review([dict(row) for row in rows])


def department_counts() -> dict[str, int]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT department, COUNT(*) AS count FROM suggestions GROUP BY department"
        ).fetchall()
    return {row["department"]: row["count"] for row in rows}


def list_department_suggestions(department: str, limit: int = 200, allowed: list[str] | None = None) -> list[dict]:
    department = sanitize_field("department", department) or ""
    if allowed is not None and department not in allowed:
        return []
    if not department:
        return []
    limit = max(1, min(int(limit), 300))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, department, title, status, score, public_code, manager_decision,
                   problem, employee_suggestion, analysis_json
            FROM suggestions
            WHERE department = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (department, limit),
        ).fetchall()
    return _annotate_review([dict(row) for row in rows])


DECISION_KINDS = ("adopted", "rejected", "modified")
DECISION_LABELS = {
    "adopted": "اُعتمد",
    "rejected": "رُفض",
    "modified": "طُلب تعديله",
}
PENDING_REVIEW_LABEL = "يحتاج مراجعة المدير"


def suggestion_review_label(item: dict) -> str:
    decision = item.get("manager_decision")
    if decision in DECISION_LABELS:
        return DECISION_LABELS[decision]
    return PENDING_REVIEW_LABEL


def format_created_display(created: str) -> str:
    raw = str(created or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(DISPLAY_TZ)
        return f"{dt.day} {MONTHS_AR[dt.month]} {dt.year} · {dt:%H:%M}"
    except (ValueError, TypeError, IndexError):
        return raw.replace("T", " ")[:16]


def _annotate_review(items: list[dict]) -> list[dict]:
    for item in items:
        item["review_label"] = suggestion_review_label(item)
        item["review_kind"] = item.get("manager_decision") or "pending"
        item["created_display"] = format_created_display(item.get("created_at") or "")
        problem = str(item.get("problem") or "").strip()
        item["problem_preview"] = (problem[:90] + "…") if len(problem) > 90 else problem
        item["display_title"] = proposal_headline(item)
        item["analysis_ready"] = item.get("status") == "analyzed"
        item.pop("analysis_json", None)
    return items


def list_user_suggestions(user_id: str, limit: int = 50) -> list[dict]:
    if not is_suggestion_id(user_id):
        return []
    limit = max(1, min(int(limit), 80))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, department, title, status,
                   manager_decision, manager_note, decided_at, public_code,
                   employee_suggestion, analysis_json
            FROM suggestions
            WHERE owner_user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return _annotate_review([dict(row) for row in rows])


def create_user(record: dict) -> None:
    with _connect() as conn:
        public_code = record.get("public_code") or _allocate_public_code(conn, "users", EMPLOYEE_CODE_PREFIX)
        conn.execute(
            """
            INSERT INTO users (id, created_at, full_name, email, password_hash, role, public_code)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["id"],
                record["created_at"],
                sanitize_field("full_name", record["full_name"]),
                record["email"],
                record["password_hash"],
                "employee",
                public_code,
            ),
        )


def get_user_by_email(email: str) -> dict | None:
    if not email:
        return None
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    return dict(row) if row else None


def get_user_by_id(user_id: str) -> dict | None:
    if not is_suggestion_id(user_id):
        return None
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def set_manager_decision(suggestion_id: str, decision: str, note: str | None) -> dict | None:
    if not is_suggestion_id(suggestion_id) or decision not in DECISION_KINDS:
        return None
    suggestion = get_suggestion(suggestion_id)
    if not suggestion:
        return None
    decided_at = datetime.now(timezone.utc).isoformat()
    clean_note = sanitize_field("manager_note", note)
    with _connect() as conn:
        conn.execute(
            """
            UPDATE suggestions
            SET manager_decision = ?, manager_note = ?, decided_at = ?
            WHERE id = ?
            """,
            (decision, clean_note, decided_at, suggestion_id),
        )
    suggestion["manager_decision"] = decision
    suggestion["manager_note"] = clean_note
    suggestion["decided_at"] = decided_at
    return suggestion


def create_notification(record: dict) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO notifications (
                id, created_at, user_id, suggestion_id, kind, title, body, is_read
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                record["id"],
                record["created_at"],
                record["user_id"],
                record["suggestion_id"],
                record["kind"],
                sanitize_field("title", record["title"]) or "تحديث على مقترحك",
                sanitize_field("manager_note", record.get("body")),
            ),
        )


def list_notifications(user_id: str, limit: int = 20) -> list[dict]:
    if not is_suggestion_id(user_id):
        return []
    limit = max(1, min(int(limit), 50))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM notifications
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def unread_notification_count(user_id: str) -> int:
    if not is_suggestion_id(user_id):
        return 0
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM notifications WHERE user_id = ? AND is_read = 0",
            (user_id,),
        ).fetchone()
    return int(row["count"] if row else 0)


def mark_notifications_read(user_id: str) -> None:
    if not is_suggestion_id(user_id):
        return
    with _connect() as conn:
        conn.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (user_id,))


def _safe_ip(ip: str) -> str:
    return ip if IP_RE.fullmatch(ip or "") else "unknown"


def record_auth_failure(ip: str) -> int:
    safe_ip = _safe_ip(ip)
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(seconds=LOCKOUT_WINDOW_SECONDS)).isoformat()
    with _connect() as conn:
        conn.execute("DELETE FROM auth_failures WHERE created_at < ?", (cutoff,))
        conn.execute(
            "INSERT INTO auth_failures (ip, created_at) VALUES (?, ?)",
            (safe_ip, now.isoformat()),
        )
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM auth_failures WHERE ip = ? AND created_at >= ?",
            (safe_ip, cutoff),
        ).fetchone()["count"]
    return int(count)


def clear_auth_failures(ip: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM auth_failures WHERE ip = ?", (_safe_ip(ip),))


def is_ip_locked(ip: str) -> bool:
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=LOCKOUT_WINDOW_SECONDS)).isoformat()
    with _connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM auth_failures WHERE ip = ? AND created_at >= ?",
            (_safe_ip(ip), cutoff),
        ).fetchone()["count"]
    return int(count) >= LOCKOUT_LIMIT
