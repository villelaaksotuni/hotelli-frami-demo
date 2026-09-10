import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict

from app.config.settings import settings
from app.models.call import CallSession, ConversationLog
from app.services.conversation_anonymizer import conversation_anonymizer
from app.services.dashboard_data import build_session_analytics

logger = logging.getLogger(__name__)


async def save_conversation_log(session: CallSession) -> ConversationLog:
    """
    Save session metadata and transcript logs to local JSON files.

    TODO:
    - replace or extend with DB persistence
    - persist session records and transcript events in normalized tables
    - store summaries, extracted slots, or booking intent later
    """
    anonymized_summary = await conversation_anonymizer.summarize_session(session)
    dialogue_turns = await asyncio.to_thread(_write_session_logs, session, anonymized_summary)
    logger.info(
        "Saved privacy-reduced call session for stream_sid=%s (%s transcript entries, duration=%ss, method=%s)",
        session.stream_sid,
        len(session.transcript_entries),
        session.duration_seconds(),
        anonymized_summary.anonymization_method,
    )
    return dialogue_turns


def _write_session_logs(session: CallSession, anonymized_summary) -> ConversationLog:
    log_dir = settings.conversation_log_dir
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_identifier = session.stream_sid or session.call_sid or "unknown_session"

    session_record = _build_session_record(session, anonymized_summary.to_dict())
    session_log_path = os.path.join(log_dir, f"session_{session_identifier}_{timestamp}.json")
    with open(session_log_path, "w", encoding="utf-8") as file_handle:
        json.dump(session_record, file_handle, ensure_ascii=False, indent=2)

    summary_log_path = os.path.join(
        log_dir, f"conversation_summary_{session_identifier}_{timestamp}.json"
    )
    with open(summary_log_path, "w", encoding="utf-8") as file_handle:
        json.dump(anonymized_summary.to_dict(), file_handle, ensure_ascii=False, indent=2)

    return session.merged_dialogue_turns()


def _build_session_record(session: CallSession, anonymized_summary: Dict[str, Any]) -> Dict[str, Any]:
    dialogue_turns = session.merged_dialogue_turns()
    analytics = build_session_analytics(
        status=session.status,
        last_error=session.last_error,
        metadata=_build_redacted_metadata(session),
        anonymized_summary=anonymized_summary,
        dialogue_turns=dialogue_turns,
        transcript_turn_count=len(dialogue_turns),
    )
    return {
        "log_version": 3,
        "privacy_mode": "llm_anonymized_summary",
        "call_sid": session.call_sid,
        "stream_sid": session.stream_sid,
        "status": session.status,
        "created_at": session.created_at,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "duration_seconds": session.duration_seconds(),
        "termination_reason": session.termination_reason,
        "last_error": session.last_error,
        "metadata": _build_redacted_metadata(session),
        "config": {
            "voice": session.config.voice,
            "language": session.config.language,
            "temperature": session.config.temperature,
            "reasoning_effort": session.config.reasoning_effort,
        },
        "transcript_turn_count": len(dialogue_turns),
        "anonymized_summary": anonymized_summary,
        "analytics": analytics,
        "raw_transcript_persisted": False,
    }


def _build_redacted_metadata(session: CallSession) -> Dict[str, Any]:
    metadata = session.metadata or {}
    direction = str(metadata.get("direction") or "unknown")
    to_number = metadata.get("to_number")
    from_number = metadata.get("from_number")
    return {
        "direction": direction,
        "counterparty_label": _mask_counterparty(direction, to_number, from_number),
        "has_last_error": bool(session.last_error),
    }


def _mask_counterparty(direction: str, to_number: Any, from_number: Any) -> str:
    candidate = None
    if direction == "outbound":
        candidate = to_number
    elif direction == "inbound":
        candidate = from_number
    else:
        candidate = to_number or from_number

    digits = "".join(ch for ch in str(candidate or "") if ch.isdigit())
    if not digits:
        return "unknown"
    return f"***{digits[-4:]}"
