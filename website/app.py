from __future__ import annotations

import asyncio
import json
import os
import secrets
import sqlite3
import time
import traceback
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import Field, ValidationError
from starlette.middleware.sessions import SessionMiddleware

load_dotenv()

from audit import write_audit
from database import (
    DECISION_KINDS,
    DECISION_LABELS,
    LOCKOUT_LIMIT,
    clear_auth_failures,
    create_notification,
    create_user,
    department_counts,
    get_suggestion,
    get_user_by_email,
    get_user_by_id,
    init_db,
    is_ip_locked,
    list_department_suggestions,
    list_notifications,
    list_pending_review,
    list_user_suggestions,
    mark_notifications_read,
    record_auth_failure,
    save_suggestion,
    set_manager_decision,
    similar_suggestions,
    top_suggestions,
    unread_notification_count,
)
from model_schema import SuggestionInput
from model_service import MODEL_MODE, ModelUnavailable, analyze_and_score, check_model_ready
from injection_guard import is_safe_app_redirect, is_safe_next_path, sanitize_analysis, sanitize_email, sanitize_field
from password_safety import constant_time_equals, hash_password, load_password_hash, verify_password
from session_security import SESSION_ABSOLUTE_SECONDS, enforce_session, stamp_new_session
from path_safety import (
    AllowlistStaticFiles,
    is_suggestion_id,
    load_static_allowlist,
    logger as security_logger,
    request_path_is_safe,
)

BASE_DIR = Path(__file__).resolve().parent
APP_ENV = os.getenv("APP_ENV", "development").lower()
SECRET_KEY = os.getenv("SECRET_KEY", "")
MANAGER_EMAIL = sanitize_email(os.getenv("MANAGER_EMAIL", "admin@jeddah.local"))
MANAGER_PASSWORD_HASH = load_password_hash()

if not SECRET_KEY or SECRET_KEY == "CHANGE_ME_RANDOM_SECRET":
    raise RuntimeError("SECRET_KEY غير مضبوط. شغل setup_windows.bat أو عدّل ملف .env")
if not MANAGER_EMAIL:
    raise RuntimeError("MANAGER_EMAIL غير صالح. عدّل ملف .env")
if os.getenv("MANAGER_PASSWORD"):
    if APP_ENV == "production":
        raise RuntimeError("لا تترك MANAGER_PASSWORD نصًا واضحًا في الإنتاج. استخدم الهاش فقط.")
    security_logger.warning("MANAGER_PASSWORD ما زالت نصًا واضحًا. شغّل python hash_manager_password.py --migrate")

DEPARTMENTS = [
    "تقنية المعلومات",
    "العمليات",
    "الخدمات البلدية",
    "المشاريع",
    "الموارد البشرية",
    "خدمة المستفيدين",
    "المالية",
    "التخطيط والتطوير",
    "اخرى",
]


class AnalyzeApiRequest(SuggestionInput):
    csrf_token: str = Field(min_length=8)

