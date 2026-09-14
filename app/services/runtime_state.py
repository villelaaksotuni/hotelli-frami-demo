from datetime import datetime, timezone
from typing import Dict, Optional

from app.models.call import CallConfig, CallSession


class InMemoryCallSessionStore:
    def __init__(self) -> None:
        self._sessions_by_call_sid: Dict[str, CallSession] = {}
        self._sessions_by_stream_sid: Dict[str, CallSession] = {}

    def create_outbound_session(
        self,
        call_sid: str,
        config: CallConfig,
        metadata: Optional[dict] = None,
    ) -> CallSession:
        session = CallSession(call_sid=call_sid, config=config)
        session.add_metadata(metadata or {})
        self._sessions_by_call_sid[call_sid] = session
        return session

    def get_or_create_session(
        self,
        call_sid: Optional[str] = None,
        stream_sid: Optional[str] = None,
        config: Optional[CallConfig] = None,
        metadata: Optional[dict] = None,
    ) -> CallSession:
        session = None
        if call_sid:
            session = self._sessions_by_call_sid.get(call_sid)
        if session is None and stream_sid:
            session = self._sessions_by_stream_sid.get(stream_sid)
        if session is None:
            session = CallSession(call_sid=call_sid, config=config or CallConfig())
            if call_sid:
                self._sessions_by_call_sid[call_sid] = session

        if config is not None:
            session.config = config
        session.add_metadata(metadata or {})

        if call_sid and session.call_sid != call_sid:
            session.call_sid = call_sid
            self._sessions_by_call_sid[call_sid] = session

        if stream_sid:
            session.bind_stream(stream_sid)
            self._sessions_by_stream_sid[stream_sid] = session

        return session

    def get_by_call_sid(self, call_sid: Optional[str]) -> Optional[CallSession]:
        if not call_sid:
            return None
        return self._sessions_by_call_sid.get(call_sid)

    def get_by_stream_sid(self, stream_sid: Optional[str]) -> Optional[CallSession]:
        if not stream_sid:
            return None
        return self._sessions_by_stream_sid.get(stream_sid)

    def add_session_metadata(
        self,
        *,
        call_sid: Optional[str] = None,
        stream_sid: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[CallSession]:
        session = self.get_by_stream_sid(stream_sid) or self.get_by_call_sid(call_sid)
        if session is None:
            return None
        session.add_metadata(metadata or {})
        return session

    def append_transcript(
        self,
        stream_sid: str,
        speaker: str,
        text: str,
        source: str = "realtime",
    ) -> Optional[CallSession]:
        session = self.get_by_stream_sid(stream_sid)
        if session is None:
            return None
        session.append_transcript(speaker=speaker, text=text, source=source)
        return session

    def mark_session_error(
        self,
        *,
        call_sid: Optional[str] = None,
        stream_sid: Optional[str] = None,
        error: str,
    ) -> Optional[CallSession]:
        session = self.get_by_stream_sid(stream_sid) or self.get_by_call_sid(call_sid)
        if session is None:
            return None
        session.mark_error(error)
        return session

    def finish_session(
        self,
        stream_sid: Optional[str],
        *,
        call_sid: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Optional[CallSession]:
        # call_sid fallback (CR-03): a call that fails before Twilio's
        # "start" event never has a stream_sid, so stream_sid-only lookup
        # would silently no-op and leak the session's concurrent-call slot.
        session = self.get_by_stream_sid(stream_sid) or self.get_by_call_sid(call_sid)
        if session is None:
            return None
        session.finish(reason=reason)
        return session

    def remove_session(self, session: CallSession) -> None:
        if session.call_sid:
            self._sessions_by_call_sid.pop(session.call_sid, None)
        if session.stream_sid:
            self._sessions_by_stream_sid.pop(session.stream_sid, None)

    def active_call_count(self) -> int:
        return len(self._sessions_by_call_sid)

    def reap_stale_sessions(self, max_age_seconds: float) -> int:
        # WR-01: only reap sessions that never bound a stream (stream_sid is
        # still None). A session that did bind a stream is a genuinely
        # in-progress call whose normal termination flow (handle_media_stream's
        # finally block) is responsible for removing it; silently dropping it
        # here would understate active_call_count() for a call that may still
        # be live and billable, e.g. if the Twilio REST "completed" update
        # failed silently on the duration-cap cutoff path.
        reaped_count = 0
        now = datetime.now(timezone.utc)
        for session in list(self._sessions_by_call_sid.values()):
            if session.stream_sid is not None:
                continue
            try:
                created_at = datetime.fromisoformat(session.created_at)
            except (TypeError, ValueError):
                continue
            age_seconds = (now - created_at).total_seconds()
            if age_seconds > max_age_seconds:
                self.remove_session(session)
                reaped_count += 1
        return reaped_count


session_store = InMemoryCallSessionStore()
