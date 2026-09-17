from __future__ import annotations

import logging
import time
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
# code path from this module into that shape, nor into any live/in-memory
# reservation store. Everything this module returns is a scalar count, a
# rounded average, a boolean or a small dict of tool-name -> count, allow-list
# projected through PUBLIC_STATS_FIELDS before it ever leaves
# `build_public_stats()`.

PUBLIC_CAPABILITY_TOOLS: tuple[str, ...] = (
    AVAILABILITY_TOOL_NAME,
    CREATE_RESERVATION_TOOL_NAME,
    CALLBACK_REQUEST_SMS_TOOL_NAME,
)

PUBLIC_STATS_FIELDS: tuple[str, ...] = (
    "total_calls",
    "reservation_calls",
    "average_duration_seconds",
    "capability_usage",
    "has_sufficient_sample",
)

PUBLIC_STATS_MIN_CALLS = 5
PUBLIC_STATS_CACHE_TTL_SECONDS = 30

# Process-local memo keyed on the resolved log directory, so a test passing an
# explicit directory can never be served another directory's cached numbers.
_stats_cache: dict[Path, tuple[float, dict[str, Any]]] = {}


def reset_public_stats_cache() -> None:
    _stats_cache.clear()


def build_public_stats(*, log_dir: Path | None = None) -> dict[str, Any]:
    resolved_log_dir = log_dir if log_dir is not None else Path(settings.conversation_log_dir)

    cached = _stats_cache.get(resolved_log_dir)
    if cached is not None:
        cached_at, cached_result = cached
        if time.monotonic() - cached_at < PUBLIC_STATS_CACHE_TTL_SECONDS:
            return cached_result

    capability_usage: dict[str, int] = {tool: 0 for tool in PUBLIC_CAPABILITY_TOOLS}
    total_calls = 0
    reservation_calls = 0
    durations: list[float] = []

    if resolved_log_dir.exists():
        for session_path in sorted(resolved_log_dir.glob("session_*.json")):
            session = DashboardDataService._read_json(session_path)
            if session is None:
                continue
            total_calls += 1

            metadata = (
                session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
            )

            counts = metadata.get("capability_invocation_counts")
            if isinstance(counts, dict):
                for tool in PUBLIC_CAPABILITY_TOOLS:
                    value = counts.get(tool)
                    if isinstance(value, int):
                        capability_usage[tool] += value

            if _record_has_reservation(metadata):
                reservation_calls += 1

            duration = session.get("duration_seconds")
            if isinstance(duration, (int, float)) and not isinstance(duration, bool):
                durations.append(float(duration))

    average_duration_seconds = (
        round(sum(durations) / len(durations), 1) if durations else None
    )
    has_sufficient_sample = total_calls >= PUBLIC_STATS_MIN_CALLS

    raw_result: dict[str, Any] = {
        "total_calls": total_calls,
        "reservation_calls": reservation_calls,
        "average_duration_seconds": average_duration_seconds,
        "capability_usage": capability_usage,
        "has_sufficient_sample": has_sufficient_sample,
    }

    projected = {key: raw_result[key] for key in PUBLIC_STATS_FIELDS}
    _stats_cache[resolved_log_dir] = (time.monotonic(), projected)
    return projected


def _record_has_reservation(metadata: dict[str, Any]) -> bool:
    # The server-recorded signal `transcript_service._build_redacted_metadata`
    # writes from confirmed-reservation history, never inferred from
    # transcript text. Fall back to reservation_count > 0 when the boolean
    # key is absent (older logs).
    flag = metadata.get("reservation_created")
    if isinstance(flag, bool):
        return flag
    count = metadata.get("reservation_count")
    if isinstance(count, (int, float)) and not isinstance(count, bool):
        return count > 0
    return False
