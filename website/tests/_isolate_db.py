from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("SECRET_KEY", "unit-test-secret-key-not-for-production")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("MODEL_MODE", "disabled")
os.environ.setdefault(
    "JEDDAH_DB_PATH",
    str(Path(tempfile.gettempdir()) / "jeddah_test_suggestions.db"),
)

from database import init_db

init_db()

