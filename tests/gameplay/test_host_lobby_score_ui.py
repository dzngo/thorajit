"""The lobby score editor must follow the room, not a previous browser widget."""
import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from models import RoomSettings
from services.room_service import RoomService
from storage.room_repository import RoomRepository


APP = '''
import streamlit as st
from pathlib import Path
from unittest.mock import Mock
from storage.room_repository import RoomRepository
from services.room_service import RoomService
from ui.host_flow import HostFlow
rooms = RoomService(RoomRepository(Path(st.session_state.path)))
HostFlow(rooms, Mock(), Mock())._render_lobby()
'''

GUEST_APP = '''
import streamlit as st
from pathlib import Path
from storage.room_repository import RoomRepository
from services.room_service import RoomService
from ui.join_flow import JoinFlow
rooms = RoomService(RoomRepository(Path(st.session_state.path)))
JoinFlow(rooms).render()
'''


class HostLobbyScoreUITests(unittest.TestCase):
    def test_guest_sees_room_code_after_host_makes_room_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rooms.json'
            rooms = RoomService(RoomRepository(path))
            room = rooms.create_room('Alex', 'Friends', RoomSettings(), is_private=False, emoji='😀')
            guest = rooms.add_player(room, 'Bea', emoji='🐸')
            host_app = AppTest.from_string(APP, default_timeout=15)
            host_app.session_state.path = str(path)
            host_app.session_state.host_flow = {'room_code': room.room_code}
            host_app.run()
            guest_app = AppTest.from_string(GUEST_APP, default_timeout=15)
            guest_app.session_state.path = str(path)
            guest_app.session_state.join_flow = {'step': 'lobby', 'joined_room_code': room.room_code,
                                                 'player_id': guest.player_id}
            guest_app.run()
            self.assertTrue(any('Friends' in element.value for element in guest_app.get('html')))

            host_app.toggle(key=f'lobby_private_{room.room_code}').set_value(True).run()
            host_app.button(key=f'{room.room_code}_settings_save').click().run()
            guest_app.run()
            markup = ' '.join(element.value for element in guest_app.get('html'))
            self.assertIn(room.room_code, markup)
            self.assertNotIn('Friends', markup)
            self.assertEqual(len(rooms.get_room_by_code(room.room_code).players), 2)
            self.assertFalse(guest_app.exception)

    def test_room_settings_save_explicitly_and_keep_players(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rooms.json'
            rooms = RoomService(RoomRepository(path))
            room = rooms.create_room('Alex', 'Friends', RoomSettings(), is_private=False, emoji='😀')
            guest = rooms.add_player(room, 'Bea', emoji='🐸')
            app = AppTest.from_string(APP, default_timeout=15)
            app.session_state.path = str(path)
            app.session_state.host_flow = {'room_code': room.room_code}
            app.run()
            app.selectbox(key=f'lobby_language_{room.room_code}').select('fr').run()
            app.toggle(key=f'lobby_private_{room.room_code}').set_value(True).run()
            self.assertTrue(next(button for button in app.button if button.label == 'Start game').disabled)
            self.assertEqual(rooms.get_room_by_code(room.room_code).settings.language, 'en')
            self.assertFalse(rooms.get_room_by_code(room.room_code).is_private)
            app.button(key=f'{room.room_code}_settings_save').click().run()
            saved = rooms.get_room_by_code(room.room_code)
            self.assertEqual(saved.settings.language, 'fr')
            self.assertTrue(saved.is_private)
            self.assertEqual([p.player_id for p in saved.players], [room.host_id, guest.player_id])
            self.assertFalse(next(button for button in app.button if button.label == 'Start game').disabled)
            self.assertFalse(app.exception)

    def test_discarding_room_settings_keeps_the_saved_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rooms.json'
            rooms = RoomService(RoomRepository(path))
            room = rooms.create_room('Alex', 'Friends', RoomSettings(), is_private=False, emoji='😀')
            rooms.add_player(room, 'Bea', emoji='🐸')
            app = AppTest.from_string(APP, default_timeout=15)
            app.session_state.path = str(path)
            app.session_state.host_flow = {'room_code': room.room_code}
            app.run()
            app.toggle(key=f'lobby_private_{room.room_code}').set_value(True).run()
            app.button(key=f'{room.room_code}_settings_discard').click().run()
            self.assertFalse(app.toggle(key=f'lobby_private_{room.room_code}').value)
            self.assertFalse(rooms.get_room_by_code(room.room_code).is_private)
            self.assertFalse(next(button for button in app.button if button.label == 'Start game').disabled)
            self.assertFalse(app.exception)

    def test_room_settings_conflict_preserves_draft_until_reloaded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rooms.json'
            rooms = RoomService(RoomRepository(path))
            room = rooms.create_room('Alex', 'Friends', RoomSettings(), is_private=False, emoji='😀')
            app = AppTest.from_string(APP, default_timeout=15)
            app.session_state.path = str(path)
            app.session_state.host_flow = {'room_code': room.room_code}
            app.run()
            app.selectbox(key=f'lobby_language_{room.room_code}').select('fr').run()
            rooms.update_lobby_settings(room, language='en', is_private=True,
                                        expected_language='en', expected_private=False)
            app.run()
            self.assertEqual(app.selectbox(key=f'lobby_language_{room.room_code}').value, 'fr')
            self.assertTrue(app.button(key=f'{room.room_code}_settings_save').disabled)
            self.assertTrue(any('changed elsewhere' in warning.value for warning in app.warning))
            app.button(key=f'{room.room_code}_settings_reload').click().run()
            self.assertEqual(app.selectbox(key=f'lobby_language_{room.room_code}').value, 'en')
            self.assertTrue(app.toggle(key=f'lobby_private_{room.room_code}').value)
            self.assertFalse(app.exception)

    def test_scores_are_isolated_by_room_and_refresh_from_saved_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rooms.json'
            rooms = RoomService(RoomRepository(path))
            first = rooms.create_room('Alex', 'First', RoomSettings(max_score=30, max_score_customized=True), is_private=False, emoji='😀')
            second = rooms.create_room('Bea', 'Second', RoomSettings(max_score=70, max_score_customized=True), is_private=False, emoji='🐸')
            app = AppTest.from_string(APP, default_timeout=15)
            app.session_state.path = str(path)
            app.session_state.host_flow = {'room_code': first.room_code}
            app.run()
            self.assertEqual(app.number_input[0].value, 30)
            app.number_input[0].set_value(40).run()
            self.assertEqual(rooms.get_room_by_code(first.room_code).settings.max_score, 40)

            app.session_state.host_flow['room_code'] = second.room_code
            app.run()
            self.assertEqual(app.number_input[0].value, 70)
            self.assertEqual(rooms.get_room_by_code(second.room_code).settings.max_score, 70)

            rooms.update_max_score(second, 90)
            app.run()
            self.assertEqual(app.number_input[0].value, 90)
            self.assertEqual(rooms.get_room_by_code(second.room_code).settings.max_score, 90)
            self.assertFalse(app.exception)


if __name__ == '__main__':
    unittest.main()
