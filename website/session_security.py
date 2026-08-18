from __future__ import annotations

import hashlib
import hmac
import time
from typing import Literal

from starlette.requests import Request

SESSION_IDLE_SECONDS = 30 * 60
SESSION_ABSOLUTE_SECONDS = 8 * 60 * 60
RejectReason = Literal["fingerprint", "idle", "absolute", "incomplete"]


def now_ts() -> int:
    return int(time.time())


def request_fingerprint(secret: str, request: Request) -> str:
    user_agent = (request.headers.get("user-agent") or "")[:300]
    digest = hmac.new(secret.encode("utf-8"), user_agent.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:32]


def stamp_new_session(request: Request, secret: str) -> None:
    current = now_ts()
    request.session["issued_at"] = current
    request.session["last_seen"] = current
    request.session["fp"] = request_fingerprint(secret, request)


def _is_authenticated_session(session: dict) -> bool:
    return session.get("role") in {"employee", "manager"} or session.get("manager_authenticated") is True


def enforce_session(request: Request, secret: str) -> RejectReason | None:
    session = request.session
    if not session or not _is_authenticated_session(session):
        return None
    issued = int(session.get("issued_at") or 0)
    last_seen = int(session.get("last_seen") or 0)
    stored = str(session.get("fp") or "")
    expected = request_fingerprint(secret, request)
    current = now_ts()
    if not issued or not last_seen or not stored:
        session.clear()
        return "incomplete"
    if not hmac.compare_digest(stored, expected):
        session.clear()
        return "fingerprint"
    if current - issued > SESSION_ABSOLUTE_SECONDS:
        session.clear()
        return "absolute"
    if current - last_seen > SESSION_IDLE_SECONDS:
        session.clear()
        return "idle"
    session["last_seen"] = current
    return None