app = FastAPI(
    title="جِدّة - منصة الابتكار المؤسسي",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    debug=False,
)
STATIC_DIR = BASE_DIR / "static"
STATIC_ALLOWLIST = load_static_allowlist(STATIC_DIR)
app.mount("/static", AllowlistStaticFiles(STATIC_DIR, STATIC_ALLOWLIST), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.autoescape = True
templates.env.auto_reload = APP_ENV != "production"

RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


MIN_PASSWORD_LENGTH = 8
MANAGER_NAME = "مدير المنصة"
MANAGER_ONLY_MESSAGE = "لا يمكنك دخول لوحة المدير. هذه الصفحة مخصصة لحساب المدير فقط."
DUMMY_PASSWORD_HASH = hash_password("not-a-real-account-password")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _session_email(request: Request) -> str:
    return sanitize_email(str(request.session.get("user_email") or ""))


def _is_manager_session(request: Request) -> bool:
    if request.session.get("manager_authenticated") is not True:
        return False
    if request.session.get("role") != "manager":
        return False
    if request.session.get("user_id"):
        return False
    email = _session_email(request)
    return bool(email) and constant_time_equals(email, MANAGER_EMAIL)


def _is_employee_session(request: Request) -> bool:
    if request.session.get("manager_authenticated") is True:
        return False
    if request.session.get("role") != "employee":
        return False
    return is_suggestion_id(str(request.session.get("user_id") or ""))


def _current_role(request: Request) -> str | None:
    if _is_manager_session(request):
        return "manager"
    if _is_employee_session(request):
        return "employee"
    return None


def _current_user(request: Request) -> dict | None:
    role = _current_role(request)
    if role == "manager":
        return {"id": None, "role": "manager", "email": MANAGER_EMAIL, "full_name": MANAGER_NAME}
    if role == "employee":
        user = get_user_by_id(str(request.session.get("user_id")))
        if not user:
            return None
        session_email = _session_email(request)
        if not session_email or not constant_time_equals(session_email, user["email"]):
            return None
        return {"id": user["id"], "role": "employee", "email": user["email"], "full_name": user["full_name"], "public_code": user.get("public_code")}
    return None


def _start_session(request: Request, *, role: str, user_id: str | None, email: str) -> None:
    request.session.clear()
    stamp_new_session(request, SECRET_KEY)
    request.session["csrf"] = secrets.token_urlsafe(32)
    request.session["role"] = role
    request.session["user_email"] = email
    if role == "manager":
        request.session["manager_authenticated"] = True
    else:
        request.session["user_id"] = user_id
        request.session["manager_authenticated"] = False


def _rate_limit(request: Request, name: str, limit: int, window_seconds: int) -> None:
    now = time.monotonic()
    key = f"{name}:{_client_ip(request)}"
    bucket = RATE_BUCKETS[key]
    while bucket and bucket[0] <= now - window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="عدد المحاولات كبير. حاول بعد قليل.")
    bucket.append(now)


def _csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def _verify_csrf(request: Request, token: str) -> None:
    expected = str(request.session.get("csrf") or "")
    if not expected or not constant_time_equals(str(token or ""), expected):
        raise HTTPException(status_code=403, detail="رمز الحماية غير صالح. حدّث الصفحة وحاول مرة أخرى.")


def _flash_error(request: Request, message: str) -> None:
    request.session["flash_error"] = message


def _flash_success(request: Request, message: str) -> None:
    request.session["flash_success"] = message


def _mark_submit_success(request: Request, suggestion_id: str) -> None:
    request.session["submit_success_id"] = suggestion_id


def _manager_required(request: Request) -> None:
    role = _current_role(request)
    if role == "manager":
        return
    if role == "employee":
        _flash_error(request, MANAGER_ONLY_MESSAGE)
        raise HTTPException(status_code=403, detail=MANAGER_ONLY_MESSAGE)
    raise HTTPException(status_code=401, detail="يلزم تسجيل دخول المدير.")


def _employee_required(request: Request) -> dict:
    user = _current_user(request)
    if not user or user["role"] != "employee":
        raise HTTPException(status_code=401, detail="يلزم تسجيل دخول الموظف.")
    return user


EMPLOYEE_AREA_COPY = {
    "submit": (
        "تقديم المقترح من حساب الموظف",
        "أنت داخل بحساب المدير. هذا الحساب للمراجعة واتخاذ القرار: اعتماد أو رفض أو طلب تعديل. كتابة مقترح جديد تتم من حساب موظف.",
    ),
    "mine": (
        "اقتراحاتي للموظف",
        "سجل المقترحات الشخصية يظهر لصاحب الحساب الذي قدّمها. حساب المدير يستعرض المقترحات من لوحة المراجعة.",
    ),
    "notifications": (
        "الإشعارات للموظف",
        "إشعارات القرار تصل لصاحب المقترح. حساب المدير يتابع الحالات من لوحة المراجعة.",
    ),
}


def _manager_on_employee_page(request: Request, intent: str):
    title, body = EMPLOYEE_AREA_COPY[intent]
    return templates.TemplateResponse(
        request=request,
        name="role_notice.html",
        context=_context(request, page=intent, notice_title=title, notice_body=body),
    )


def _grant_result_access(request: Request, suggestion_id: str) -> None:
    owned = [item for item in request.session.get("owned_results") or [] if is_suggestion_id(str(item))]
    if suggestion_id not in owned:
        owned.append(suggestion_id)
    request.session["owned_results"] = owned[-20:]


