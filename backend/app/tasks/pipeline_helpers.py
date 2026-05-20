from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.database import sync_session_factory
from app.models.meeting import Meeting
from app.services.notification_service import notification_manager

logger = logging.getLogger(__name__)

ROLE_PRIORITY = {"admin": 3, "editor": 2, "member": 1, "viewer": 1}


def get_meeting_owner_id(meeting_id: str) -> str | None:
    with sync_session_factory() as session:
        meeting = session.query(Meeting).filter(
            Meeting.id == uuid.UUID(meeting_id)
        ).first()
        return str(meeting.created_by) if meeting else None


def notify_meeting(meeting_id: str, event_type: str, data: dict | None = None) -> None:
    user_id = get_meeting_owner_id(meeting_id)
    if not user_id:
        return
    payload = {"meeting_id": meeting_id, **(data or {})}
    notification_manager.notify(user_id, event_type, payload)


def mark_meeting_processing(meeting_id: str) -> None:
    from sqlalchemy.orm import selectinload
    from app.models.summary import Summary
    from app.models.transcript import Transcript

    with sync_session_factory() as session:
        meeting = (
            session.query(Meeting)
            .options(selectinload(Meeting.transcript), selectinload(Meeting.summary))
            .filter(Meeting.id == uuid.UUID(meeting_id))
            .first()
        )
        if not meeting:
            return

        if meeting.transcript:
            session.delete(meeting.transcript)
        if meeting.summary:
            session.delete(meeting.summary)

        meeting.status = "processing"
        meeting.error_message = None
        meeting.processing_started_at = datetime.now(timezone.utc)
        meeting.processing_completed_at = None
        session.commit()
    notify_meeting(meeting_id, "pipeline_started", {"status": "processing"})


def mark_meeting_failed(meeting_id: str, error: str, step: str | None = None) -> None:
    message = f"{step}: {error}" if step else error
    if len(message) > 2000:
        message = message[:2000] + "..."

    with sync_session_factory() as session:
        meeting = session.query(Meeting).filter(
            Meeting.id == uuid.UUID(meeting_id)
        ).first()
        if not meeting:
            return
        meeting.status = "failed"
        meeting.error_message = message
        meeting.processing_completed_at = datetime.now(timezone.utc)
        session.commit()

    notify_meeting(
        meeting_id,
        "pipeline_failed",
        {"status": "failed", "error": message, "step": step},
    )
    logger.error(f"Pipeline failed for meeting {meeting_id}: {message}")


def check_remote_ml_services() -> list[str]:
    """Verify remote ASR/diarize endpoints before starting a pipeline."""
    errors: list[str] = []
    timeout = httpx.Timeout(10.0, connect=5.0)

    if settings.ASR_PROVIDER == "sensevoice" and settings.SENSEVOICE_MODE == "remote":
        url = (settings.SENSEVOICE_API_URL or "").rstrip("/")
        if not url:
            errors.append("SENSEVOICE_API_URL is not configured")
        else:
            try:
                r = httpx.get(f"{url}/health", timeout=timeout)
                r.raise_for_status()
            except Exception as e:
                errors.append(f"Remote ASR unreachable ({url}): {e}")

    if settings.DIARIZE_PROVIDER == "remote":
        url = (settings.DIARIZE_API_URL or "").rstrip("/")
        if not url:
            errors.append("DIARIZE_API_URL is not configured")
        else:
            try:
                r = httpx.get(f"{url}/health", timeout=timeout)
                r.raise_for_status()
            except Exception as e:
                errors.append(f"Remote diarizer unreachable ({url}): {e}")

    return errors
