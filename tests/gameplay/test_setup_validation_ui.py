import unittest
import tempfile
from pathlib import Path
from streamlit.testing.v1 import AppTest
from models import RoomSettings
from services.room_service import RoomService
from storage.room_repository import RoomRepository

HOST_APP = '''
from unittest.mock import Mock, patch
from ui.host_flow import HostFlow
with patch('ui.host_flow.pick_emoji', return_value=''):
    HostFlow(Mock(), Mock(), Mock()).render()
'''

JOIN_APP = '''
import streamlit as st
from types import SimpleNamespace
from unittest.mock import Mock, patch
from services.room_service import EmojiTakenError
from ui.join_flow import JoinFlow
if 'join_flow' not in st.session_state:
    st.session_state.join_flow={'step':'player_name','candidate_room_code':'TEST','player_name':'',
                                'emoji':'','player_id':None,'joined_room_code':None,'selected_player_id':None}
service=Mock()
service.get_room_by_code.return_value=SimpleNamespace(room_code='TEST',started=False,players=[])
service.add_player.side_effect=EmojiTakenError('That emoji was just taken. Choose another.')
with patch('ui.join_flow.pick_emoji',return_value='🐸'):
    JoinFlow(service).render()
'''

CONFLICT_APP = '''
import streamlit as st
from pathlib import Path
from unittest.mock import Mock, patch
from services.room_service import RoomService
from storage.room_repository import RoomRepository
from ui.host_flow import HostFlow
service = RoomService(RoomRepository(Path(st.session_state.path)))
with patch('ui.host_flow.pick_emoji', return_value='🐸'):
    HostFlow(service, Mock(), Mock()).render()
'''


class SetupValidationTests(unittest.TestCase):
    def test_existing_room_keeps_the_creation_details_when_going_back(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rooms.json'
            rooms = RoomService(RoomRepository(path))
            rooms.create_room('Alex', 'Friends', RoomSettings(), is_private=False, emoji='😀')
            app = AppTest.from_string(CONFLICT_APP)
            app.session_state.path = str(path)
            app.run()
            app.text_input[0].input('Bea').run()
            app.text_input[1].input('Friends').run()
            app.toggle[0].set_value(True).run()
            app.button(key='room_name_next').click().run()
            self.assertEqual(app.session_state.host_flow['step'], 'existing_room_decision')
            app.button(key='existing_back').click().run()
            self.assertEqual([item.value for item in app.text_input], ['Bea', 'Friends'])
            self.assertTrue(app.toggle[0].value)
            self.assertEqual(app.session_state.host_flow['emoji'], '🐸')
            self.assertEqual(len(rooms.list_rooms()), 1)
            self.assertFalse(app.exception)

    def test_host_validation_shows_missing_fields_and_keeps_input(self):
        app = AppTest.from_string(HOST_APP).run()
        self.assertFalse(app.error)
        app.text_input[0].input('Alex').run()
        app.button(key='room_name_next').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_input[0].value, 'Alex')
        self.assertEqual({item.value for item in app.error}, {'Choose your emoji.', 'Enter a room name.'})

    def test_taken_emoji_keeps_player_name(self):
        app = AppTest.from_string(JOIN_APP).run()
        app.text_input[0].input('Sam').run()
        app.button(key='player_name_join').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_input[0].value, 'Sam')
        self.assertTrue(any('emoji was just taken' in item.value for item in app.error))


if __name__ == '__main__':
    unittest.main()
