"""A removed player should not remain in a lobby or enter its game."""
import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from models import RoomSettings
from services.game_service import GameService
from services.room_service import RoomService
from storage.room_repository import RoomRepository


APP = '''
import streamlit as st
from pathlib import Path
from storage.room_repository import RoomRepository
from services.room_service import RoomService
from ui.join_flow import JoinFlow
rooms = RoomService(RoomRepository(Path(st.session_state.path)))
JoinFlow(rooms).render()
'''


class RemovedGuestUITests(unittest.TestCase):
    def test_removed_guest_returns_to_room_list_even_if_game_starts(self):
        for started in (False, True):
            with self.subTest(started=started), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'rooms.json'
                rooms = RoomService(RoomRepository(path))
                room = rooms.create_room('Alex', 'Test', RoomSettings(), is_private=False, emoji='😀')
                guest = rooms.add_player(room, 'Bea', emoji='🐸')
                rooms.add_player(room, 'Cee', emoji='🐱')
                app = AppTest.from_string(APP, default_timeout=15)
                app.session_state.path = str(path)
                app.session_state.route = 'join'
                app.session_state.join_flow = {'step': 'lobby', 'joined_room_code': room.room_code,
                                                'player_id': guest.player_id}
                app.session_state.player_profile = {'player_id': guest.player_id, 'room_code': room.room_code}
                app.run()
                self.assertIn('Your room', [header.value for header in app.header])

                rooms.remove_player(room, guest.player_id)
                if started:
                    GameService(rooms).start_game(room)
                app.run()
                self.assertFalse(app.exception)
                self.assertEqual(app.session_state.route, 'join')
                self.assertEqual(app.session_state.join_flow['step'], 'room_list')
                self.assertTrue(any('no longer in that room' in warning.value for warning in app.warning))
                self.assertNotIn('player_profile', app.session_state)


if __name__ == '__main__':
    unittest.main()
