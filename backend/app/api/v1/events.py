from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from app.api.deps import get_current_user
from app.models.user import User
from app.services.notification_service import notification_manager

router = APIRouter(tags=["events"])


@router.get("/events")
async def stream_events(user: User = Depends(get_current_user)):
    """SSE endpoint for real-time job progress updates."""

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()
        user_id = str(user.id)
        notification_manager.subscribe(user_id, queue)
        try:
            # Send initial connection event
            yield f"data: {json.dumps({'type': 'connected', 'user_id': user_id})}\n\n"
            while True:
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield f": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            notification_manager.unsubscribe(user_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
