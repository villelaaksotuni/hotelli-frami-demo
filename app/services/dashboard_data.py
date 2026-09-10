from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.config.settings import settings
from app.services.topic_taxonomy import infer_topic_keys, normalize_topic_keys

logger = logging.getLogger(__name__)

TOPIC_KEYWORDS = {
    "booking": ("book", "booking", "reserve", "vara", "varaus", "majoitus"),
    "availability": ("available", "availability", "saatav", "vapaa", "huone"),
    "pricing": ("price", "pricing", "hinta", "maksu", "euro"),
    "check_in_out": ("check in", "check-out", "check out", "sisään", "ulos"),
    "cancellation": ("cancel", "cancellation", "peruu"),
    "pets": ("pet", "dog", "cat", "lemmik"),
    "parking": ("parking", "parkki", "pysä"),
    "breakfast": ("breakfast", "aamupala", "aamiainen"),
}

TOPIC_LABELS = {
    "booking": "Varaus",
    "availability": "Saatavuus",
    "pricing": "Hinta",
    "check_in_out": "Sisään / uloskirjaus",
    "cancellation": "Peruutus",
    "pets": "Lemmikit",
    "parking": "Pysäköinti",
    "breakfast": "Aamiainen",
}

DIRECTION_LABELS = {
    "inbound": "Saapuva",
    "outbound": "Lähtevä",
    "unknown": "Tuntematon",
}

RESOLUTION_LABELS = {
    "resolved": "Ratkaistu",
    "unresolved": "Ratkaisematon",
}


@dataclass(frozen=True)
class DashboardCall:
    session_id: str
    occurred_at: str
    occurred_at_local: str
    occurred_date_local: str
    direction: str
    direction_label: str
    counterparty: str
    status: str
    resolution_status: str
    resolution_label: str
    duration_seconds: Optional[float]
    follow_up_needed: bool
    booking_link_shared: bool
    has_error: bool
    topics: list[str]
    topic_labels: list[str]
    summary: str
    caller_intent: str
    outcome: str
    transcript_turn_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_session_analytics(
    *,
    status: str,
    last_error: Optional[str],
    metadata: dict[str, Any],
    anonymized_summary: dict[str, Any],
    dialogue_turns: list[dict[str, Any]],
    transcript_turn_count: int,
) -> dict[str, Any]:
    direction = str(metadata.get("direction") or "unknown").strip().lower() or "unknown"
    counterparty_label = str(
        metadata.get("counterparty_label") or _pick_counterparty(metadata, direction)
    ).strip() or "unknown"
    topics = _extract_topics(anonymized_summary, dialogue_turns)
    follow_up_needed = bool(anonymized_summary.get("follow_up_needed", False))
    # Historical anonymized summaries may still carry this flag from calls
    # logged before the booking-link SMS tool was removed (02-02).
    booking_link_shared = bool(anonymized_summary.get("booking_link_shared", False))
    has_error = bool(last_error) or status != "completed"
    resolution_status = "resolved" if not has_error and not follow_up_needed else "unresolved"

    summary_text = _clean_text(anonymized_summary.get("summary"))
    caller_intent = _clean_text(anonymized_summary.get("caller_intent"))
    outcome = _clean_text(anonymized_summary.get("outcome"))

    return {
        "direction": direction,
        "direction_label": DIRECTION_LABELS.get(direction, DIRECTION_LABELS["unknown"]),
        "counterparty_label": counterparty_label,
        "topics": topics,
        "topic_labels": [TOPIC_LABELS.get(topic, topic) for topic in topics],
        "primary_topic": topics[0] if topics else None,
        "follow_up_needed": follow_up_needed,
        "booking_link_shared": booking_link_shared,
        "has_error": has_error,
        "resolution_status": resolution_status,
        "resolution_label": RESOLUTION_LABELS[resolution_status],
        "summary_preview": summary_text,
        "caller_intent": caller_intent,
        "outcome": outcome,
        "transcript_turn_count": transcript_turn_count,
    }


