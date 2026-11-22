"""File-system backed repository for persisting Room entities."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import Lock
from typing import Callable, Dict, List, Optional, TypeVar
import streamlit as st

from models import Room
from storage.room_notifications import RoomNotifications

T = TypeVar("T")


@st.cache_resource(show_spinner=False)  # type: ignore[arg-type]
def _shared_room_lock() -> Lock:
    return Lock()


@st.cache_resource(show_spinner=False)  # type: ignore[arg-type]
def _shared_room_notifications() -> RoomNotifications:
    return RoomNotifications()


class RoomStorageError(OSError):
    """Room data could not be read or written."""


class RoomNameExistsError(Exception):
    def __init__(self, room: Room) -> None:
        self.room = room
        super().__init__("A room with this name already exists.")


class RoomCodeExistsError(Exception):
    pass


class RoomRepository:
    """Very small JSON-based repository used during the early iterations."""

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        default_path = Path(__file__).resolve().parent / "rooms.json"
        self.storage_path = storage_path or default_path
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RoomStorageError("Room storage is unavailable.") from exc
        self._lock = _shared_room_lock()
        self.notifications = _shared_room_notifications()
        self.notification_key = str(self.storage_path.resolve())

    def list_rooms(self) -> List[Room]:
        with self._lock:
            return list(self._load().values())

    def get_by_code(self, room_code: str) -> Optional[Room]:
        with self._lock:
            return self._load().get(room_code.upper())

    def get_by_name(self, name: str) -> Optional[Room]:
        normalized = name.strip().casefold()
        with self._lock:
            for room in self._load().values():
                if room.name.strip().casefold() == normalized:
                    return room
        return None

    def create(self, room: Room) -> None:
        """Insert a room only if its name and code are still available."""
        with self._lock:
            rooms = self._load()
            existing = next((item for item in rooms.values()
                             if item.name.strip().casefold() == room.name.strip().casefold()), None)
            if existing is not None:
                raise RoomNameExistsError(existing)
            if room.room_code.upper() in rooms:
                raise RoomCodeExistsError()
            rooms[room.room_code.upper()] = room
            self._write(rooms)
            self.notifications.publish(self.notification_key, room.room_code)

    def save(self, room: Room) -> None:
        with self._lock:
            rooms = self._load()
            rooms[room.room_code.upper()] = room
            self._write(rooms)
            self.notifications.publish(self.notification_key, room.room_code)

    def update(self, room_code: str, operation: Callable[[Room], T]) -> tuple[Room, T]:
        """Apply a room mutation under the shared in-process lock."""
        with self._lock:
            rooms = self._load()
            room = rooms.get(room_code.upper())
            if room is None:
                raise KeyError(room_code)
            result = operation(room)
            rooms[room.room_code.upper()] = room
            self._write(rooms)
            self.notifications.publish(self.notification_key, room.room_code)
            return room, result

    def delete(self, room_code: str) -> None:
        with self._lock:
            rooms = self._load()
            key = room_code.upper()
            if key in rooms:
                del rooms[key]
                self._write(rooms)
                self.notifications.publish(self.notification_key, key)

    def _load(self) -> Dict[str, Room]:
        try:
            if not self.storage_path.exists():
                return {}
            with self.storage_path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise RoomStorageError("Room storage is unavailable.") from exc
        rooms: Dict[str, Room] = {}
        for payload in raw:
            room = Room.from_dict(payload)
            rooms[room.room_code.upper()] = room
        return rooms

    def _write(self, rooms: Dict[str, Room]) -> None:
        data = [room.to_dict() for room in rooms.values()]
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.storage_path.parent,
                                             prefix=f".{self.storage_path.name}.", suffix=".tmp",
                                             delete=False) as fh:
                temporary_path = Path(fh.name)
                json.dump(data, fh, indent=2)
            os.replace(temporary_path, self.storage_path)
        except OSError as exc:
            raise RoomStorageError("Room storage is unavailable.") from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