def _can_view_result(request: Request, suggestion_id: str, suggestion: dict | None = None) -> bool:
    if _current_role(request) == "manager":
        return True
    record = suggestion or get_suggestion(suggestion_id)
    if not record:
        return False
    user = _current_user(request)
    owner_id = str(record.get("owner_user_id") or "")
    if owner_id:
        return bool(user and user["id"] == owner_id)
    if not user:
        return False
    owned = request.session.get("owned_results") or []
    return suggestion_id in owned


def _employee_safe_suggestion(suggestion: dict) -> dict:
    item = dict(suggestion)
    item.pop("score", None)
    analysis = item.get("analysis")
    if isinstance(analysis, dict):
        cleaned = dict(analysis)
        cleaned.pop("score", None)
        cleaned.pop("score_breakdown", None)
        cleaned.pop("score_source", None)
        item["analysis"] = cleaned
    return item


def _ui_theme(request: Request) -> str:
    raw = (request.cookies.get("mufakkir_theme") or "").strip().lower()
    return "dark" if raw == "dark" else "light"


def _context(request: Request, **kwargs):
    user = _current_user(request)
    unread = unread_notification_count(user["id"]) if user and user["role"] == "employee" else 0
    preview = list_notifications(user["id"], 5) if user and user["role"] == "employee" else []
    return {
        "request": request,
        "csrf_token": _csrf_token(request),
        "model_mode": MODEL_MODE,
        "departments": DEPARTMENTS,
        "current_user": user,
        "unread_count": unread,
        "notifications_preview": preview,
        "decision_labels": DECISION_LABELS,
        "pending_review_label": "يحتاج مراجعة المدير",
        "alt_kind_labels": {
            "فوري": "حل سريع اليوم",
            "تشخيص": "افحص السبب أولًا",
            "اقتراح الموظف": "حل الموظف",
            "تنظيمي": "تحسين أسلوب العمل",
        },
        "verdict_labels": {
            "يُختبر": "يُجرَّب أولًا",
            "يُعتمد": "مناسب بعد التجربة",
            "يُعدل": "يحتاج تعديل",
            "يُرفض": "غير مناسب بهذا الشكل",
            "لا يوجد اقتراح": "الموظف لم يكتب حلًا",
        },
        "ui_theme": _ui_theme(request),
        "flash_error": request.session.pop("flash_error", None),
        "flash_success": request.session.pop("flash_success", None),
        **kwargs,
    }


def _analyze_payload(result: dict) -> dict:
    return {
        "ok": result["status"] == "analyzed",
        "status": result["status"],
        "error": result["error"],
        "redirect": result["redirect"],
    }


async def _analyze_and_store(
    data: SuggestionInput,
    owner_user_id: str | None = None,
    suggestion_id: str | None = None,
    on_stage=None,
) -> dict:
    suggestion_id = suggestion_id or uuid.uuid4().hex
    analysis = None
    score = None
    status = "pending_model"
    model_error = None
    try:
        analysis_obj, score_obj = await analyze_and_score(data, on_stage=on_stage)
        if analysis_obj is not None and score_obj is not None:
            analysis = sanitize_analysis(analysis_obj.model_dump())
            analysis["score_breakdown"] = score_obj.model_dump()
            analysis["score_source"] = "computed"
            score = score_obj.total
            status = "analyzed"
    except (ModelUnavailable, ValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
        security_logger.warning("model analysis failed: %s", exc)
        model_error = "تعذر تحليل المقترح حاليًا. تأكد أن المودل جاهز ثم أعد المحاولة."
        status = "model_error"
    except Exception:
        security_logger.exception("unexpected model analysis failure")
        model_error = "تعذر تحليل المقترح حاليًا. تأكد أن المودل جاهز ثم أعد المحاولة."
        status = "model_error"

    save_suggestion(
        {
            "id": suggestion_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "department": data.department,
            "title": data.title,
            "problem": data.problem,
            "employee_suggestion": data.employee_suggestion,
            "resources": data.resources,
            "constraints": data.constraints,
            "status": status,
            "score": score,
            "analysis": analysis,
            "owner_user_id": owner_user_id,
        }
    )
    redirect = f"/result/{suggestion_id}"
    if not is_safe_app_redirect(redirect):
        raise HTTPException(status_code=400, detail="طلب غير صالح.")
    return {
        "id": suggestion_id,
        "status": status,
        "score": score,
        "analysis": analysis,
        "error": model_error,
        "redirect": redirect,
    }


@app.middleware("http")
async def security_headers(request: Request, call_next):
    if not request_path_is_safe(request.url.path):
        security_logger.warning("blocked unsafe request path from %s", _client_ip(request))
        write_audit("path_blocked", _client_ip(request), "denied")
        response = templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "request": request,
                "csrf_token": "",
                "model_mode": MODEL_MODE,
                "departments": DEPARTMENTS,
                "page": "",
                "code": 400,
                "message": "طلب غير صالح.",
                "current_user": None,
                "unread_count": 0,
                "notifications_preview": [],
                "decision_labels": {},
                "ui_theme": _ui_theme(request),
            },
            status_code=400,
        )
    else:
        rejected = enforce_session(request, SECRET_KEY)
        if rejected == "fingerprint":
            write_audit("session_rejected", _client_ip(request), "denied")
        response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; object-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
    )
    if APP_ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/static/"):
        if APP_ENV != "production":
            response.headers["Cache-Control"] = "no-store"
    else:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
    return response


