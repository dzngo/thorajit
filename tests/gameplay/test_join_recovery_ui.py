"""Profile drafts and status remain visible when a room changes while joining."""
import unittest
from streamlit.testing.v1 import AppTest

APP = '''
import streamlit as st
from types import SimpleNamespace
from unittest.mock import Mock, patch
from ui.join_flow import JoinFlow
if 'join_flow' not in st.session_state:
    st.session_state.join_flow = {'step': 'player_name', 'player_name': '', 'emoji': '',
                                  'candidate_room_code': 'TEST', 'player_id': None,
                                  'joined_room_code': None, 'selected_player_id': None}
if 'available' not in st.session_state:
    st.session_state.available = True
room = SimpleNamespace(room_code='TEST', started=st.session_state.get('started', False),
                       players=[SimpleNamespace(player_id='a', name='Alex', emoji='😀')])
service = Mock()
service.get_room_by_code.return_value = room if st.session_state.available else None
service.list_rooms.return_value = []
with patch('ui.join_flow.pick_emoji', return_value='🐸'):
    JoinFlow(service).render()
'''


class JoinRecoveryUITests(unittest.TestCase):
    def test_room_disappearing_preserves_draft_and_explains_what_happened(self):
        app = AppTest.from_string(APP).run()
        app.text_input[0].input('Sam').run()
        app.session_state['join_emoji_TEST'] = {'value': '🐸'}
        app.session_state.available = False
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.join_flow['step'], 'room_list')
        self.assertEqual(app.session_state.join_flow['player_name'], 'Sam')
        self.assertEqual(app.session_state.join_flow['emoji'], '🐸')
        self.assertTrue(any('no longer available' in item.value for item in app.warning))
        self.assertIn('Refresh', [button.label for button in app.button])

    def test_room_starting_preserves_draft_and_offers_resume(self):
        app = AppTest.from_string(APP).run()
        app.text_input[0].input('Sam').run()
        app.session_state['join_emoji_TEST'] = {'value': '🐸'}
        app.session_state.started = True
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.join_flow['step'], 'reclaim_player')
        self.assertEqual(app.session_state.join_flow['player_name'], 'Sam')
        self.assertEqual(app.session_state.join_flow['emoji'], '🐸')
        self.assertTrue(any('already started' in item.value for item in app.warning))
        self.assertIn('Resume game', [button.label for button in app.button])
        self.assertTrue(app.button(key='reclaim_confirm').disabled)
        self.assertEqual(app.radio[0].options, ['😀 Alex'])
        app.radio[0].set_value('😀 Alex').run()
        self.assertFalse(app.button(key='reclaim_confirm').disabled)

    def test_back_preserves_profile_draft(self):
        app = AppTest.from_string(APP).run()
        app.text_input[0].input('Sam').run()
        app.button(key='player_name_back').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.join_flow['player_name'], 'Sam')
        self.assertEqual(app.session_state.join_flow['emoji'], '🐸')


if __name__ == '__main__':
    unittest.main()
