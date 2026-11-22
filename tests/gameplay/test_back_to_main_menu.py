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
from unittest.mock import Mock
from services.game_service import GameService
from services.room_service import RoomService
from storage.room_repository import RoomRepository
from ui.game_flow import GameFlow
from ui.routing import Router

rooms = RoomService(RoomRepository(Path(st.session_state.path)))
if st.session_state.get('route') == 'entry':
    router = Router.__new__(Router)
    router.room_service = rooms
    router._render_entry()
else:
    GameFlow(rooms, GameService(rooms), Mock()).render()
'''


class BackToMainMenuTests(unittest.TestCase):
    def test_close_buttons_return_to_game_without_changing_room(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rooms.json'
            rooms = RoomService(RoomRepository(path))
            room = rooms.create_room('Host', 'Test room', RoomSettings(), is_private=False)
            rooms.add_player(room, 'Guest')
            GameService(rooms).start_game(room)
            before = path.read_bytes()
            app = AppTest.from_string(APP)
            app.session_state.path = str(path)
            app.session_state.route = 'game'
            app.session_state.active_room_code = room.room_code
            app.session_state.player_profile = {'room_code': room.room_code,
                                                'player_id': room.host_id, 'name': room.host_name}
            app.run()
            for panel in ('scores', 'settings'):
                with self.subTest(panel=panel):
                    app.button(key=f'{room.room_code}_open_{panel}').click().run()
                    self.assertEqual(app.session_state[f'{room.room_code}_game_panel'], panel)
                    app.button(key=f'{room.room_code}_close_{panel}').click().run()
                    self.assertIsNone(app.session_state[f'{room.room_code}_game_panel'])
                    self.assertEqual(app.session_state.route, 'game')
                    self.assertFalse(app.exception)
                    self.assertEqual(path.read_bytes(), before)

    def test_host_and_guest_can_return_without_changing_room(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rooms.json'
            rooms = RoomService(RoomRepository(path))
            room = rooms.create_room('Host', 'Test room', RoomSettings(), is_private=False)
            guest = rooms.add_player(room, 'Guest')
            GameService(rooms).start_game(room)
            before = path.read_bytes()
            for player in (room.players[0], guest):
                with self.subTest(player=player.name):
                    app = AppTest.from_string(APP)
                    app.session_state.path = str(path)
                    app.session_state.route = 'game'
                    app.session_state.active_room_code = room.room_code
                    app.session_state.player_profile = {'room_code': room.room_code,
                                                        'player_id': player.player_id, 'name': player.name}
                    app.session_state.reconnect_token = 'existing-token'
                    app.session_state.reconnect_identity = (room.room_code, player.player_id)
                    app.run()
                    app.button(key=f'{room.room_code}_open_settings').click().run()
                    app.button(key=f'{room.room_code}_back_to_main_menu').click().run()
                    self.assertFalse(app.exception)
                    self.assertEqual(app.session_state.route, 'entry')
                    self.assertEqual(app.session_state.reconnect_token, 'existing-token')
                    self.assertEqual(path.read_bytes(), before)
                    app.button(key='entry_return_game').click().run()
                    self.assertFalse(app.exception)
                    self.assertEqual(app.session_state.route, 'game')
                    self.assertEqual(app.session_state.active_room_code, room.room_code)
                    self.assertEqual(path.read_bytes(), before)
