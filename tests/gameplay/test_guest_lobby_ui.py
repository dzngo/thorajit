import unittest
from streamlit.testing.v1 import AppTest

APP = '''
import streamlit as st
from types import SimpleNamespace
from datetime import datetime
from unittest.mock import Mock
from models import PlayerRole, RoomSettings
from ui.join_flow import JoinFlow
if 'join_flow' not in st.session_state:
    st.session_state.join_flow={'step':'lobby','joined_room_code':'TEST','candidate_room_code':'TEST',
                                'player_id':'b','player_name':'Sam','emoji':'🐱'}
players=[SimpleNamespace(player_id='a',name='Alex',emoji='😀',role=PlayerRole.HOST),
         SimpleNamespace(player_id='b',name='Sam',emoji='🐱',role=PlayerRole.JOINER)]
room=SimpleNamespace(room_code='TEST',name='Friends',is_private=False,players=players,
                     started=False,game_state={},settings=RoomSettings(),updated_at=datetime.now())
service=Mock()
service.get_room_by_code.return_value=room
flow=JoinFlow(service)
flow._watch_room_updates=lambda *args: None
flow._render_lobby()
'''


class GuestLobbyUITests(unittest.TestCase):
    def test_waiting_status_is_not_a_button(self):
        app = AppTest.from_string(APP).run()
        self.assertFalse(app.exception)
        status = [item.value for item in app.get('html') if 'Waiting for the host' in item.value]
        self.assertEqual(len(status), 1)
        self.assertIn('role="status"', status[0])
        self.assertNotIn('<button', status[0])
        self.assertEqual([button.label for button in app.button], ['Refresh', 'Change room'])


if __name__ == '__main__':
    unittest.main()