class DashboardDataService:
    def __init__(self, *, log_dir: Path, timezone_name: str) -> None:
        self._log_dir = log_dir
        self._timezone = ZoneInfo(timezone_name)
        self._timezone_name = timezone_name

    def build_dashboard_payload(
        self,
        *,
        now: Optional[datetime] = None,
        recent_call_limit: int = 10,
        trend_days: int = 7,
    ) -> dict[str, Any]:
        calls = self._load_call_records()
        local_now = (now or datetime.now(self._timezone)).astimezone(self._timezone)

        total_calls = len(calls)
        resolved_calls = sum(1 for call in calls if call.resolution_status == "resolved")
        unresolved_calls = total_calls - resolved_calls
        follow_up_calls = sum(1 for call in calls if call.follow_up_needed)
        error_calls = sum(1 for call in calls if call.has_error)
        booking_link_calls = sum(1 for call in calls if call.booking_link_shared)
        inbound_calls = sum(1 for call in calls if call.direction == "inbound")
        outbound_calls = sum(1 for call in calls if call.direction == "outbound")

        durations = [call.duration_seconds for call in calls if call.duration_seconds is not None]
        average_duration_seconds = round(sum(durations) / len(durations), 1) if durations else None
        resolution_rate = round((resolved_calls / total_calls) * 100, 1) if total_calls else None

        topic_counter: Counter[str] = Counter()
        for call in calls:
            topic_counter.update(call.topics)

        recent_calls = [call.to_dict() for call in calls[:recent_call_limit]]
        trend_end_date = (
            date.fromisoformat(calls[0].occurred_date_local)
            if calls
            else local_now.date()
        )
        trend = self._build_trend(calls, end_date=trend_end_date, trend_days=trend_days)
        topic_breakdown = [
            {"key": topic, "label": TOPIC_LABELS.get(topic, topic), "count": count}
            for topic, count in topic_counter.most_common(6)
        ]

        return {
            "generated_at": local_now.isoformat(),
            "timezone": self._timezone_name,
            "summary": {
                "total_calls": total_calls,
                "resolved_calls": resolved_calls,
                "unresolved_calls": unresolved_calls,
                "follow_up_calls": follow_up_calls,
                "error_calls": error_calls,
                "booking_link_calls": booking_link_calls,
                "inbound_calls": inbound_calls,
                "outbound_calls": outbound_calls,
                "average_duration_seconds": average_duration_seconds,
                "resolution_rate": resolution_rate,
            },
            "topic_breakdown": topic_breakdown,
            "trend": trend,
            "recent_calls": recent_calls,
        }

    def _load_call_records(self) -> list[DashboardCall]:
        if not self._log_dir.exists():
            return []

        calls: list[DashboardCall] = []
        for session_path in sorted(self._log_dir.glob("session_*.json"), reverse=True):
            session = self._read_json(session_path)
            if not session:
                continue
            record = self._build_call_record(session)
            if record is not None:
                calls.append(record)

        calls.sort(key=lambda item: item.occurred_at, reverse=True)
        return calls

    def _build_call_record(self, session: dict[str, Any]) -> Optional[DashboardCall]:
        occurred_at = _extract_occurrence_datetime(session)
        if occurred_at is None:
            return None

        metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
        anonymized_summary = (
            session.get("anonymized_summary")
            if isinstance(session.get("anonymized_summary"), dict)
            else {}
        )
        dialogue_turns = _normalize_dialogue_turns(session)
        transcript_turn_count = _read_turn_count(session, dialogue_turns)
        analytics = session.get("analytics") if isinstance(session.get("analytics"), dict) else {}
        if not analytics:
            analytics = build_session_analytics(
                status=str(session.get("status") or "unknown"),
                last_error=session.get("last_error"),
                metadata=metadata,
                anonymized_summary=anonymized_summary,
                dialogue_turns=dialogue_turns,
                transcript_turn_count=transcript_turn_count,
            )

        local_occurred_at = occurred_at.astimezone(self._timezone)
        topics = [str(topic) for topic in analytics.get("topics") or []]
        topic_labels = [
            str(label) for label in analytics.get("topic_labels") or [TOPIC_LABELS.get(topic, topic) for topic in topics]
        ]
        resolution_status = str(analytics.get("resolution_status") or "unresolved")
        direction = str(analytics.get("direction") or metadata.get("direction") or "unknown")

        summary_text = str(
            analytics.get("summary_preview")
            or anonymized_summary.get("summary")
            or _extract_summary_from_dialogue(dialogue_turns)
            or "Ei yhteenvetoa."
        )
        caller_intent = str(
            analytics.get("caller_intent")
            or anonymized_summary.get("caller_intent")
            or "Ei tunnistettua aikomusta."
        )
        outcome = str(
            analytics.get("outcome")
            or anonymized_summary.get("outcome")
            or "Lopputulos ei saatavilla."
        )

        return DashboardCall(
            session_id=str(session.get("stream_sid") or session.get("call_sid") or "unknown"),
            occurred_at=occurred_at.isoformat(),
            occurred_at_local=local_occurred_at.strftime("%d.%m.%Y %H:%M"),
            occurred_date_local=local_occurred_at.date().isoformat(),
            direction=direction,
            direction_label=str(
                analytics.get("direction_label") or DIRECTION_LABELS.get(direction, DIRECTION_LABELS["unknown"])
            ),
            counterparty=str(
                analytics.get("counterparty_label")
                or metadata.get("counterparty_label")
                or _pick_counterparty(metadata, direction)
            ),
            status=str(session.get("status") or "unknown"),
            resolution_status=resolution_status,
            resolution_label=str(
                analytics.get("resolution_label")
                or RESOLUTION_LABELS.get(resolution_status, RESOLUTION_LABELS["unresolved"])
            ),
            duration_seconds=_read_float(session.get("duration_seconds")),
            follow_up_needed=bool(analytics.get("follow_up_needed", False)),
            booking_link_shared=bool(analytics.get("booking_link_shared", False)),
            has_error=bool(analytics.get("has_error", False)),
            topics=topics,
            topic_labels=topic_labels,
            summary=summary_text,
            caller_intent=caller_intent,
            outcome=outcome,
            transcript_turn_count=transcript_turn_count,
        )

    def _build_trend(
        self,
        calls: list[DashboardCall],
        *,
        end_date,
        trend_days: int,
    ) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for offset in range(trend_days - 1, -1, -1):
            current_date = end_date - timedelta(days=offset)
            key = current_date.isoformat()
            buckets[key] = {
                "date": key,
                "label": current_date.strftime("%d.%m"),
                "calls": 0,
                "resolved": 0,
                "unresolved": 0,
            }

        for call in calls:
            bucket = buckets.get(call.occurred_date_local)
            if bucket is None:
                continue
            bucket["calls"] += 1
            if call.resolution_status == "resolved":
                bucket["resolved"] += 1
            else:
                bucket["unresolved"] += 1

        return list(buckets.values())

    @staticmethod
    def _read_json(path: Path) -> Optional[dict[str, Any]]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, JSONDecodeError):
            logger.warning("Failed to read dashboard session log: %s", path)
            return None
        return payload if isinstance(payload, dict) else None


