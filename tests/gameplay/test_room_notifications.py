import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from models import RoomSettings
from services.room_service import RoomService
from storage.room_repository import RoomRepository, RoomStorageError


class RoomNotificationTests(unittest.TestCase):
    def test_committed_changes_wake_subscribers_and_reload_latest_state(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = RoomRepository(Path(directory) / "rooms.json")
            service = RoomService(repository)
            room = service.create_room("Host", "Test", RoomSettings(), is_private=False)
            notifications = repository.notifications
            key = repository.notification_key
            initial = notifications.version(key, room.room_code)
            received = []
            thread = threading.Thread(target=lambda: received.append(
                notifications.wait_for_change(key, room.room_code, initial, timeout=2)))
            thread.start()
            service.add_player(room, "Guest")
            thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertGreater(received[0], initial)
            self.assertEqual(len(repository.get_by_code(room.room_code).players), 2)
            # A subscriber that missed an event can still detect it immediately.
            self.assertEqual(notifications.wait_for_change(key, room.room_code, initial, 0), received[0])
            repository.delete(room.room_code)
            self.assertGreater(notifications.version(key, room.room_code), received[0])
            self.assertIsNone(repository.get_by_code(room.room_code))

    def test_failed_write_and_other_rooms_do_not_notify(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = RoomRepository(Path(directory) / "rooms.json")
            room = RoomService(repository).create_room("Host", "Test", RoomSettings(), is_private=False)
            notifications = repository.notifications
            key = repository.notification_key
            version = notifications.version(key, room.room_code)
            with patch.object(repository, "_write", side_effect=RoomStorageError("failed")):
                with self.assertRaises(RoomStorageError):
                    repository.save(room)
            self.assertEqual(notifications.version(key, room.room_code), version)
            self.assertEqual(notifications.wait_for_change(key, "OTHER", 0, 0), 0)


if __name__ == "__main__":
    unittest.main()
