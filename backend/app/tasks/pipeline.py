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
from app.tasks.pipeline_helpers import (
    check_remote_ml_services,
    mark_meeting_failed,
    mark_meeting_processing,
    notify_meeting,
)
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

    remote_errors = check_remote_ml_services()
    if remote_errors:
        mark_meeting_failed(meeting_id, "; ".join(remote_errors), step="preflight")
        return {"meeting_id": meeting_id, "status": "failed"}

    # Get meeting audio path using sync session (avoids async loop conflicts)
    with sync_session_factory() as session:
        meeting = session.query(Meeting).filter(Meeting.id == uuid.UUID(meeting_id)).first()
        if not meeting:
            raise ValueError(f"Meeting {meeting_id} not found")
        audio_path = meeting.audio_path
        already_processing = meeting.status == "processing"

    if not already_processing:
        mark_meeting_processing(meeting_id)

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
    workflow.apply_async(link_error=on_pipeline_error.s(meeting_id))


def _meeting_id_from_errback_request(request) -> str:
    """Resolve meeting_id from Celery errback request (signature is request, exc, traceback)."""
    if request.args:
        first = request.args[0]
        if isinstance(first, str) and len(first) >= 32:
            return first
        if isinstance(first, dict) and first.get("meeting_id"):
            return str(first["meeting_id"])
    kwargs = getattr(request, "kwargs", None) or {}
    if kwargs.get("meeting_id"):
        return str(kwargs["meeting_id"])
    raise ValueError("Cannot resolve meeting_id from errback request")


@celery_app.task
def on_pipeline_error(request, exc, traceback):
    """Celery errback: mark meeting failed when any pipeline step fails."""
    try:
        meeting_id = _meeting_id_from_errback_request(request)
    except ValueError:
        logger.exception("Pipeline errback could not resolve meeting_id")
        return
    step = getattr(request, "task", None) or getattr(request, "name", None) or "pipeline"
    mark_meeting_failed(meeting_id, str(exc), step=step)


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

    # Chain summarize → store_results (summary only — do not rewrite transcript rows)
    workflow = chain(
        summarize.s(
            {
                "meeting_id": meeting_id,
                "segments": segments,
                "summary_only": True,
            }
        ),
        store_results.s(),
    )
    workflow.apply_async()


def _replace_transcript_segments(
    session: Session,
    transcript: Transcript,
    segments: list[dict],
    *,
    language: str | None,
    model_used: str | None,
    word_count: int,
) -> None:
    """Replace all segments on an existing transcript row."""
    for seg in list(transcript.segments):
        session.delete(seg)
    session.flush()

    if language:
        transcript.language = language
    if model_used:
        transcript.model_used = model_used
    transcript.word_count = word_count

    for i, seg in enumerate(segments):
        session.add(
            TranscriptSegment(
                transcript_id=transcript.id,
                seq_number=i,
                speaker_id=seg.get("speaker_id"),
                speaker_name=None,
                start_time=seg.get("start", 0),
                end_time=seg.get("end", 0),
                text=seg.get("text", ""),
                confidence=seg.get("confidence"),
            )
        )


def _populate_summary_children(session: Session, summary: Summary, summary_data: dict) -> None:
    for a in list(summary.attendees):
        session.delete(a)
    for kp in list(summary.key_points):
        session.delete(kp)
    for d in list(summary.decisions):
        session.delete(d)
    for ai in list(summary.action_items):
        session.delete(ai)
    session.flush()

    for a in summary_data.get("attendees", []):
        name = a.get("name", "Unknown")
        speaker_id = a.get("speaker_id")
        if not speaker_id and isinstance(name, str) and name.startswith("SPEAKER_"):
            speaker_id = name
        session.add(
            SummaryAttendee(
                summary_id=summary.id,
                speaker_id=speaker_id,
                name=name,
                is_guest=a.get("is_guest", False),
            )
        )
    for kp in summary_data.get("key_points", []):
        session.add(
            SummaryKeyPoint(
                summary_id=summary.id,
                topic=kp.get("topic"),
                description=kp.get("description", ""),
                importance=kp.get("importance"),
            )
        )
    for d in summary_data.get("decisions", []):
        session.add(
            SummaryDecision(
                summary_id=summary.id,
                description=d.get("description", ""),
                made_by=d.get("made_by"),
                consensus=d.get("consensus", True),
            )
        )
    for ai in summary_data.get("action_items", []):
        session.add(
            SummaryActionItem(
                summary_id=summary.id,
                description=ai.get("description", ""),
                assignee=ai.get("assignee"),
                due_date=(
                    datetime.fromisoformat(ai["due_date"]) if ai.get("due_date") else None
                ),
                status=ai.get("status", "pending"),
            )
        )


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

        segments = pipeline_result.get("segments", [])
        if segments and not pipeline_result.get("summary_only"):
            existing = (
                session.query(Transcript).filter(Transcript.meeting_id == meeting.id).first()
            )
            if existing:
                _replace_transcript_segments(
                    session,
                    existing,
                    segments,
                    language=pipeline_result.get("language"),
                    model_used=pipeline_result.get("model_used"),
                    word_count=pipeline_result.get("word_count", 0),
                )
            else:
                transcript = Transcript(
                    meeting_id=meeting.id,
                    language=pipeline_result.get("language", "unknown"),
                    model_used=pipeline_result.get("model_used", "unknown"),
                    word_count=pipeline_result.get("word_count", 0),
                )
                session.add(transcript)
                session.flush()
                _replace_transcript_segments(
                    session,
                    transcript,
                    segments,
                    language=pipeline_result.get("language"),
                    model_used=pipeline_result.get("model_used"),
                    word_count=pipeline_result.get("word_count", 0),
                )

        summary_data = pipeline_result.get("summary")
        if summary_data:
            model_used = f"llm/{pipeline_result.get('summary_model', settings.LLM_MODEL)}"
            ai_date = (
                datetime.fromisoformat(summary_data["date"])
                if summary_data.get("date")
                else None
            )
            existing_summary = (
                session.query(Summary).filter(Summary.meeting_id == meeting.id).first()
            )
            if existing_summary:
                existing_summary.model_used = model_used
                existing_summary.ai_title = summary_data.get("title")
                existing_summary.ai_date = ai_date
                existing_summary.next_agenda = summary_data.get("next_agenda")
                existing_summary.additional_notes = summary_data.get("additional_notes")
                existing_summary.updated_at = datetime.now(timezone.utc)
                _populate_summary_children(session, existing_summary, summary_data)
            else:
                summary = Summary(
                    meeting_id=meeting.id,
                    model_used=model_used,
                    ai_title=summary_data.get("title"),
                    ai_date=ai_date,
                    next_agenda=summary_data.get("next_agenda"),
                    additional_notes=summary_data.get("additional_notes"),
                )
                session.add(summary)
                session.flush()
                _populate_summary_children(session, summary, summary_data)

        meeting.status = "completed"
        meeting.processing_completed_at = datetime.now(timezone.utc)

        if pipeline_result.get("duration"):
            meeting.duration_seconds = int(pipeline_result["duration"])

        session.commit()

    notify_meeting(meeting_id, "pipeline_completed", {"status": "completed"})

    logger.info(f"Pipeline results stored for meeting {meeting_id}")
    return {"meeting_id": meeting_id, "status": "completed"}
