from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.services.dashboard_data import DashboardDataService
from app.services.realtime_session import (
    AVAILABILITY_TOOL_NAME,
    CALLBACK_REQUEST_SMS_TOOL_NAME,
    CREATE_RESERVATION_TOOL_NAME,
)

logger = logging.getLogger(__name__)

# This module is a deliberately narrow, aggregate-only reader for the public
# `/tilastot` route (SITE-02). It borrows only the malformed-JSON-tolerant
# file reader that already handles OSError/JSONDecodeError on a persisted
# session log; the per-session record builder that shapes admin-only,
# per-caller data is deliberately not reused here — there is no reachable
# code path from this module into that shape. Everything this module returns
# is a scalar count or a small dict of tool-name -> count, allow-list
# projected before it ever leaves `build_public_stats()`.

PUBLIC_CAPABILITY_TOOLS: tuple[str, ...] = (
    AVAILABILITY_TOOL_NAME,
    CREATE_RESERVATION_TOOL_NAME,
    CALLBACK_REQUEST_SMS_TOOL_NAME,
)


def build_public_stats(*, log_dir: Path | None = None) -> dict[str, Any]:
    resolved_log_dir = log_dir if log_dir is not None else Path(settings.conversation_log_dir)

    capability_usage: dict[str, int] = {tool: 0 for tool in PUBLIC_CAPABILITY_TOOLS}
    total_calls = 0

    if resolved_log_dir.exists():
        for session_path in sorted(resolved_log_dir.glob("session_*.json")):
            session = DashboardDataService._read_json(session_path)
            if session is None:
                continue
            total_calls += 1
            metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
            counts = metadata.get("capability_invocation_counts")
            if not isinstance(counts, dict):
                continue
            for tool in PUBLIC_CAPABILITY_TOOLS:
                value = counts.get(tool)
                if isinstance(value, int):
                    capability_usage[tool] += value

    return {
        "total_calls": total_calls,
        "capability_usage": capability_usage,
    }
