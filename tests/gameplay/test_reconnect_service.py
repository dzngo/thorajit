import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from models import RoomSettings
from services.reconnect_service import ReconnectService
from services.room_service import RoomService
from storage.room_repository import RoomRepository


class ReconnectServiceTests(unittest.TestCase):
    def test_token_rotation_expiry_and_removal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rooms.json"
            repository = RoomRepository(path)
            rooms = RoomService(repository)
            room = rooms.create_room("Host", "Test", RoomSettings(), is_private=False)
            player = rooms.add_player(room, "Guest")
            reconnect = ReconnectService(repository)
            token = reconnect.issue(room.room_code, player.player_id)
            self.assertNotIn(token, path.read_text())
            self.assertEqual(reconnect.resolve(token)[1].player_id, player.player_id)
            replacement = reconnect.issue(room.room_code, player.player_id)
            self.assertIsNone(reconnect.resolve(token))
            self.assertIsNone(reconnect.resolve("invalid"))
            def expire(latest):
                next(p for p in latest.players if p.player_id == player.player_id).reconnect_expires_at = (
                    datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
            repository.update(room.room_code, expire)
            self.assertIsNone(reconnect.resolve(replacement))
            replacement = reconnect.issue(room.room_code, player.player_id)
            rooms.remove_player(room, player.player_id)
            self.assertIsNone(reconnect.resolve(replacement))
            host_token = reconnect.issue(room.room_code, room.host_id)
            repository.delete(room.room_code)
            self.assertIsNone(reconnect.resolve(host_token))
