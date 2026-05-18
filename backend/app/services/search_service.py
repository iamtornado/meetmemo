from __future__ import annotations

import math

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meeting import Meeting
from app.models.transcript import Transcript, TranscriptSegment
from app.models.summary import Summary, SummaryKeyPoint, SummaryActionItem
from app.schemas.search import SearchResponse, SearchResultItem


class SearchService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def search(
        self,
        query: str,
        user_id: str,
        team_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SearchResponse:
        q = f"%{query}%"
        results = []
        seen_meetings = set()

        # 1. Search in transcript segments (primary)
        seg_query = (
            select(
                Meeting.id,
                Meeting.title,
                Meeting.date,
                Meeting.status,
                Meeting.team_id,
                Meeting.created_at,
                TranscriptSegment.text,
                text("'transcript' as match_type"),
            )
            .select_from(Meeting)
            .join(Transcript, Transcript.meeting_id == Meeting.id)
            .join(TranscriptSegment, TranscriptSegment.transcript_id == Transcript.id)
            .where(
                Meeting.created_by == user_id,
                TranscriptSegment.text.ilike(q),
            )
        )

        if team_id:
            seg_query = seg_query.where(Meeting.team_id == team_id)

        result = await self.session.execute(
            seg_query.order_by(Meeting.created_at.desc())
            .limit(page_size * 2)
        )
        for row in result:
            if row.id not in seen_meetings:
                seen_meetings.add(row.id)
                results.append(SearchResultItem(
                    meeting_id=row.id,
                    title=row.title,
                    date=row.date,
                    status=row.status,
                    team_id=row.team_id,
                    created_at=row.created_at,
                    matched_text=row.text[:200] + ("..." if len(row.text) > 200 else ""),
                    match_type="transcript",
                ))

        # 2. Search in summary fields
        if len(results) < page_size * 2:
            summary_query = (
                select(
                    Meeting.id,
                    Meeting.title,
                    Meeting.date,
                    Meeting.status,
                    Meeting.team_id,
                    Meeting.created_at,
                    func.coalesce(Summary.ai_title, "").label("matched_text"),
                    text("'summary' as match_type"),
                )
                .select_from(Meeting)
                .join(Summary, Summary.meeting_id == Meeting.id)
                .where(
                    Meeting.created_by == user_id,
                    or_(
                        Summary.ai_title.ilike(q),
                        Summary.next_agenda.ilike(q),
                        Summary.additional_notes.ilike(q),
                    ),
                    Meeting.id.notin_(seen_meetings),
                )
            )

            if team_id:
                summary_query = summary_query.where(Meeting.team_id == team_id)

            result = await self.session.execute(
                summary_query.order_by(Meeting.created_at.desc())
                .limit(page_size)
            )
            for row in result:
                seen_meetings.add(row.id)
                results.append(SearchResultItem(
                    meeting_id=row.id,
                    title=row.title,
                    date=row.date,
                    status=row.status,
                    team_id=row.team_id,
                    created_at=row.created_at,
                    matched_text=row.matched_text[:200],
                    match_type="summary",
                ))

        # 3. Search in meeting titles
        if len(results) < page_size * 2:
            title_query = (
                select(Meeting)
                .where(
                    Meeting.created_by == user_id,
                    Meeting.title.ilike(q),
                    Meeting.id.notin_(seen_meetings),
                )
                .order_by(Meeting.created_at.desc())
                .limit(page_size)
            )
            if team_id:
                title_query = title_query.where(Meeting.team_id == team_id)

            result = await self.session.execute(title_query)
            for m in result.scalars().all():
                results.append(SearchResultItem(
                    meeting_id=m.id,
                    title=m.title,
                    date=m.date,
                    status=m.status,
                    team_id=m.team_id,
                    created_at=m.created_at,
                    matched_text=m.title or "",
                    match_type="title",
                ))

        total = len(results)
        paged = results[(page - 1) * page_size : page * page_size]

        return SearchResponse(
            items=paged,
            total=total,
            page=page,
            page_size=page_size,
        )
