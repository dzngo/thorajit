import copy
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from models import RoomSettings
from services.game_service import GameService, GameStateConflictError
from services.room_service import RoomAlreadyStartedError, RoomService, RoomSettingsConflictError
from storage.room_repository import RoomRepository


class ConcurrentGameStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = RoomRepository(Path(self.tmp.name) / 'rooms.json')
        self.rooms = RoomService(self.repo)
        self.game = GameService(self.rooms)
        room = self.rooms.create_room('Host', 'Test', RoomSettings(), is_private=False, emoji='😀')
        self.rooms.add_player(room, 'Guest', emoji='🐸')
        self.game.start_game(room)
        self.code = room.room_code

    def test_simultaneous_reveal_readiness_advances_once(self):
        room = self.repo.get_by_code(self.code)
        state = copy.deepcopy(room.game_state)
        state.update(phase='reveal', round_summary={'winners': [], 'points': 1})
        self.game.set_state(room, state)
        snapshots = [self.repo.get_by_code(self.code) for _ in room.players]
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda pair: self.game.mark_reveal_ready(pair[0], pair[1].player_id),
                          zip(snapshots, room.players)))
        latest = self.repo.get_by_code(self.code)
        self.assertEqual(latest.game_state['round'], 2)
        self.assertEqual(latest.game_state['phase'], 'theme_selection')
        self.assertEqual(latest.game_state['reveal_ready'], [])
        with self.assertRaises(GameStateConflictError):
            self.game.mark_reveal_ready(snapshots[0], room.players[0].player_id)

    def test_unread_final_reveal_survives_return_to_lobby_and_new_game(self):
        room = self.repo.get_by_code(self.code)
        state = copy.deepcopy(room.game_state)
        state.update(phase='reveal', round_summary={'winners': [room.host_id], 'points': 1})
        self.game.set_state(room, state)
        guest = next(player for player in room.players if player.player_id != room.host_id)
        self.game.mark_reveal_ready(room, room.host_id)
        held = copy.deepcopy(room.game_state['pending_reveals'][guest.player_id])
        self.assertEqual(room.game_state['phase'], 'results')
        self.game.end_game(room)
        self.assertFalse(room.started)
        self.assertEqual(room.game_state['pending_reveals'][guest.player_id], held)
        self.game.start_game(room)
        self.game.mark_reveal_ready(room, guest.player_id, held)
        self.assertEqual(room.game_state['phase'], 'theme_selection')
        self.assertNotIn(guest.player_id, room.game_state['pending_reveals'])

    def test_non_host_storyteller_advances_and_late_host_keeps_reveal(self):
        room = self.repo.get_by_code(self.code)
        guest = next(player for player in room.players if player.player_id != room.host_id)
        state = copy.deepcopy(room.game_state)
        state.update(phase='reveal', storyteller_order=[guest.player_id, room.host_id], turn_index=0,
                     round_summary={'winners': [], 'points': 1})
        self.game.set_state(room, state)
        self.game.mark_reveal_ready(room, guest.player_id)
        self.assertEqual(room.game_state['phase'], 'theme_selection')
        self.assertIn(room.host_id, room.game_state['pending_reveals'])
        held = room.game_state['pending_reveals'][room.host_id]
        self.game.mark_reveal_ready(room, room.host_id, held)
        self.assertNotIn(room.host_id, room.game_state['pending_reveals'])

    def test_start_from_stale_lobby_keeps_newly_joined_player(self):
        room = self.rooms.create_room('Other host', 'Other room', RoomSettings(), is_private=False, emoji='🌼')
        self.rooms.add_player(room, 'First guest', emoji='🐱')
        stale = self.repo.get_by_code(room.room_code)
        self.rooms.add_player(room, 'New guest', emoji='🦊')
        self.game.start_game(stale)
        latest = self.repo.get_by_code(room.room_code)
        self.assertEqual(len(latest.players), 3)
        self.assertEqual(latest.game_state['game_mode'], 'standard')
        self.assertEqual(set(latest.game_state['scores']), {p.player_id for p in latest.players})

    def test_lobby_changes_preserve_players_who_just_joined(self):
        room = self.rooms.create_room('Other host', 'Other room', RoomSettings(), is_private=False, emoji='🌼')
        first = self.rooms.add_player(room, 'First guest', emoji='🐱')
        stale = self.repo.get_by_code(room.room_code)
        self.rooms.add_player(room, 'New guest', emoji='🦊')
        self.rooms.update_max_score(stale, 15)
        self.assertEqual(len(self.repo.get_by_code(room.room_code).players), 3)
        self.rooms.remove_player(stale, first.player_id)
        names = {player.name for player in self.repo.get_by_code(room.room_code).players}
        self.assertEqual(names, {'Other host', 'New guest'})

    def test_stale_lobby_cannot_remove_a_player_after_start(self):
        room = self.rooms.create_room('Other host', 'Other room', RoomSettings(), is_private=False, emoji='🌼')
        guest = self.rooms.add_player(room, 'Guest', emoji='🐱')
        stale = self.repo.get_by_code(room.room_code)
        self.game.start_game(room)
        with self.assertRaises(RoomAlreadyStartedError):
            self.rooms.remove_player(stale, guest.player_id)
        self.assertEqual(len(self.repo.get_by_code(room.room_code).players), 2)

    def test_lobby_settings_preserve_new_players_and_reject_stale_settings(self):
        room = self.rooms.create_room('Other host', 'Other room', RoomSettings(), is_private=False, emoji='🌼')
        stale = self.repo.get_by_code(room.room_code)
        guest = self.rooms.add_player(room, 'Guest', emoji='🐱')
        self.rooms.update_lobby_settings(stale, language='fr', is_private=True,
                                        expected_language='en', expected_private=False)
        latest = self.repo.get_by_code(room.room_code)
        self.assertEqual([p.player_id for p in latest.players], [room.host_id, guest.player_id])
        self.assertEqual(latest.settings.language, 'fr')
        self.assertTrue(latest.is_private)
        with self.assertRaises(RoomSettingsConflictError):
            self.rooms.update_lobby_settings(room, language='de', is_private=False,
                                             expected_language='en', expected_private=False)
        self.assertEqual(self.repo.get_by_code(room.room_code).settings.language, 'fr')

    def test_started_game_rejects_lobby_settings_changes(self):
        room = self.rooms.create_room('Other host', 'Other room', RoomSettings(), is_private=False, emoji='🌼')
        self.rooms.add_player(room, 'Guest', emoji='🐱')
        stale = self.repo.get_by_code(room.room_code)
        self.game.start_game(room)
        with self.assertRaises(RoomAlreadyStartedError):
            self.rooms.update_lobby_settings(stale, language='fr', is_private=True,
                                             expected_language='en', expected_private=False)
        self.assertEqual(self.repo.get_by_code(room.room_code).settings.language, 'en')

    def test_two_concurrent_answers_never_silently_overwrite_each_other(self):
        snapshots = [self.repo.get_by_code(self.code) for _ in range(2)]
        def submit(index):
            state = copy.deepcopy(snapshots[index].game_state)
            state['answer_submissions'][f'player-{index}'] = f'answer-{index}'
            try:
                self.game.set_state(snapshots[index], state)
                return ('saved', index)
            except GameStateConflictError:
                return ('conflict', index)
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(submit, range(2)))
        self.assertCountEqual([status for status, _ in outcomes], ['saved', 'conflict'])
        latest = self.repo.get_by_code(self.code)
        self.assertEqual(len(latest.game_state['answer_submissions']), 1)
        retry_index = next(index for status, index in outcomes if status == 'conflict')
        state = copy.deepcopy(latest.game_state)
        state['answer_submissions'][f'player-{retry_index}'] = f'answer-{retry_index}'
        self.game.set_state(latest, state)
        self.assertEqual(len(self.repo.get_by_code(self.code).game_state['answer_submissions']), 2)

    def test_other_player_metadata_survives_game_state_save(self):
        snapshot = self.repo.get_by_code(self.code)
        self.rooms.set_player_emoji(self.repo.get_by_code(self.code), snapshot.players[1].player_id, '🐱')
        state = copy.deepcopy(snapshot.game_state)
        state['selected_level'] = 'deep'
        self.game.set_state(snapshot, state)
        self.assertEqual(self.repo.get_by_code(self.code).players[1].emoji, '🐱')

    def test_a_closed_room_cannot_be_reopened_by_a_stale_save(self):
        snapshot = self.repo.get_by_code(self.code)
        self.game.end_game(self.repo.get_by_code(self.code))
        with self.assertRaises(GameStateConflictError):
            self.game.set_state(snapshot, snapshot.game_state)
        self.assertFalse(self.repo.get_by_code(self.code).started)

    def test_return_to_lobby_does_not_overwrite_a_new_game_update(self):
        stale = self.repo.get_by_code(self.code)
        current = self.repo.get_by_code(self.code)
        state = copy.deepcopy(current.game_state)
        state['question_events_pending'] = [{'id': 'event', 'question_id': 'q', 'action': 'saved'}]
        self.game.set_state(current, state)
        with self.assertRaises(GameStateConflictError):
            self.game.end_game(stale)
        latest = self.repo.get_by_code(self.code)
        self.assertTrue(latest.started)
        self.assertEqual(latest.game_state['question_events_pending'], state['question_events_pending'])

    def test_return_to_lobby_keeps_recent_player_metadata(self):
        stale = self.repo.get_by_code(self.code)
        self.rooms.set_player_emoji(self.repo.get_by_code(self.code), stale.players[1].player_id, '🐱')
        self.game.end_game(stale)
        latest = self.repo.get_by_code(self.code)
        self.assertFalse(latest.started)
        self.assertEqual(latest.players[1].emoji, '🐱')


if __name__ == '__main__':
    unittest.main()
