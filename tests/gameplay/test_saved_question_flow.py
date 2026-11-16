import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from streamlit.testing.v1 import AppTest

from services.game_service import GameService
from ui.game_flow import GameFlow


class SavedQuestionFlowTests(unittest.TestCase):
    @patch('ui.game_flow.prepare_saved_question', side_effect=ValueError('Question unavailable.'))
    @patch('ui.game_flow.st')
    def test_unavailable_saved_question_preserves_existing_draft(self, st, prepare):
        st.container.return_value = MagicMock()
        st.button.side_effect = lambda _label, **kwargs: '_saved_use_' in kwargs.get('key', '')
        flow = GameFlow(Mock(), Mock(), Mock())
        flow._clear_question_draft = Mock()
        saved = {'save_id': 's', 'question': 'Saved?', 'theme': 'Friends', 'level': 'deep'}
        state = {'phase': 'saved_questions', 'question': {'question': 'Draft?'}, 'selected_theme': 'Travel',
                 'selected_level': 'shallow', 'saved_questions_by_player': {'p': [saved]}}
        flow._render_saved_questions_phase(SimpleNamespace(room_code='TEST', players=[]), state, 'p', 'p')
        self.assertEqual(state['question']['question'], 'Draft?')
        self.assertEqual(state['selected_theme'], 'Travel')
        self.assertEqual(state['selected_level'], 'shallow')
        flow._clear_question_draft.assert_not_called()
        st.error.assert_called_once_with('Question unavailable.')

    def test_next_turn_opens_saved_questions_only_when_available(self):
        for saved, expected in [({'next': [{'question': 'Saved?'}]}, 'saved_questions'), ({}, 'theme_selection')]:
            with self.subTest(expected=expected):
                room_service = Mock()
                room = SimpleNamespace(game_state={'storyteller_order': ['first', 'next'], 'turn_index': 0,
                                                   'saved_questions_by_player': saved}, update_timestamp=Mock())
                service = GameService(room_service)
                with patch.object(service, 'set_state', side_effect=lambda room, state: setattr(room, 'game_state', state)):
                    service.prepare_next_turn(room)
                self.assertEqual(room.game_state['phase'], expected)

    @patch('ui.game_flow.st')
    def test_skip_goes_to_theme_selection_and_retains_saved(self, st):
        st.container.return_value = MagicMock()
        st.button.side_effect = lambda _label, **kwargs: kwargs.get('key', '').endswith('_skip_saved_questions')
        flow = GameFlow(Mock(), Mock(), Mock())
        flow._save_state = Mock()
        saved = {'save_id': 's', 'question': 'Saved?'}
        state = {'phase': 'saved_questions', 'saved_questions_by_player': {'p': [saved]}}
        flow._render_saved_questions_phase(SimpleNamespace(room_code='TEST'), state, 'p', 'p')
        self.assertEqual(state['phase'], 'theme_selection')
        self.assertEqual(state['saved_questions_by_player']['p'], [saved])
        flow._save_state.assert_called_once()

    def test_saved_question_actions_preserve_the_selected_question(self):
        source = """
import streamlit as st
from types import SimpleNamespace
from unittest.mock import Mock
from ui.game_flow import GameFlow
if 'game' not in st.session_state:
    st.session_state.game = {'phase':'saved_questions', 'saved_questions_by_player':{'p':[
        {'save_id':'s', 'question':'What makes you smile?', 'question_en':'What makes you smile?',
         'theme':'Friends', 'level':'shallow'}]}}
room = SimpleNamespace(room_code='TEST', players=[SimpleNamespace(player_id='p', name='Alex')])
flow = GameFlow(Mock(), Mock(), Mock())
flow._save_state = lambda room, state: None
flow._render_saved_questions_phase(room, st.session_state.game, 'p', 'p')
"""
        app = AppTest.from_string(source).run()
        app.button(key='TEST_saved_use_s').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.game['phase'], 'question_generation')
        self.assertEqual(app.session_state.game['question']['question'], 'What makes you smile?')
        remove_app = AppTest.from_string(source).run()
        remove_app.button(key='TEST_saved_remove_s').click().run()
        self.assertFalse(remove_app.exception)
        self.assertEqual(remove_app.session_state.game['saved_questions_by_player']['p'], [])


if __name__ == '__main__':
    unittest.main()