def _extract_occurrence_datetime(session: dict[str, Any]) -> Optional[datetime]:
    for field in ("ended_at", "started_at", "created_at"):
        raw_value = session.get(field)
        if not raw_value:
            continue
        try:
            return datetime.fromisoformat(str(raw_value))
        except ValueError:
            continue
    return None


def _normalize_dialogue_turns(session: dict[str, Any]) -> list[dict[str, Any]]:
    dialogue_turns = session.get("dialogue_turns")
    if isinstance(dialogue_turns, list):
        return [turn for turn in dialogue_turns if isinstance(turn, dict)]

    transcript_entries = session.get("transcript_entries")
    if not isinstance(transcript_entries, list):
        return []

    merged_turns: list[dict[str, Any]] = []
    for entry in transcript_entries:
        if not isinstance(entry, dict):
            continue
        speaker = str(entry.get("speaker") or "").strip()
        text = str(entry.get("text") or "").strip()
        if not speaker or not text:
            continue
        if not merged_turns or merged_turns[-1]["speaker"] != speaker:
            merged_turns.append({"speaker": speaker, "text": text})
        else:
            merged_turns[-1]["text"] += "\n" + text
    return merged_turns


def _read_turn_count(session: dict[str, Any], dialogue_turns: list[dict[str, Any]]) -> int:
    value = session.get("transcript_turn_count")
    if isinstance(value, int):
        return value
    return len(dialogue_turns)


def _extract_summary(dialogue_turns: list[dict[str, Any]]) -> str:
    return "\n".join(
        str(turn.get("text") or "").strip()
        for turn in dialogue_turns
        if isinstance(turn, dict) and str(turn.get("text") or "").strip()
    )


def _extract_topics(
    anonymized_summary: dict[str, Any],
    dialogue_turns: list[dict[str, Any]],
) -> list[str]:
    searchable_text = (
        _clean_text(anonymized_summary.get("summary"))
        + "\n"
        + _clean_text(anonymized_summary.get("caller_intent"))
        + "\n"
        + _clean_text(anonymized_summary.get("outcome"))
        + "\n"
        + _extract_summary(dialogue_turns)
    )

    explicit_topics = normalize_topic_keys(anonymized_summary.get("topics") or [])
    inferred_topics = infer_topic_keys(searchable_text)
    merged_topics: list[str] = []
    for topic in [*explicit_topics, *inferred_topics]:
        if topic not in merged_topics:
            merged_topics.append(topic)
    return merged_topics[:6]


def _pick_counterparty(metadata: dict[str, Any], direction: str) -> str:
    if metadata.get("counterparty_label"):
        return str(metadata["counterparty_label"])
    if direction == "outbound":
        return str(metadata.get("to_number") or "unknown")
    if direction == "inbound":
        return str(metadata.get("from_number") or "unknown")
    return str(metadata.get("to_number") or metadata.get("from_number") or "unknown")


def _extract_summary_from_dialogue(dialogue_turns: list[dict[str, Any]]) -> str:
    for turn in dialogue_turns:
        if str(turn.get("speaker") or "").strip().lower() == "user":
            text = _clean_text(turn.get("text"))
            if text:
                return text
    return ""


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _read_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


dashboard_data_service = DashboardDataService(
    log_dir=Path(settings.conversation_log_dir),
    timezone_name=settings.daily_summary_timezone,
)
