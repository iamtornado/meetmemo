from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    model_used: Mapped[str] = mapped_column(String(100), nullable=False)
    ai_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ai_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_agenda: Mapped[str | None] = mapped_column(Text, nullable=True)
    additional_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    formal_minutes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    meeting = relationship("Meeting", back_populates="summary", lazy="selectin")
    attendees = relationship("SummaryAttendee", back_populates="summary", lazy="selectin", cascade="all, delete-orphan")
    key_points = relationship("SummaryKeyPoint", back_populates="summary", lazy="selectin", cascade="all, delete-orphan")
    decisions = relationship("SummaryDecision", back_populates="summary", lazy="selectin", cascade="all, delete-orphan")
    action_items = relationship("SummaryActionItem", back_populates="summary", lazy="selectin", cascade="all, delete-orphan")


class SummaryAttendee(Base):
    __tablename__ = "summary_attendees"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    summary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("summaries.id", ondelete="CASCADE"), nullable=False
    )
    speaker_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    summary = relationship("Summary", back_populates="attendees", lazy="selectin")


class SummaryKeyPoint(Base):
    __tablename__ = "summary_key_points"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    summary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("summaries.id", ondelete="CASCADE"), nullable=False
    )
    topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    importance: Mapped[int | None] = mapped_column(Integer, nullable=True)

    summary = relationship("Summary", back_populates="key_points", lazy="selectin")


class SummaryDecision(Base):
    __tablename__ = "summary_decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    summary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("summaries.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    made_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consensus: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    summary = relationship("Summary", back_populates="decisions", lazy="selectin")


class SummaryActionItem(Base):
    __tablename__ = "summary_action_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    summary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("summaries.id", ondelete="CASCADE"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")

    summary = relationship("Summary", back_populates="action_items", lazy="selectin")
