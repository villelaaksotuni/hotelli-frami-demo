from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.config.settings import settings
from app.services.topic_taxonomy import infer_topic_keys, normalize_topic_keys

logger = logging.getLogger(__name__)

SUMMARY_TOPIC_KEYWORDS = {
    "booking": (
        "book",
        "booking",
        "reserve",
        "reservation",
        "varaa",
        "varaus",
    ),
    "availability": (
        "availability",
        "available",
        "saatavuus",
        "vapaa",
        "room",
        "huone",
        "mokki",
        "apartment",
    ),
    "pricing": (
        "price",
        "pricing",
        "rate",
        "cost",
        "hinta",
        "euro",
    ),
    "check_in_out": (
        "check in",
        "check-in",
        "check out",
        "check-out",
        "sisaan",
        "ulos",
    ),
    "cancellation": (
        "cancel",
        "cancellation",
        "peruut",
    ),
    "pets": (
        "pet",
        "dog",
        "cat",
        "lemmik",
    ),
    "parking": (
        "parking",
        "parkki",
        "pysak",
    ),
    "breakfast": (
        "breakfast",
        "aamupala",
    ),
}

TOPIC_LABELS_FI = {
    "booking": "varaus",
    "availability": "saatavuus",
    "pricing": "hinnat",
    "check_in_out": "sisään- ja uloskirjautuminen",
    "cancellation": "peruutukset",
    "pets": "lemmikit",
    "parking": "pysäköinti",
    "breakfast": "aamiainen",
}


@dataclass(frozen=True)
class DailyActivity:
    session_id: str
    occurred_at: str
    direction: str
    counterparty: str
    status: str
    duration_seconds: Optional[float]
    termination_reason: Optional[str]
    topics: list[str]
    first_user_utterance: str
    highlight: str
    transcript_turn_count: int


@dataclass(frozen=True)
class DailyDigest:
    summary_date: str
    timezone: str
    total_activities: int
    completed_activities: int
    error_activities: int
    average_duration_seconds: Optional[float]
    topic_counts: dict[str, int]
    highlights: list[str]
    sms_body: str
    activities: list[DailyActivity]


@dataclass(frozen=True)
class SendDailyDigestResult:
    summary_date: str
    activities_found: int
    sent: bool
    skipped_reason: Optional[str]
    sms_body: str
    message_sid: Optional[str] = None


@dataclass(frozen=True)
class RollingDigest:
    window_start: str
    window_end: str
    timezone: str
    total_activities: int
    completed_activities: int
    error_activities: int
    average_duration_seconds: Optional[float]
    topic_counts: dict[str, int]
    highlights: list[str]
    sms_body: str
    activities: list[DailyActivity]


@dataclass(frozen=True)
class SendRollingDigestResult:
    history_key: str
    window_start: str
    window_end: str
    activities_found: int
    sent: bool
    skipped_reason: Optional[str]
    sms_body: str
    message_sid: Optional[str] = None