app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="jeddah_session",
    max_age=SESSION_ABSOLUTE_SECONDS,
    same_site="lax",
    https_only=APP_ENV == "production",
)
if APP_ENV == "production":
    from starlette.middleware.trustedhost import TrustedHostMiddleware

    allowed_hosts = [item.strip() for item in os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if item.strip()]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context=_context(request, page="home"),
    )


@app.get("/submit", response_class=HTMLResponse)
def submit_page(request: Request):
    if _current_role(request) == "manager":
        return _manager_on_employee_page(request, "submit")
    _employee_required(request)
    return templates.TemplateResponse(request=request, name="submit.html", context=_context(request, page="submit", errors=[], values={}))


@app.post("/submit")
async def submit_suggestion(
    request: Request,
    csrf_token: str = Form(...),
    department: str = Form(...),
    title: str = Form(...),
    problem: str = Form(...),
    employee_suggestion: str = Form(""),
    resources: str = Form(""),
    constraints: str = Form(""),
):
    _rate_limit(request, "submit", limit=8, window_seconds=60 * 10)
    _verify_csrf(request, csrf_token)
    if _current_role(request) == "manager":
        return _manager_on_employee_page(request, "submit")
    user = _employee_required(request)

    values = {
        "department": department,
        "title": title,
        "problem": problem,
        "employee_suggestion": employee_suggestion,
        "resources": resources,
        "constraints": constraints,
    }
    if department not in DEPARTMENTS:
        return templates.TemplateResponse(
            request=request,
            name="submit.html",
            context=_context(request, page="submit", errors=["اختار القسم المختص"], values=values),
            status_code=400,
        )
    try:
        data = SuggestionInput(**values)
    except ValidationError as exc:
        errors = ["تأكد من تعبئة عنوان المقترح ووصف الوضع بشكل واضح وعدم تجاوز الحد المسموح للنص."]
        if exc.errors():
            errors.append("بعض الحقول غير مكتملة أو غير صالحة.")
        return templates.TemplateResponse(
            request=request,
            name="submit.html",
            context=_context(request, page="submit", errors=errors, values=values),
            status_code=400,
        )

    result = await _analyze_and_store(data, owner_user_id=user["id"])
    _grant_result_access(request, result["id"])
    _mark_submit_success(request, result["id"])
    request.session["last_model_error"] = result["error"]
    return RedirectResponse(url=result["redirect"], status_code=303)


@app.get("/api/health")
async def api_health():
    ready, _detail = await check_model_ready()
    return JSONResponse(
        {
            "ok": ready,
            "detail": "مُفكر جاهز يفكر معك." if ready else "مُفكر غير جاهز حاليًا.",
        },
        status_code=200 if ready else 503,
    )


