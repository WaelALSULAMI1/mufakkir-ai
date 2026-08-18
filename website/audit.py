from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

AUDIT_PATH = Path(__file__).resolve().parent / "data" / "audit.log"
MAX_BYTES = 2_000_000
ALLOWED_EVENTS = frozenset(
    {
        "login_success",
        "login_failure",
        "login_lockout",
        "path_blocked",
        "result_denied",
        "session_rejected",
    }
)
IP_RE = re.compile(r"^[A-Za-z0-9.:-]{1,64}$")


def _safe_ip(ip: str) -> str:
    return ip if IP_RE.fullmatch(ip or "") else "unknown"


def write_audit(event: str, ip: str, outcome: str = "ok") -> None:
    name = event if event in ALLOWED_EVENTS else "unknown"
    status = "ok" if outcome == "ok" else "denied"
    line = f"{datetime.now(timezone.utc).isoformat()}\t{name}\t{_safe_ip(ip)}\t{status}\n"
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if AUDIT_PATH.exists() and AUDIT_PATH.stat().st_size > MAX_BYTES:
        AUDIT_PATH.replace(AUDIT_PATH.with_suffix(".log.1"))
    with AUDIT_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line)
