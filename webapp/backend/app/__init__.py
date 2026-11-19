"""HYDRO web backend package (FastAPI + SQLAlchemy + domain adapter)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from hidrostatik_test.app_metadata import APP_VERSION as __version__  # noqa: E402

__all__ = ["__version__"]