@app.post("/api/analyze")
async def api_analyze(request: Request, body: AnalyzeApiRequest):
    _rate_limit(request, "submit", limit=8, window_seconds=60 * 10)
    _verify_csrf(request, body.csrf_token)
    if _current_role(request) == "manager":
        return JSONResponse(
            {"ok": False, "error": "تقديم المقترح من حساب الموظف. حساب المدير للمراجعة."},
            status_code=403,
        )
    user = _employee_required(request)
    if body.department not in DEPARTMENTS:
        return JSONResponse({"ok": False, "errors": ["اختر قسمًا من القائمة."]}, status_code=400)
    data = SuggestionInput(
        department=body.department,
        title=body.title,
        problem=body.problem,
        employee_suggestion=body.employee_suggestion,
        resources=body.resources,
        constraints=body.constraints,
    )
    accept = (request.headers.get("accept") or "").lower()
    wants_stream = "application/x-ndjson" in accept
    if not wants_stream:
        result = await _analyze_and_store(data, owner_user_id=user["id"])
        _grant_result_access(request, result["id"])
        _mark_submit_success(request, result["id"])
        request.session["last_model_error"] = result["error"]
        return JSONResponse(
            _analyze_payload(result),
            status_code=200 if result["status"] == "analyzed" else 502,
        )

    suggestion_id = uuid.uuid4().hex
    _grant_result_access(request, suggestion_id)
    _mark_submit_success(request, suggestion_id)
    queue: asyncio.Queue = asyncio.Queue()

    async def on_stage(name: str) -> None:
        await queue.put({"stage": name})

    async def work() -> None:
        try:
            result = await _analyze_and_store(
                data,
                owner_user_id=user["id"],
                suggestion_id=suggestion_id,
                on_stage=on_stage,
            )
            try:
                request.session["last_model_error"] = result["error"]
            except Exception:
                security_logger.exception("could not store last_model_error")
            await queue.put(_analyze_payload(result))
        except Exception:
            security_logger.exception("analyze stream failed")
            await queue.put({"ok": False, "error": "تعذر تحليل المقترح حاليًا. أعد المحاولة بعد قليل."})
        finally:
            await queue.put(None)

    async def stream():
        task = asyncio.create_task(work())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield json.dumps(item, ensure_ascii=False) + "\n"
        finally:
            await task

    return StreamingResponse(stream(), media_type="application/x-ndjson; charset=utf-8")


@app.get("/result/{suggestion_id}", response_class=HTMLResponse)
def result_page(request: Request, suggestion_id: str):
    if not is_suggestion_id(suggestion_id):
        raise HTTPException(status_code=404)
    suggestion = get_suggestion(suggestion_id)
    if not suggestion or not _can_view_result(request, suggestion_id, suggestion):
        write_audit("result_denied", _client_ip(request), "denied")
        raise HTTPException(status_code=404)
    model_error = request.session.pop("last_model_error", None)
    just_submitted = request.session.pop("submit_success_id", None) == suggestion_id
    visible = suggestion if _current_role(request) == "manager" else _employee_safe_suggestion(suggestion)
    return templates.TemplateResponse(
        request=request,
        name="result.html",
        context=_context(
            request,
            page="result",
            suggestion=visible,
            model_error=model_error,
            manager_view=False,
            just_submitted=just_submitted,
            similar_items=[],
        ),
    )


@app.get("/guide", response_class=HTMLResponse)
def guide(request: Request):
    return templates.TemplateResponse(request=request, name="guide.html", context=_context(request, page="guide"))


@app.get("/about", response_class=HTMLResponse)
def about(request: Request):
    return templates.TemplateResponse(request=request, name="about.html", context=_context(request, page="about"))


@app.get("/privacy", response_class=HTMLResponse)
def privacy(request: Request):
    return templates.TemplateResponse(request=request, name="privacy.html", context=_context(request, page="privacy"))


@app.get("/terms", response_class=HTMLResponse)
def terms(request: Request):
    return templates.TemplateResponse(request=request, name="terms.html", context=_context(request, page="terms"))


def _safe_next(value: str | None, fallback: str) -> str:
    return value if is_safe_next_path(value) else fallback


