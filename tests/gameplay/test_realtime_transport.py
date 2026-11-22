import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from asgi_app import realtime
from models import RoomSettings
from services.reconnect_service import ReconnectService
from services.room_service import RoomService
from storage.room_repository import RoomRepository


class Socket:
    def __init__(self, token):
        self.headers = {"origin": "http://test", "host": "test"}
        self.token = token
        self.messages = asyncio.Queue()
        self.closed = None

    async def accept(self):
        pass

    async def receive_text(self):
        return self.token

    async def send_text(self, message):
        await self.messages.put(message)

    async def close(self, code):
        self.closed = code


class RealtimeTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_event_and_reconnect_resynchronise_without_room_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = RoomRepository(Path(directory) / "rooms.json")
            rooms = RoomService(repository)
            room = rooms.create_room("Host", "Room", RoomSettings(), is_private=False)
            token = ReconnectService(repository).issue(room.room_code, room.host_id)
            with patch("asgi_app.RoomRepository", return_value=repository):
                socket = Socket(token)
                task = asyncio.create_task(realtime(socket))
                self.assertEqual(await asyncio.wait_for(socket.messages.get(), 2), "sync")
                rooms.add_player(room, "Guest")
                self.assertEqual(await asyncio.wait_for(socket.messages.get(), 2), "sync")
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                rooms.update_max_score(room, 25)
                replacement = Socket(token)
                task = asyncio.create_task(realtime(replacement))
                self.assertEqual(await asyncio.wait_for(replacement.messages.get(), 2), "sync")
                self.assertEqual(repository.get_by_code(room.room_code).settings.max_score, 25)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

    async def test_invalid_token_and_cross_origin_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = RoomRepository(Path(directory) / "rooms.json")
            with patch("asgi_app.RoomRepository", return_value=repository):
                socket = Socket("invalid")
                await realtime(socket)
                self.assertEqual(await socket.messages.get(), "invalid")
                self.assertEqual(socket.closed, 1008)
                socket = Socket("invalid")
                socket.headers["origin"] = "https://elsewhere.example"
                await realtime(socket)
                self.assertEqual(socket.closed, 1008)
