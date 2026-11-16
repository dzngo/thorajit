import unittest

from streamlit.testing.v1 import AppTest


APP = '''
import streamlit as st
from types import SimpleNamespace
from unittest.mock import Mock
from ui.game_flow import GameFlow

if 'game' not in st.session_state:
    st.session_state.game = {
        'question': {'question_id': 'q1', 'question': 'Original question?', 'question_en': 'Original question?', 'source': 'bank'},
        'selected_theme': 'Friends 🤝', 'selected_level': 'shallow', 'phase': 'question_generation',
        'storyteller_order': ['p'], 'turn_index': 0,
    }
room = SimpleNamespace(room_code='TEST', settings=SimpleNamespace(language='en'))
flow = GameFlow(Mock(), Mock(), Mock())
flow._save_state = lambda room, state: None
flow._render_question_phase(room, st.session_state.game, 'p', 'p')
'''


class QuestionEditUITests(unittest.TestCase):
    def test_edit_prefills_cancel_discards_and_confirm_uses_original(self):
        app = AppTest.from_string(APP).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.text_area), 0)
        app.button(key='TEST_question_edit').click().run()
        self.assertEqual(app.button(key='TEST_question_edit').label, 'Cancel edit')
        self.assertEqual(app.text_area[0].value, 'Original question?')
        app.text_area[0].input('Changed question?').run()
        app.button(key='TEST_question_edit').click().run()
        self.assertEqual(len(app.text_area), 0)
        self.assertEqual(app.button(key='TEST_question_edit').label, 'Edit question')
        app.button(key='TEST_question_edit').click().run()
        self.assertEqual(app.text_area[0].value, 'Original question?')
        app.button(key='TEST_question_edit').click().run()
        next(button for button in app.button if button.label == 'Confirm question').click().run()
        self.assertEqual(app.session_state['game']['question']['question'], 'Original question?')
        self.assertFalse(app.exception)

    def test_confirm_preserves_the_edited_question(self):
        app = AppTest.from_string(APP).run()
        app.button(key='TEST_question_edit').click().run()
        app.text_area[0].input('Changed question?').run()
        next(button for button in app.button if button.label == 'Confirm question').click().run()
        self.assertEqual(app.session_state['game']['question']['question'], 'Changed question?')
        self.assertFalse(app.exception)

    def test_edit_clears_old_translation_fallback_notice(self):
        app = AppTest.from_string(APP.replace("'source': 'bank'", "'source': 'bank', 'translation_fallback': True")).run()
        app.button(key='TEST_question_edit').click().run()
        app.text_area[0].input('Changed question?').run()
        app.button(key='TEST_question_confirm').click().run()
        self.assertFalse(app.session_state.game['question']['translation_fallback'])
        self.assertFalse(app.exception)


if __name__ == '__main__':
    unittest.main()
