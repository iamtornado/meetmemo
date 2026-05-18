from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class NotificationManager:
    """Manages SSE subscriptions for real-time job progress."""

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, user_id: str, queue: asyncio.Queue):
        if user_id not in self._subscribers:
            self._subscribers[user_id] = []
        self._subscribers[user_id].append(queue)
        logger.info(f"User {user_id} subscribed to events")

    def unsubscribe(self, user_id: str, queue: asyncio.Queue):
        if user_id in self._subscribers:
            self._subscribers[user_id] = [
                q for q in self._subscribers[user_id] if q is not queue
            ]
            if not self._subscribers[user_id]:
                del self._subscribers[user_id]

    def notify(self, user_id: str, event_type: str, data: dict[str, Any]):
        if user_id not in self._subscribers:
            return

        message = json.dumps({"type": event_type, **data})
        dead_queues = []
        for queue in self._subscribers[user_id]:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                dead_queues.append(queue)

        for q in dead_queues:
            self.unsubscribe(user_id, q)

    def notify_all(self, event_type: str, data: dict[str, Any]):
        for user_id in list(self._subscribers.keys()):
            self.notify(user_id, event_type, data)


notification_manager = NotificationManager()
