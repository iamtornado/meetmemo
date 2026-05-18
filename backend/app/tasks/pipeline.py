from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from celery import chain
from sqlalchemy.orm import Session

from app.database import sync_session_factory
from app.models.meeting import Meeting
from app.models.summary import (
    Summary,
    SummaryAttendee,
    SummaryKeyPoint,
    SummaryDecision,
    SummaryActionItem,
)
from app.models.transcript import Transcript, TranscriptSegment
from app.tasks.celery_app import celery_app
from app.tasks.audio_preprocess import audio_preprocess
from app.tasks.transcribe import transcribe
from app.tasks.diarize import diarize
from app.tasks.summarize import summarize
from app.config import settings
from app.services.notification_service import notification_manager
from app.utils.audio import get_audio_duration

logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def run_meeting_pipeline(
    self,
    meeting_id: str,
    whisper_model: str | None = None,
    run_diarize: bool = True,
    run_summarize: bool = True,
):
    """Orchestrate the full meeting processing pipeline."""
    logger.info(f"Starting pipeline for meeting {meeting_id}")

    # Get meeting audio path using sync session (avoids async loop conflicts)
    with sync_session_factory() as session:
        meeting = session.query(Meeting).filter(Meeting.id == uuid.UUID(meeting_id)).first()
        if not meeting:
            raise ValueError(f"Meeting {meeting_id} not found")
        meeting.status = "processing"
        meeting.processing_started_at = datetime.now(timezone.utc)
        session.flush()
        session.commit()
        audio_path = meeting.audio_path
    notification_manager.notify(meeting_id, "pipeline_started", {"meeting_id": meeting_id})

    # Build task chain
    steps = [
        audio_preprocess.s(meeting_id, audio_path),
        transcribe.s(),
    ]

    if run_diarize:
        steps.append(diarize.s())

    if run_summarize:
        steps.append(summarize.s())

    # Add store step at the end
    steps.append(store_results.s())

    workflow = chain(*steps)
    workflow.apply_async()


@celery_app.task(bind=True)
def run_summarization(self, meeting_id: str):
    """Re-run only the summarization step (summarize + store_results)."""
    from app.models.transcript import Transcript

    with sync_session_factory() as session:
        transcript = session.query(Transcript).filter(
            Transcript.meeting_id == uuid.UUID(meeting_id)
        ).first()
        if not transcript:
            raise ValueError(f"No transcript found for meeting {meeting_id}")
        segments = [
            {
                "start": s.start_time,
                "end": s.end_time,
                "text": s.text,
                "speaker_id": s.speaker_id,
            }
            for s in transcript.segments
        ]

    # Chain summarize → store_results so the result gets persisted
    workflow = chain(
        summarize.s({"meeting_id": meeting_id, "segments": segments}),
        store_results.s(),
    )
    workflow.apply_async()


@celery_app.task(bind=True)
def store_results(self, pipeline_result: dict) -> dict:
    """Store pipeline results (transcript + summary) to database."""
    meeting_id = pipeline_result.get("meeting_id")
    if not meeting_id:
        raise ValueError("Missing meeting_id in pipeline result")

    with sync_session_factory() as session:
        meeting = session.query(Meeting).filter(Meeting.id == uuid.UUID(meeting_id)).first()
        if not meeting:
            raise ValueError(f"Meeting {meeting_id} not found")

        # Store transcript
        segments = pipeline_result.get("segments", [])
        if segments:
            transcript = Transcript(
                meeting_id=meeting.id,
                language=pipeline_result.get("language", "unknown"),
                model_used=pipeline_result.get("model_used", "unknown"),
                word_count=pipeline_result.get("word_count", 0),
            )
            session.add(transcript)
            session.flush()

            for i, seg in enumerate(segments):
                tseg = TranscriptSegment(
                    transcript_id=transcript.id,
                    seq_number=i,
                    speaker_id=seg.get("speaker_id"),
                    speaker_name=None,
                    start_time=seg.get("start", 0),
                    end_time=seg.get("end", 0),
                    text=seg.get("text", ""),
                    confidence=seg.get("confidence"),
                )
                session.add(tseg)

        # Store summary
        summary_data = pipeline_result.get("summary")
        if summary_data:
            summary = Summary(
                meeting_id=meeting.id,
                model_used=f"llm/{pipeline_result.get('summary_model', settings.LLM_MODEL)}",
                ai_title=summary_data.get("title"),
                ai_date=(
                    datetime.fromisoformat(summary_data["date"])
                    if summary_data.get("date")
                    else None
                ),
                next_agenda=summary_data.get("next_agenda"),
                additional_notes=summary_data.get("additional_notes"),
            )
            session.add(summary)
            session.flush()

            # Attendees
            for a in summary_data.get("attendees", []):
                session.add(SummaryAttendee(
                    summary_id=summary.id,
                    name=a.get("name", "Unknown"),
                    is_guest=a.get("is_guest", False),
                ))

            # Key points
            for kp in summary_data.get("key_points", []):
                session.add(SummaryKeyPoint(
                    summary_id=summary.id,
                    topic=kp.get("topic"),
                    description=kp.get("description", ""),
                    importance=kp.get("importance"),
                ))

            # Decisions
            for d in summary_data.get("decisions", []):
                session.add(SummaryDecision(
                    summary_id=summary.id,
                    description=d.get("description", ""),
                    made_by=d.get("made_by"),
                    consensus=d.get("consensus", True),
                ))

            # Action items
            for ai in summary_data.get("action_items", []):
                session.add(SummaryActionItem(
                    summary_id=summary.id,
                    description=ai.get("description", ""),
                    assignee=ai.get("assignee"),
                    due_date=(
                        datetime.fromisoformat(ai["due_date"])
                        if ai.get("due_date")
                        else None
                    ),
                    status=ai.get("status", "pending"),
                ))

        # Update meeting status
        meeting.status = "completed"
        meeting.processing_completed_at = datetime.now(timezone.utc)

        # Update duration if available
        if pipeline_result.get("duration"):
            meeting.duration_seconds = int(pipeline_result["duration"])

        session.commit()

    # Notify via SSE
    notification_manager.notify(
        meeting_id,
        "pipeline_completed",
        {"meeting_id": meeting_id, "status": "completed"},
    )

    logger.info(f"Pipeline results stored for meeting {meeting_id}")
    return {"meeting_id": meeting_id, "status": "completed"}