def _auth_failure_response(
    request: Request,
    template: str,
    page: str,
    role: str,
    next_path: str,
    locked: bool,
    values: dict | None = None,
):
    message = "تم إيقاف المحاولات مؤقتًا. حاول بعد قليل." if locked else "بيانات الدخول غير صحيحة."
    status = 429 if locked else 401
    field_errors = {} if locked else {"email": message, "password": message}
    return templates.TemplateResponse(
        request=request,
        name=template,
        context=_context(
            request,
            page=page,
            error=message if locked else None,
            field_errors=field_errors,
            selected_role=role,
            next_path=next_path,
            values=values or {},
        ),
        status_code=status,
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, role: str = "employee", next: str = ""):
    current = _current_role(request)
    if current == "manager":
        return RedirectResponse("/manager", status_code=303)
    if current == "employee":
        wants_manager = role == "manager" or str(next).startswith("/manager")
        if wants_manager:
            _flash_error(request, MANAGER_ONLY_MESSAGE)
            return RedirectResponse("/", status_code=303)
        return RedirectResponse(_safe_next(next, "/submit"), status_code=303)
    selected = "manager" if role == "manager" else "employee"
    next_path = _safe_next(next, "/manager" if selected == "manager" else "/submit")
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context=_context(
            request,
            page="login",
            error=None,
            field_errors={},
            selected_role=selected,
            next_path=next_path,
            values={},
        ),
    )


@app.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    csrf_token: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form("employee"),
    next: str = Form(""),
):
    _rate_limit(request, "login", limit=8, window_seconds=60 * 10)
    _verify_csrf(request, csrf_token)
    selected = "manager" if role == "manager" else "employee"
    next_path = _safe_next(next, "/manager" if selected == "manager" else "/submit")
    client_ip = _client_ip(request)
    if is_ip_locked(client_ip):
        write_audit("login_lockout", client_ip, "denied")
        return _auth_failure_response(request, "login.html", "login", selected, next_path, True)

    email = sanitize_email(email)
    if selected == "manager":
        email_ok = constant_time_equals(email, MANAGER_EMAIL)
        pass_ok = verify_password(password, MANAGER_PASSWORD_HASH)
        if not (email_ok and pass_ok):
            failures = record_auth_failure(client_ip)
            write_audit("login_failure", client_ip, "denied")
            return _auth_failure_response(
                request,
                "login.html",
                "login",
                selected,
                next_path,
                failures >= LOCKOUT_LIMIT,
                values={"email": email},
            )
        clear_auth_failures(client_ip)
        write_audit("login_success", client_ip, "ok")
        _start_session(request, role="manager", user_id=None, email=MANAGER_EMAIL)
        return RedirectResponse("/manager", status_code=303)

    user = get_user_by_email(email) if email else None
    stored_hash = user["password_hash"] if user and user.get("role") == "employee" else DUMMY_PASSWORD_HASH
    pass_ok = verify_password(password, stored_hash)
    if not user or user.get("role") != "employee" or not pass_ok:
        failures = record_auth_failure(client_ip)
        write_audit("login_failure", client_ip, "denied")
        return _auth_failure_response(
            request,
            "login.html",
            "login",
            selected,
            next_path,
            failures >= LOCKOUT_LIMIT,
            values={"email": email},
        )
    clear_auth_failures(client_ip)
    write_audit("login_success", client_ip, "ok")
    _start_session(request, role="employee", user_id=user["id"], email=user["email"])
    return RedirectResponse(next_path, status_code=303)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    if _current_role(request) == "employee":
        return RedirectResponse("/submit", status_code=303)
    if _current_role(request) == "manager":
        return RedirectResponse("/manager", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context=_context(request, page="login", error=None, field_errors={}, values={}),
    )


@app.post("/register", response_class=HTMLResponse)
def register(
    request: Request,
    csrf_token: str = Form(...),
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    _rate_limit(request, "register", limit=6, window_seconds=60 * 10)
    _verify_csrf(request, csrf_token)
    values = {"full_name": full_name, "email": email}
    name = sanitize_field("full_name", full_name)
    clean_email = sanitize_email(email)
    if not name:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context=_context(
                request,
                page="login",
                error=None,
                field_errors={"full_name": "اكتب الاسم بشكل واضح."},
                values=values,
            ),
            status_code=400,
        )
    if not clean_email:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context=_context(
                request,
                page="login",
                error=None,
                field_errors={"email": "البريد الإلكتروني غير صالح."},
                values=values,
            ),
            status_code=400,
        )
    if constant_time_equals(clean_email, MANAGER_EMAIL):
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context=_context(
                request,
                page="login",
                error=None,
                field_errors={"email": "هذا البريد مخصص لحساب المدير الحالي."},
                values=values,
            ),
            status_code=400,
        )
    if not password or len(password) < MIN_PASSWORD_LENGTH or len(password) > 256:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context=_context(
                request,
                page="login",
                error=None,
                field_errors={"password": "كلمة المرور يجب أن تكون 8 أحرف على الأقل."},
                values=values,
            ),
            status_code=400,
        )
    if get_user_by_email(clean_email):
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context=_context(
                request,
                page="login",
                error=None,
                field_errors={"email": "يوجد حساب موظف بهذا البريد. سجّل الدخول."},
                values=values,
            ),
            status_code=400,
        )
    user_id = uuid.uuid4().hex
    try:
        create_user(
            {
                "id": user_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "full_name": name,
                "email": clean_email,
                "password_hash": hash_password(password),
                "role": "employee",
            }
        )
    except sqlite3.IntegrityError:
        return templates.TemplateResponse(
            request=request,
            name="register.html",
            context=_context(
                request,
                page="login",
                error=None,
                field_errors={"email": "يوجد حساب موظف بهذا البريد. سجّل الدخول."},
                values=values,
            ),
            status_code=400,
        )
    _start_session(request, role="employee", user_id=user_id, email=clean_email)
    return RedirectResponse("/submit", status_code=303)


