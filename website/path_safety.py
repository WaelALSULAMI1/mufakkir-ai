from __future__ import annotations

import logging
import re
from pathlib import Path
from urllib.parse import unquote

from starlette._utils import get_route_path
from starlette.staticfiles import StaticFiles

logger = logging.getLogger("jeddah.security")

SAFE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SUGGESTION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
MAX_PATH_LENGTH = 256
MAX_DECODE_ROUNDS = 3
MAX_STATIC_DEPTH = 3


def _fully_unquote(value: str) -> str:
    current = value
    for _ in range(MAX_DECODE_ROUNDS):
        decoded = unquote(current)
        if decoded == current:
            break
        current = decoded
    return current


def request_path_is_safe(path: str) -> bool:
    """Fail closed: reject parent segments, encodings, and Windows path tricks."""
    if not isinstance(path, str) or not path or len(path) > MAX_PATH_LENGTH:
        return False
    if "\x00" in path or "%" in path and "%00" in path.lower():
        return False

    decoded = _fully_unquote(path)
    if len(decoded) > MAX_PATH_LENGTH or "\x00" in decoded:
        return False

    normalized = decoded.replace("\\", "/")
    raw_normalized = path.replace("\\", "/")
    for candidate in (path, decoded, normalized, raw_normalized, path.casefold(), decoded.casefold()):
        if ".." in candidate or "\\" in candidate:
            return False

    if re.search(r"(^|/)[a-zA-Z]:(/|$)", normalized):
        return False
    if "//" in normalized or normalized.startswith("//"):
        return False

    for segment in normalized.split("/"):
        if segment in {".", ".."}:
            return False
        if ":" in segment:
            return False
    return True


def is_suggestion_id(suggestion_id: str) -> bool:
    return bool(suggestion_id) and bool(SUGGESTION_ID_RE.fullmatch(suggestion_id.lower()))


def load_static_allowlist(static_dir: Path) -> frozenset[str]:
    allowed: set[str] = set()
    root = static_dir.resolve()
    if not root.is_dir():
        return frozenset()

    for item in root.rglob("*"):
        if not item.is_file() or item.is_symlink():
            continue
        try:
            relative = item.resolve().relative_to(root)
        except ValueError:
            continue
        parts = relative.parts
        if not parts or len(parts) > MAX_STATIC_DEPTH:
            continue
        if any(part.startswith(".") or ".." in part or not SAFE_SEGMENT_RE.fullmatch(part) for part in parts):
            continue
        allowed.add(relative.as_posix())
    return frozenset(allowed)


def safe_join(base_dir: Path, relative: str) -> Path | None:
    if not relative or relative.startswith(("/", "\\")):
        return None
    posix = relative.replace("\\", "/")
    if not request_path_is_safe("/" + posix):
        return None

    parts = [part for part in posix.split("/") if part]
    if not parts or any(part in {".", ".."} or not SAFE_SEGMENT_RE.fullmatch(part) for part in parts):
        return None

    root = base_dir.resolve()
    candidate = root.joinpath(*parts).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if candidate.is_symlink() or not candidate.is_file():
        return None
    return candidate


class AllowlistStaticFiles(StaticFiles):
    """Serve only files discovered at startup. Unknown or escaped paths are 404."""

    def __init__(self, directory: Path, allowed_names: frozenset[str]) -> None:
        super().__init__(directory=directory, html=False, follow_symlink=False, check_dir=True)
        self.allowed_names = allowed_names
        self._base = Path(directory).resolve()

    def get_path(self, scope) -> str:
        return get_route_path(scope).lstrip("/")

    def lookup_path(self, path: str):
        normalized = str(path or "").replace("\\", "/").lstrip("/")
        if normalized not in self.allowed_names:
            return "", None
        safe = safe_join(self._base, normalized)
        if safe is None:
            return "", None
        try:
            return str(safe), safe.stat()
        except OSError:
            return "", None
