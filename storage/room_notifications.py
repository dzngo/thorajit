"""In-process, payload-free notifications for committed room changes.

Consumers must reload the room after waking. Sequence numbers are only valid
for the lifetime of this process and are scoped to a repository and room.
"""

from __future__ import annotations

from threading import Condition
import asyncio


class RoomNotifications:
    def __init__(self) -> None:
        self._condition = Condition()
        self._versions: dict[tuple[str, str], int] = {}
        self._subscribers: dict[tuple[str, str], set[tuple[asyncio.AbstractEventLoop, asyncio.Event]]] = {}

    def version(self, repository: str, room_code: str) -> int:
        with self._condition:
            return self._versions.get((repository, room_code.upper()), 0)

    def publish(self, repository: str, room_code: str) -> None:
        key = (repository, room_code.upper())
        with self._condition:
            self._versions[key] = self._versions.get(key, 0) + 1
            self._condition.notify_all()
            for loop, event in tuple(self._subscribers.get(key, ())):
                try:
                    loop.call_soon_threadsafe(event.set)
                except RuntimeError:
                    pass  # The event loop has already shut down.

    def subscribe(self, repository: str, room_code: str):
        key = (repository, room_code.upper())
        subscriber = (asyncio.get_running_loop(), asyncio.Event())
        with self._condition:
            self._subscribers.setdefault(key, set()).add(subscriber)
        return subscriber

    def unsubscribe(self, repository: str, room_code: str, subscriber) -> None:
        key = (repository, room_code.upper())
        with self._condition:
            subscribers = self._subscribers.get(key)
            if subscribers is not None:
                subscribers.discard(subscriber)
                if not subscribers:
                    del self._subscribers[key]

    def wait_for_change(self, repository: str, room_code: str, version: int,
                        timeout: float | None = None) -> int:
        key = (repository, room_code.upper())
        with self._condition:
            self._condition.wait_for(lambda: self._versions.get(key, 0) != version, timeout)
            return self._versions.get(key, 0)
