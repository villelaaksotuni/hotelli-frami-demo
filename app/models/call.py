from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from app.config.settings import settings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


@dataclass
class CallConfig:
    system_message: str = settings.default_system_message
    opening_message: str = settings.default_opening_message
    voice: str = settings.default_voice
    language: str = settings.default_language
    temperature: float = settings.default_temperature
    reasoning_effort: str = settings.default_reasoning_effort
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConversationMessage(TypedDict):
    speaker: str
    text: str


ConversationLog = List[ConversationMessage]


@dataclass
class TranscriptEntry:
    speaker: str
    text: str
    timestamp: str = field(default_factory=utc_now_iso)
    source: str = "realtime"


@dataclass
class CallSession:
    call_sid: Optional[str] = None
    stream_sid: Optional[str] = None
    config: CallConfig = field(default_factory=CallConfig)
    metadata: Dict[str, Any] = field(default_factory=dict)
    transcript_entries: List[TranscriptEntry] = field(default_factory=list)
    status: str = "created"
    created_at: str = field(default_factory=utc_now_iso)
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    termination_reason: Optional[str] = None
    last_error: Optional[str] = None

    def bind_stream(self, stream_sid: str) -> None:
        self.stream_sid = stream_sid
        if self.started_at is None:
            self.started_at = utc_now_iso()
        self.status = "in_progress"

    def finish(self, reason: Optional[str] = None) -> None:
        if self.ended_at is None:
            self.ended_at = utc_now_iso()
        self.status = "completed"
        if reason:
            self.termination_reason = reason

    def mark_error(self, error: str) -> None:
        self.last_error = error
        self.add_metadata({"last_error": error})

    def add_metadata(self, values: Dict[str, Any]) -> None:
        self.metadata.update({key: value for key, value in values.items() if value is not None})

    def append_transcript(self, speaker: str, text: str, source: str = "realtime") -> None:
        cleaned_text = text.strip()
        if not cleaned_text:
            return
        self.transcript_entries.append(
            TranscriptEntry(speaker=speaker, text=cleaned_text, source=source)
        )

    def merged_dialogue_turns(self) -> ConversationLog:
        dialogue_turns: ConversationLog = []
        for entry in self.transcript_entries:
            if not dialogue_turns or dialogue_turns[-1]["speaker"] != entry.speaker:
                dialogue_turns.append({"speaker": entry.speaker, "text": entry.text})
            else:
                dialogue_turns[-1]["text"] += "\n" + entry.text
        return dialogue_turns

    def duration_seconds(self) -> Optional[float]:
        if not self.started_at or not self.ended_at:
            return None
        started_at = datetime.fromisoformat(self.started_at)
        ended_at = datetime.fromisoformat(self.ended_at)
        return round((ended_at - started_at).total_seconds(), 3)