@app.get("/manager/login", response_class=HTMLResponse)
def manager_login_page(request: Request):
    return RedirectResponse("/login?role=manager&next=/manager", status_code=303)


@app.post("/manager/login", response_class=HTMLResponse)
def manager_login(
    request: Request,
    csrf_token: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    return login(request, csrf_token=csrf_token, email=email, password=password, role="manager", next="/manager")


@app.post("/logout")
@app.post("/manager/logout")
def logout(request: Request, csrf_token: str = Form(...)):
    _verify_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/", status_code=303)


@app.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request):
    if _current_role(request) == "manager":
        return _manager_on_employee_page(request, "notifications")
    user = _employee_required(request)
    items = list_notifications(user["id"], 30)
    mark_notifications_read(user["id"])
    return templates.TemplateResponse(
        request=request,
        name="notifications.html",
        context=_context(request, page="notifications", notifications=items, unread_count=0),
    )


@app.get("/my-suggestions", response_class=HTMLResponse)
def my_suggestions_page(request: Request, status: str | None = None):
    if _current_role(request) == "manager":
        return _manager_on_employee_page(request, "mine")
    user = _employee_required(request)
    items = list_user_suggestions(user["id"])
    allowed = {"pending", "adopted", "rejected", "modified"}
    selected = status if status in allowed else "all"
    if selected != "all":
        items = [item for item in items if item.get("review_kind") == selected]
    return templates.TemplateResponse(
        request=request,
        name="my_suggestions.html",
        context=_context(request, page="mine", suggestions=items, status_filter=selected),
    )


@app.post("/manager/result/{suggestion_id}/decision")
def manager_decision(
    request: Request,
    suggestion_id: str,
    csrf_token: str = Form(...),
    decision: str = Form(...),
    manager_note: str = Form(""),
):
    _manager_required(request)
    _verify_csrf(request, csrf_token)
    if not is_suggestion_id(suggestion_id) or decision not in DECISION_KINDS:
        raise HTTPException(status_code=400, detail="قرار غير صالح.")
    suggestion = set_manager_decision(suggestion_id, decision, manager_note)
    if not suggestion:
        raise HTTPException(status_code=404)
    owner_id = suggestion.get("owner_user_id")
    if owner_id and is_suggestion_id(str(owner_id)):
        label = DECISION_LABELS[decision]
        note = suggestion.get("manager_note")
        body = f"مقترحك «{suggestion['title']}» — قرار المدير: {label}"
        if note:
            body = f"{body} — {note}"
        create_notification(
            {
                "id": uuid.uuid4().hex,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "user_id": owner_id,
                "suggestion_id": suggestion_id,
                "kind": decision,
                "title": f"قرار المدير: {label}",
                "body": body,
            }
        )
    _flash_success(request, f"تم حفظ القرار: {DECISION_LABELS[decision]}.")
    return RedirectResponse(f"/manager/result/{suggestion_id}", status_code=303)


