from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(100), nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    meeting = relationship("Meeting", back_populates="transcript", lazy="selectin")
    segments = relationship(
        "TranscriptSegment", back_populates="transcript", lazy="selectin",
        cascade="all, delete-orphan", order_by="TranscriptSegment.seq_number"
    )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False
    )
    seq_number: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    speaker_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    transcript = relationship("Transcript", back_populates="segments", lazy="selectin")
