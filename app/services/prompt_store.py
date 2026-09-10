from __future__ import annotations

import json
import logging
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class PromptVersion:
    id: str
    prompt: str
    opening_message: str
    created_at: str
    updated_by: str
    action: str
    source_version_id: Optional[str] = None


@dataclass(frozen=True)
class PromptStoreSnapshot:
    active_version_id: Optional[str]
    active_prompt: str
    active_opening_message: str
    versions: list[PromptVersion]


class PromptStore:
    def __init__(
        self,
        storage_path: Path,
        default_prompt: str,
        default_opening_message: str,
    ) -> None:
        self._storage_path = storage_path
        self._default_prompt = self._normalize_prompt(default_prompt)
        self._default_opening_message = self._normalize_prompt(default_opening_message)
        self._lock = threading.Lock()

    def get_active_prompt(self) -> str:
        return self.get_snapshot().active_prompt

    def get_active_opening_message(self) -> str:
        return self.get_snapshot().active_opening_message

    def get_snapshot(self) -> PromptStoreSnapshot:
        with self._lock:
            state = self._read_state_unlocked()

        versions = [PromptVersion(**item) for item in reversed(state["versions"])]
        active_version_id = state["active_version_id"]
        active_prompt = self._default_prompt
        active_opening_message = self._default_opening_message
        if active_version_id:
            matching_version = next(
                (version for version in versions if version.id == active_version_id),
                None,
            )
            if matching_version is not None:
                active_prompt = matching_version.prompt
                active_opening_message = matching_version.opening_message

        return PromptStoreSnapshot(
            active_version_id=active_version_id,
            active_prompt=active_prompt,
            active_opening_message=active_opening_message,
            versions=versions,
        )

    def save_prompt(
        self,
        prompt: str,
        *,
        opening_message: Optional[str] = None,
        updated_by: str,
        action: str = "save",
    ) -> PromptVersion:
        return self._append_version(
            prompt=prompt,
            opening_message=opening_message or self.get_active_opening_message(),
            updated_by=updated_by,
            action=action,
            source_version_id=None,
        )

    def reset_to_default(self, *, updated_by: str) -> PromptVersion:
        return self._append_version(
            prompt=self._default_prompt,
            opening_message=self._default_opening_message,
            updated_by=updated_by,
            action="reset_to_default",
            source_version_id=None,
        )

    def restore_version(self, version_id: str, *, updated_by: str) -> PromptVersion:
        with self._lock:
            state = self._read_state_unlocked()
            source_item = next(
                (item for item in state["versions"] if item["id"] == version_id),
                None,
            )
            if source_item is None:
                raise KeyError(f"Unknown prompt version: {version_id}")

            version = self._build_version(
                prompt=source_item["prompt"],
                opening_message=source_item.get("opening_message", self._default_opening_message),
                updated_by=updated_by,
                action="restore",
                source_version_id=source_item["id"],
            )
            state["active_version_id"] = version.id
            state["versions"].append(asdict(version))
            self._write_state_unlocked(state)
            return version

    def _append_version(
        self,
        *,
        prompt: str,
        opening_message: str,
        updated_by: str,
        action: str,
        source_version_id: Optional[str],
    ) -> PromptVersion:
        with self._lock:
            state = self._read_state_unlocked()
            version = self._build_version(
                prompt=prompt,
                opening_message=opening_message,
                updated_by=updated_by,
                action=action,
                source_version_id=source_version_id,
            )
            state["active_version_id"] = version.id
            state["versions"].append(asdict(version))
            self._write_state_unlocked(state)
            return version

    def _build_version(
        self,
        *,
        prompt: str,
        opening_message: str,
        updated_by: str,
        action: str,
        source_version_id: Optional[str],
    ) -> PromptVersion:
        cleaned_prompt = self._normalize_prompt(prompt)
        cleaned_opening_message = self._normalize_prompt(opening_message)
        if not cleaned_prompt:
            raise ValueError("Prompt cannot be empty.")
        if not cleaned_opening_message:
            raise ValueError("Opening message cannot be empty.")
        if len(cleaned_prompt) > 50000:
            raise ValueError("Prompt is too long. Keep it under 50,000 characters.")
        if len(cleaned_opening_message) > 5000:
            raise ValueError("Opening message is too long. Keep it under 5,000 characters.")

        return PromptVersion(
            id=uuid.uuid4().hex,
            prompt=cleaned_prompt,
            opening_message=cleaned_opening_message,
            created_at=_utc_now_iso(),
            updated_by=updated_by,
            action=action,
            source_version_id=source_version_id,
        )

    def _read_state_unlocked(self) -> dict[str, Any]:
        if not self._storage_path.exists():
            return {"active_version_id": None, "versions": []}

        try:
            payload = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except (OSError, JSONDecodeError) as exc:
            logger.warning("Failed to read prompt store at %s: %s", self._storage_path, exc)
            return {"active_version_id": None, "versions": []}

        versions = payload.get("versions")
        if not isinstance(versions, list):
            logger.warning("Prompt store at %s is missing a valid versions list", self._storage_path)
            return {"active_version_id": None, "versions": []}

        active_version_id = payload.get("active_version_id")
        if active_version_id is not None and not isinstance(active_version_id, str):
            active_version_id = None

        normalized_versions = []
        for item in versions:
            if not isinstance(item, dict):
                continue
            if not all(
                isinstance(item.get(field), str)
                for field in ("id", "prompt", "created_at", "updated_by", "action")
            ):
                continue
            source_version_id = item.get("source_version_id")
            if source_version_id is not None and not isinstance(source_version_id, str):
                source_version_id = None
            opening_message = item.get("opening_message")
            if not isinstance(opening_message, str):
                opening_message = self._default_opening_message
            normalized_versions.append(
                {
                    "id": item["id"],
                    "prompt": self._normalize_prompt(item["prompt"]),
                    "opening_message": self._normalize_prompt(opening_message),
                    "created_at": item["created_at"],
                    "updated_by": item["updated_by"],
                    "action": item["action"],
                    "source_version_id": source_version_id,
                }
            )

        return {
            "active_version_id": active_version_id,
            "versions": normalized_versions,
        }

    def _write_state_unlocked(self, state: dict[str, Any]) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _normalize_prompt(prompt: str) -> str:
        return "\n".join(line.rstrip() for line in str(prompt).splitlines()).strip()


prompt_store = PromptStore(
    storage_path=Path(settings.prompt_store_path),
    default_prompt=settings.default_system_message,
    default_opening_message=settings.default_opening_message,
)