@app.get("/manager", response_class=HTMLResponse)
def manager_dashboard(request: Request, department: str | None = None, view: str | None = None):
    _manager_required(request)
    selected = department if department in DEPARTMENTS else DEPARTMENTS[0]
    board_view = view if view in {"review", "top", "all"} else "review"
    counts = department_counts()
    pending_review = list_pending_review(selected, 80, allowed=DEPARTMENTS)
    pending_count = len(pending_review)
    top_five = top_suggestions(selected, 5, allowed=DEPARTMENTS) if board_view == "top" else []
    all_suggestions = list_department_suggestions(selected, 200, allowed=DEPARTMENTS) if board_view == "all" else []
    if board_view != "review":
        pending_review = []
    return templates.TemplateResponse(
        request=request,
        name="manager.html",
        context=_context(
            request,
            page="manager",
            selected_department=selected,
            board_view=board_view,
            top_five=top_five,
            pending_review=pending_review,
            pending_count=pending_count,
            all_suggestions=all_suggestions,
            all_count=counts.get(selected, 0),
            counts=counts,
        ),
    )


@app.get("/manager/result/{suggestion_id}", response_class=HTMLResponse)
def manager_result(request: Request, suggestion_id: str):
    _manager_required(request)
    if not is_suggestion_id(suggestion_id):
        raise HTTPException(status_code=404)
    suggestion = get_suggestion(suggestion_id)
    if not suggestion:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        request=request,
        name="result.html",
        context=_context(
            request,
            page="manager",
            suggestion=suggestion,
            model_error=None,
            manager_view=True,
            just_submitted=False,
            similar_items=similar_suggestions(
                suggestion_id,
                suggestion.get("department") or "",
                suggestion.get("title") or "",
                suggestion.get("problem") or "",
            ),
        ),
    )


@app.exception_handler(401)
def unauthorized(request: Request, exc):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"ok": False, "error": "يلزم تسجيل الدخول."}, status_code=401)
    if request.url.path.startswith("/manager") and request.method == "GET":
        return RedirectResponse("/login?role=manager&next=/manager", status_code=303)
    if request.method == "GET" and request.url.path.startswith(("/submit", "/notifications", "/my-suggestions")):
        nxt = request.url.path if request.url.path in {"/submit", "/notifications", "/my-suggestions"} else "/submit"
        return RedirectResponse(f"/login?role=employee&next={nxt}", status_code=303)
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context=_context(request, page="", code=401, message="يلزم تسجيل الدخول."),
        status_code=401,
    )


@app.exception_handler(403)
def forbidden(request: Request, exc):
    if request.method == "GET" and request.url.path.startswith("/manager"):
        return RedirectResponse("/", status_code=303)
    detail = getattr(exc, "detail", None)
    message = detail if isinstance(detail, str) and detail else "لا يمكنك الدخول إلى هذه الصفحة."
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context=_context(request, page="", code=403, message=message),
        status_code=403,
    )


@app.exception_handler(400)
def bad_request(request: Request, exc):
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context=_context(request, page="", code=400, message="طلب غير صالح."),
        status_code=400,
    )


@app.exception_handler(404)
def not_found(request: Request, exc):
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context=_context(request, page="", code=404, message="الصفحة المطلوبة غير موجودة."),
        status_code=404,
    )


@app.exception_handler(429)
def too_many_requests(request: Request, exc):
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context=_context(request, page="", code=429, message="عدد المحاولات كبير. حاول بعد قليل."),
        status_code=429,
    )


@app.exception_handler(Exception)
def unhandled_error(request: Request, exc):
    security_logger.exception("unhandled error from %s", _client_ip(request))
    try:
        log_path = BASE_DIR / "data" / "app_error.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n{datetime.now(timezone.utc).isoformat()} {request.method} {request.url.path}\n")
            handle.write(traceback.format_exc())
    except Exception:
        pass
    message = "حدث خطأ غير متوقع. أعد المحاولة بعد قليل."
    if request.url.path.startswith("/api/"):
        return JSONResponse({"ok": False, "error": message}, status_code=500)
    try:
        context = _context(request, page="", code=500, message=message)
    except Exception:
        context = {
            "request": request,
            "csrf_token": "",
            "model_mode": MODEL_MODE,
            "departments": DEPARTMENTS,
            "page": "",
            "code": 500,
            "message": message,
            "current_user": None,
            "unread_count": 0,
            "notifications_preview": [],
            "decision_labels": {},
            "flash_error": None,
        }
    return templates.TemplateResponse(
        request=request,
        name="error.html",
        context=context,
        status_code=500,
    )
