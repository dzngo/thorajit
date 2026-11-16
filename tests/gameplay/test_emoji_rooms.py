import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from models import Player, RoomSettings
from services.room_service import EmojiTakenError, PlayerNameTakenError, RoomNameTakenError, RoomService
from storage.room_repository import RoomRepository


class RoomEmojiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = RoomRepository(Path(self.tmp.name) / 'rooms.json')
        self.service = RoomService(self.repo)
        self.room = self.service.create_room('Host', 'Test', RoomSettings(), is_private=False, emoji='😀')

    def test_simultaneous_room_creation_does_not_duplicate_names(self):
        def create(index):
            try:
                return self.service.create_room(f'Host {index}', '   SAME Room  ', RoomSettings(),
                                                is_private=False, emoji='😀')
            except RoomNameTakenError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            created = list(pool.map(create, range(2)))
        self.assertEqual(sum(room is not None for room in created), 1)
        self.assertEqual(sum(room.name.casefold() == 'same room' for room in self.repo.list_rooms()), 1)
        with self.assertRaises(RoomNameTakenError):
            self.service.create_room('Another', 'same ROOM', RoomSettings(), is_private=False, emoji='🐸')

    def test_legacy_player_without_emoji_can_be_loaded(self):
        host = self.room.players[0].to_dict()
        host.pop('emoji')
        self.assertIsNone(Player.from_dict(host).emoji)

    def test_selected_emoji_persists_and_duplicate_is_rejected(self):
        self.service.add_player(self.room, 'Guest', emoji='🐸')
        self.assertEqual(self.repo.get_by_code(self.room.room_code).players[1].emoji, '🐸')
        with self.assertRaises(EmojiTakenError):
            self.service.add_player(self.room, 'Another', emoji='🐸')
        self.assertEqual(len(self.repo.get_by_code(self.room.room_code).players), 2)

    def test_leaving_releases_the_emoji_for_another_player(self):
        guest = self.service.add_player(self.room, 'Guest', emoji='🐸')
        self.service.remove_player(self.room, guest.player_id)
        replacement = self.service.add_player(self.room, 'New guest', emoji='🐸')
        saved = self.repo.get_by_code(self.room.room_code)
        self.assertEqual(replacement.emoji, '🐸')
        self.assertEqual([player.emoji for player in saved.players], ['😀', '🐸'])

    def test_concurrent_claims_do_not_share_an_emoji(self):
        rooms = [self.repo.get_by_code(self.room.room_code) for _ in range(2)]
        def join(index):
            try:
                self.service.add_player(rooms[index], f'Guest {index}', emoji='🐸')
                return 'joined'
            except EmojiTakenError:
                return 'taken'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(pool.map(join, range(2)), ['joined', 'taken'])
        self.assertEqual(len(self.repo.get_by_code(self.room.room_code).players), 2)

    def test_duplicate_name_does_not_reclaim_or_change_another_player(self):
        guest = self.service.add_player(self.room, 'Guest', emoji='🐸')
        with self.assertRaises(PlayerNameTakenError):
            self.service.add_player(self.room, ' guest ', emoji='🐱')
        saved = self.repo.get_by_code(self.room.room_code)
        self.assertEqual(len(saved.players), 2)
        self.assertEqual(saved.players[1].player_id, guest.player_id)
        self.assertEqual(saved.players[1].emoji, '🐸')

    def test_non_emoji_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.add_player(self.room, 'Guest', emoji='hello')


if __name__ == '__main__':
    unittest.main()