class DailySummaryService:
    def __init__(
        self,
        *,
        log_dir: Path,
        history_path: Path,
        timezone_name: str,
        to_phone: Optional[str],
        from_phone: Optional[str],
        twilio_client: Any,
    ) -> None:
        self._log_dir = log_dir
        self._history_path = history_path
        self._timezone = ZoneInfo(timezone_name)
        self._timezone_name = timezone_name
        self._to_phone = to_phone
        self._from_phone = from_phone
        self._twilio_client = twilio_client

    def default_summary_date(self, *, now: Optional[datetime] = None) -> date:
        local_now = (now or datetime.now(self._timezone)).astimezone(self._timezone)
        return (local_now - timedelta(days=1)).date()

    def local_today(self, *, now: Optional[datetime] = None) -> date:
        return (now or datetime.now(self._timezone)).astimezone(self._timezone).date()

    def history_key_for_window_end(self, window_end: datetime) -> str:
        local_window_end = window_end.astimezone(self._timezone).replace(second=0, microsecond=0)
        return f"rolling_24h:{local_window_end.isoformat()}"

    def build_digest(self, summary_date: date) -> DailyDigest:
        sessions = self._load_sessions_for_date(summary_date)
        return self._build_daily_digest(summary_date, sessions)

    def build_last_24h_digest(self, *, window_end: Optional[datetime] = None) -> RollingDigest:
        resolved_window_end = (window_end or datetime.now(self._timezone)).astimezone(
            self._timezone
        )
        resolved_window_end = resolved_window_end.replace(second=0, microsecond=0)
        window_start = resolved_window_end - timedelta(hours=24)
        sessions = self._load_sessions_for_window(window_start, resolved_window_end)
        return self._build_rolling_digest(window_start, resolved_window_end, sessions)

    def send_digest(
        self,
        summary_date: date,
        *,
        force: bool = False,
        dry_run: bool = False,
    ) -> SendDailyDigestResult:
        digest = self.build_digest(summary_date)
        if digest.total_activities <= 0:
            return SendDailyDigestResult(
                summary_date=digest.summary_date,
                activities_found=0,
                sent=False,
                skipped_reason="no_activities",
                sms_body=digest.sms_body,
            )

        history = self._read_history()
        if not force and digest.summary_date in history:
            return SendDailyDigestResult(
                summary_date=digest.summary_date,
                activities_found=digest.total_activities,
                sent=False,
                skipped_reason="already_sent",
                sms_body=digest.sms_body,
                message_sid=history[digest.summary_date].get("message_sid"),
            )

        self._validate_send_configuration()

        message_sid = None
        if not dry_run:
            message = self._twilio_client.messages.create(
                body=digest.sms_body,
                from_=self._from_phone,
                to=self._to_phone,
            )
            message_sid = getattr(message, "sid", None)
            self._write_history_entry(
                history_key=digest.summary_date,
                message_sid=message_sid,
                activities_found=digest.total_activities,
                sms_body=digest.sms_body,
                metadata={
                    "kind": "daily_date",
                    "summary_date": digest.summary_date,
                    "topic_counts": digest.topic_counts,
                },
            )

        return SendDailyDigestResult(
            summary_date=digest.summary_date,
            activities_found=digest.total_activities,
            sent=not dry_run,
            skipped_reason="dry_run" if dry_run else None,
            sms_body=digest.sms_body,
            message_sid=message_sid,
        )

    def send_last_24h_digest(
        self,
        *,
        window_end: Optional[datetime] = None,
        force: bool = False,
        dry_run: bool = False,
    ) -> SendRollingDigestResult:
        digest = self.build_last_24h_digest(window_end=window_end)
        history_key = self.history_key_for_window_end(datetime.fromisoformat(digest.window_end))
        if digest.total_activities <= 0:
            return SendRollingDigestResult(
                history_key=history_key,
                window_start=digest.window_start,
                window_end=digest.window_end,
                activities_found=0,
                sent=False,
                skipped_reason="no_activities",
                sms_body=digest.sms_body,
            )

        history = self._read_history()
        if not force and history_key in history:
            return SendRollingDigestResult(
                history_key=history_key,
                window_start=digest.window_start,
                window_end=digest.window_end,
                activities_found=digest.total_activities,
                sent=False,
                skipped_reason="already_sent",
                sms_body=digest.sms_body,
                message_sid=history[history_key].get("message_sid"),
            )

        self._validate_send_configuration()

        message_sid = None
        if not dry_run:
            message = self._twilio_client.messages.create(
                body=digest.sms_body,
                from_=self._from_phone,
                to=self._to_phone,
            )
            message_sid = getattr(message, "sid", None)
            self._write_history_entry(
                history_key=history_key,
                message_sid=message_sid,
                activities_found=digest.total_activities,
                sms_body=digest.sms_body,
                metadata={
                    "kind": "rolling_24h",
                    "window_start": digest.window_start,
                    "window_end": digest.window_end,
                    "topic_counts": digest.topic_counts,
                },
            )

        return SendRollingDigestResult(
            history_key=history_key,
            window_start=digest.window_start,
            window_end=digest.window_end,
            activities_found=digest.total_activities,
            sent=not dry_run,
            skipped_reason="dry_run" if dry_run else None,
            sms_body=digest.sms_body,
            message_sid=message_sid,
        )

    def _build_daily_digest(
        self,
        summary_date: date,
        sessions: list[dict[str, Any]],
    ) -> DailyDigest:
        activities, total_activities, completed_activities, error_activities, average_duration_seconds, topic_counts, highlights = self._summarize_sessions(
            sessions
        )
        sms_body = self._format_daily_sms_body(
            summary_date=summary_date,
            total_activities=total_activities,
            completed_activities=completed_activities,
            error_activities=error_activities,
            average_duration_seconds=average_duration_seconds,
            topic_counts=topic_counts,
            highlights=highlights,
        )

        return DailyDigest(
            summary_date=summary_date.isoformat(),
            timezone=self._timezone_name,
            total_activities=total_activities,
            completed_activities=completed_activities,
            error_activities=error_activities,
            average_duration_seconds=average_duration_seconds,
            topic_counts=topic_counts,
            highlights=highlights,
            sms_body=sms_body,
            activities=activities,
        )

    def _build_rolling_digest(
        self,
        window_start: datetime,
        window_end: datetime,
        sessions: list[dict[str, Any]],
    ) -> RollingDigest:
        activities, total_activities, completed_activities, error_activities, average_duration_seconds, topic_counts, highlights = self._summarize_sessions(
            sessions
        )
        sms_body = self._format_rolling_sms_body(
            window_start=window_start,
            window_end=window_end,
            total_activities=total_activities,
            completed_activities=completed_activities,
            error_activities=error_activities,
            average_duration_seconds=average_duration_seconds,
            topic_counts=topic_counts,
            highlights=highlights,
        )

        return RollingDigest(
            window_start=window_start.isoformat(),
            window_end=window_end.isoformat(),
            timezone=self._timezone_name,
            total_activities=total_activities,
            completed_activities=completed_activities,
            error_activities=error_activities,
            average_duration_seconds=average_duration_seconds,
            topic_counts=topic_counts,
            highlights=highlights,
            sms_body=sms_body,
            activities=activities,
        )

    def _summarize_sessions(
        self,
        sessions: list[dict[str, Any]],
    ) -> tuple[
        list[DailyActivity],
        int,
        int,
        int,
        Optional[float],
        dict[str, int],
        list[str],
    ]:
        activities = [self._build_activity(session) for session in sessions]
        total_activities = len(activities)
        completed_activities = sum(1 for activity in activities if activity.status == "completed")
        error_activities = total_activities - completed_activities

        durations = [
            activity.duration_seconds
            for activity in activities
            if activity.duration_seconds is not None
        ]
        average_duration_seconds = (
            round(sum(durations) / len(durations), 1) if durations else None
        )

        topic_counter: Counter[str] = Counter()
        for activity in activities:
            topic_counter.update(activity.topics)

        highlights = [activity.highlight for activity in activities[:3]]
        return (
            activities,
            total_activities,
            completed_activities,
            error_activities,
            average_duration_seconds,
            dict(topic_counter),
            highlights,
        )

    def _load_sessions_for_date(self, summary_date: date) -> list[dict[str, Any]]:
        window_start = datetime.combine(summary_date, time.min, tzinfo=self._timezone)
        window_end = window_start + timedelta(days=1)
        return self._load_sessions_for_window(window_start, window_end)

    def _load_sessions_for_window(
        self,
        window_start: datetime,
        window_end: datetime,
    ) -> list[dict[str, Any]]:
        if not self._log_dir.exists():
            return []

        sessions = []
        for session_path in sorted(self._log_dir.glob("session_*.json")):
            session = self._read_json(session_path)
            if not session:
                continue

            occurred_at = self._extract_occurrence_datetime(session)
            if occurred_at is None:
                continue

            local_occurred_at = occurred_at.astimezone(self._timezone)
            if local_occurred_at < window_start or local_occurred_at >= window_end:
                continue

            session["_occurred_at"] = occurred_at.isoformat()
            sessions.append(session)

        sessions.sort(key=lambda item: item["_occurred_at"], reverse=True)
        return sessions

    def _build_activity(self, session: dict[str, Any]) -> DailyActivity:
        metadata = session.get("metadata") or {}
        dialogue_turns = session.get("dialogue_turns") or []
        anonymized_summary = session.get("anonymized_summary") or {}
        transcript_text = self._extract_summary_text(session)
        topics = self._extract_topics(session, transcript_text)

        session_id = str(session.get("stream_sid") or session.get("call_sid") or "unknown")
        direction = str(metadata.get("direction") or "unknown")
        counterparty = self._pick_counterparty(metadata, direction)
        first_user_utterance = (
            str(anonymized_summary.get("first_user_utterance_redacted") or "").strip()
            or self._first_user_utterance(dialogue_turns)
        )
        highlight = self._build_highlight(
            occurred_at=session["_occurred_at"],
            direction=direction,
            counterparty=counterparty,
            topics=topics,
            first_user_utterance=first_user_utterance,
            session=session,
        )

        return DailyActivity(
            session_id=session_id,
            occurred_at=session["_occurred_at"],
            direction=direction,
            counterparty=counterparty,
            status=str(session.get("status") or "unknown"),
            duration_seconds=self._read_float(session.get("duration_seconds")),
            termination_reason=session.get("termination_reason"),
            topics=topics,
            first_user_utterance=first_user_utterance,
            highlight=highlight,
            transcript_turn_count=self._extract_transcript_turn_count(session),
        )

    def _format_daily_sms_body(
        self,
        *,
        summary_date: date,
        total_activities: int,
        completed_activities: int,
        error_activities: int,
        average_duration_seconds: Optional[float],
        topic_counts: dict[str, int],
        highlights: list[str],
    ) -> str:
        return self._format_sms_body(
            header=f"Hotelli Frami AI-yhteenveto {summary_date.isoformat()}",
            intro_lines=[],
            total_activities=total_activities,
            completed_activities=completed_activities,
            error_activities=error_activities,
            average_duration_seconds=average_duration_seconds,
            topic_counts=topic_counts,
            highlights=highlights,
        )

    def _format_rolling_sms_body(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        total_activities: int,
        completed_activities: int,
        error_activities: int,
        average_duration_seconds: Optional[float],
        topic_counts: dict[str, int],
        highlights: list[str],
    ) -> str:
        return self._format_sms_body(
            header="Hotelli Frami AI-yhteenveto viimeiset 24 h",
            intro_lines=[
                (
                    "Ajanjakso "
                    f"{window_start.strftime('%Y-%m-%d %H:%M')} - "
                    f"{window_end.strftime('%Y-%m-%d %H:%M')} "
                    f"{window_end.tzname() or self._timezone_name}."
                ),
            ],
            total_activities=total_activities,
            completed_activities=completed_activities,
            error_activities=error_activities,
            average_duration_seconds=average_duration_seconds,
            topic_counts=topic_counts,
            highlights=highlights,
        )

    def _format_sms_body(
        self,
        *,
        header: str,
        intro_lines: list[str],
        total_activities: int,
        completed_activities: int,
        error_activities: int,
        average_duration_seconds: Optional[float],
        topic_counts: dict[str, int],
        highlights: list[str],
    ) -> str:
        topic_text = ", ".join(
            f"{TOPIC_LABELS_FI.get(topic, topic)} {count}"
            for topic, count in sorted(
                topic_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )[:4]
        )
        if not topic_text:
            topic_text = "ei toistuvia aiheita"

        duration_text = (
            self._format_duration(average_duration_seconds)
            if average_duration_seconds is not None
            else "ei saatavilla"
        )

        lines = [
            header,
            *intro_lines,
            (
                f"Puhelut {total_activities}, käsitelty {completed_activities}, "
                f"virheet {error_activities}, keskipituus {duration_text}."
            ),
            f"Aiheet: {topic_text}.",
        ]

        if highlights:
            lines.append("Nostot:")
            for index, highlight in enumerate(highlights, start=1):
                lines.append(f"{index}. {highlight}")

        sms_body = "\n".join(lines)
        return sms_body[:1500]

    def _build_highlight(
        self,
        *,
        occurred_at: str,
        direction: str,
        counterparty: str,
        topics: list[str],
        first_user_utterance: str,
        session: dict[str, Any],
    ) -> str:
        local_time = datetime.fromisoformat(occurred_at).astimezone(self._timezone)
        time_label = local_time.strftime("%H:%M")
        topic_label = (
            ", ".join(TOPIC_LABELS_FI.get(topic, topic) for topic in topics[:2])
            if topics
            else "yleinen kysely"
        )
        snippet = self._compact_text(first_user_utterance or "ei tallennettua asiakkaan viestiä", 70)
        anonymized_summary = session.get("anonymized_summary") or {}
        summary_text = self._compact_text(str(anonymized_summary.get("summary") or ""), 90)
        outcome_text = self._compact_text(str(anonymized_summary.get("outcome") or ""), 60)
        direction_label = {
            "inbound": "saapuva",
            "outbound": "lähtevä",
        }.get(direction, direction)

        if "booking" in topics and "availability" in topics:
            topic_label = "varaus ja saatavuus"
        elif "booking" in topics:
            topic_label = "varaus"
        elif "availability" in topics:
            topic_label = "saatavuus"

        if self._contains_reservation(session):
            suffix = "varaus tehty"
        elif session.get("last_error"):
            suffix = "päättyi virheeseen"
        else:
            suffix = "puhelu hoidettu"

        if summary_text:
            detail = summary_text
        elif snippet:
            detail = f"asiakas sanoi '{snippet}'"
        else:
            detail = "ei tarkempaa yhteenvetoa"

        if outcome_text:
            suffix = f"{suffix}; lopputulos: {outcome_text}"

        return (
            f"{time_label} {direction_label} {counterparty}: {topic_label}; "
            f"{detail}; {suffix}."
        )

    def _contains_reservation(self, session: dict[str, Any]) -> bool:
        # The server-recorded signal is authoritative — never inferred from
        # dialogue-turn text, so a caller cannot forge it by speech (T-02-06).
        analytics = session.get("analytics") or {}
        if "reservation_created" in analytics:
            return analytics.get("reservation_created") is True
        anonymized_summary = session.get("anonymized_summary") or {}
        return anonymized_summary.get("reservation_created") is True

    def _extract_occurrence_datetime(self, session: dict[str, Any]) -> Optional[datetime]:
        for field in ("ended_at", "started_at", "created_at"):
            raw_value = session.get(field)
            if not raw_value:
                continue
            try:
                return datetime.fromisoformat(str(raw_value))
            except ValueError:
                continue
        return None

    def _pick_counterparty(self, metadata: dict[str, Any], direction: str) -> str:
        if metadata.get("counterparty_label"):
            return str(metadata["counterparty_label"])
        if direction == "outbound":
            return str(metadata.get("to_number") or "unknown")
        if direction == "inbound":
            return str(metadata.get("from_number") or "unknown")
        return str(metadata.get("to_number") or metadata.get("from_number") or "unknown")

    def _extract_summary_text(self, session: dict[str, Any]) -> str:
        anonymized_summary = session.get("anonymized_summary") or {}
        summary_parts = [
            str(anonymized_summary.get("summary") or "").strip(),
            str(anonymized_summary.get("caller_intent") or "").strip(),
            str(anonymized_summary.get("outcome") or "").strip(),
        ]
        combined = "\n".join(part for part in summary_parts if part)
        if combined:
            return combined

        dialogue_turns = session.get("dialogue_turns") or []
        return "\n".join(
            str(turn.get("text") or "")
            for turn in dialogue_turns
            if isinstance(turn, dict)
        )

    def _extract_topics(self, session: dict[str, Any], transcript_text: str) -> list[str]:
        anonymized_summary = session.get("anonymized_summary") or {}
        explicit_topics = normalize_topic_keys(anonymized_summary.get("topics") or [])
        inferred_topics = infer_topic_keys(transcript_text)
        merged_topics: list[str] = []
        for topic in [*explicit_topics, *inferred_topics]:
            if topic not in merged_topics:
                merged_topics.append(topic)
        return merged_topics[:6]

    def _extract_transcript_turn_count(self, session: dict[str, Any]) -> int:
        value = session.get("transcript_turn_count")
        if isinstance(value, int):
            return value
        dialogue_turns = session.get("dialogue_turns") or []
        return len(dialogue_turns)

    def _first_user_utterance(self, dialogue_turns: list[Any]) -> str:
        for turn in dialogue_turns:
            if not isinstance(turn, dict):
                continue
            if str(turn.get("speaker") or "").strip().lower() != "user":
                continue
            text = str(turn.get("text") or "").strip()
            if text:
                return text.replace("\n", " ")
        return ""

    def _read_history(self) -> dict[str, Any]:
        if not self._history_path.exists():
            return {}
        try:
            payload = json.loads(self._history_path.read_text(encoding="utf-8"))
        except (OSError, JSONDecodeError) as exc:
            logger.warning("Failed to read daily summary history at %s: %s", self._history_path, exc)
            return {}
        return payload if isinstance(payload, dict) else {}

    def _validate_send_configuration(self) -> None:
        if not self._to_phone:
            raise ValueError("DAILY_SUMMARY_TO_PHONE is not configured.")
        if not self._from_phone:
            raise ValueError("TWILIO_PHONE_NUMBER is not configured.")
        if self._twilio_client is None:
            raise ValueError("Twilio client is not configured.")

    def _write_history_entry(
        self,
        *,
        history_key: str,
        message_sid: Optional[str],
        activities_found: int,
        sms_body: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        history = self._read_history()
        history[history_key] = {
            "sent_at": datetime.now(self._timezone).isoformat(),
            "message_sid": message_sid,
            "activities_found": activities_found,
            "sms_body": sms_body,
            **(metadata or {}),
        }
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        self._history_path.write_text(
            json.dumps(history, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _compact_text(value: str, max_length: int) -> str:
        compact = " ".join(value.split())
        return compact if len(compact) <= max_length else compact[: max_length - 3].rstrip() + "..."

    @staticmethod
    def _format_duration(value: float) -> str:
        rounded_seconds = int(round(value))
        minutes, seconds = divmod(rounded_seconds, 60)
        if minutes <= 0:
            return f"{seconds}s"
        return f"{minutes}m{seconds:02d}s"

    @staticmethod
    def _read_json(path: Path) -> Optional[dict[str, Any]]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _read_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


daily_summary_service = DailySummaryService(
    log_dir=Path(settings.conversation_log_dir),
    history_path=Path(settings.daily_summary_history_path),
    timezone_name=settings.daily_summary_timezone,
    to_phone=settings.daily_summary_to_phone,
    from_phone=settings.twilio_phone_number,
    twilio_client=settings.twilio_client,
)
