from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from app.services.daily_summary import DailySummaryService, SendRollingDigestResult

logger = logging.getLogger(__name__)


class DailySummaryScheduler:
    def __init__(
        self,
        *,
        summary_service: DailySummaryService,
        timezone_name: str,
        send_time: str,
    ) -> None:
        self._summary_service = summary_service
        self._timezone = ZoneInfo(timezone_name)
        self._timezone_name = timezone_name
        self._send_hour, self._send_minute = self._parse_send_time(send_time)

    async def run_forever(self) -> None:
        while True:
            try:
                self.send_due_digest()
            except Exception:
                logger.exception("Daily summary auto-send failed.")

            next_run = self.next_run_after(datetime.now(self._timezone))
            delay_seconds = max(
                (next_run.astimezone(ZoneInfo("UTC")) - datetime.now(ZoneInfo("UTC"))).total_seconds(),
                1.0,
            )
            logger.info(
                "Daily summary scheduler sleeping until %s (%s)",
                next_run.isoformat(),
                self._timezone_name,
            )
            await asyncio.sleep(delay_seconds)

    def send_due_digest(self, *, now: Optional[datetime] = None) -> Optional[SendRollingDigestResult]:
        due_window_end = self.latest_due_window_end(now)
        if due_window_end is None:
            return None

        result = self._summary_service.send_last_24h_digest(window_end=due_window_end)
        logger.info(
            "Daily summary auto-send evaluated window_end=%s sent=%s skipped_reason=%s activities=%s",
            due_window_end.isoformat(),
            result.sent,
            result.skipped_reason,
            result.activities_found,
        )
        return result

    def latest_due_window_end(self, now: Optional[datetime] = None) -> Optional[datetime]:
        local_now = (now or datetime.now(self._timezone)).astimezone(self._timezone)
        candidate = local_now.replace(
            hour=self._send_hour,
            minute=self._send_minute,
            second=0,
            microsecond=0,
        )
        if local_now < candidate:
            return None
        return candidate

    def next_run_after(self, now: datetime) -> datetime:
        local_now = now.astimezone(self._timezone)
        candidate = local_now.replace(
            hour=self._send_hour,
            minute=self._send_minute,
            second=0,
            microsecond=0,
        )
        if local_now >= candidate:
            candidate += timedelta(days=1)
        return candidate

    @staticmethod
    def _parse_send_time(raw_value: str) -> tuple[int, int]:
        parts = raw_value.split(":", maxsplit=1)
        if len(parts) != 2:
            raise ValueError("DAILY_SUMMARY_SEND_TIME must use HH:MM format.")

        hour = int(parts[0])
        minute = int(parts[1])
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("DAILY_SUMMARY_SEND_TIME must be a valid 24-hour clock time.")
        return hour, minute
