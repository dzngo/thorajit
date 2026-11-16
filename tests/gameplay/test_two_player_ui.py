import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from streamlit.testing.v1 import AppTest
from ui.game_flow import GameFlow


APP = '''
import streamlit as st
from types import SimpleNamespace
from unittest.mock import Mock
from ui.game_flow import GameFlow

if 'game' not in st.session_state:
    st.session_state.game = {
        'game_mode': 'two_player', 'phase': 'answer_entry', 'round': 1,
        'storyteller_order': ['a', 'b'], 'turn_index': 0, 'selected_level': 'deep',
        'selected_theme': 'Friends 🤝', 'question': {'question': 'Question?'},
        'answer_submissions': {}, 'scores': {'a': 0, 'b': 0}, 'max_score': 3,
        'completed_rounds': [], 'round_summary': None,
    }
if 'player' not in st.session_state:
    st.session_state.player = 'a'
players = [SimpleNamespace(player_id='a', name='Alex'), SimpleNamespace(player_id='b', name='Bea')]
room = SimpleNamespace(room_code='TEST', players=players, settings=SimpleNamespace(language='en', max_score=3))
flow = GameFlow(Mock(), Mock(), Mock())
flow._save_state = lambda room, state, **kwargs: None
flow._render_save_question = lambda *args: None
state = st.session_state.game
if state['phase'] == 'answer_entry':
    flow._render_answer_phase(room, state, 'a', st.session_state.player, False)
elif state['phase'] == 'judgment':
    flow._render_two_player_judgment(room, state, 'a', st.session_state.player)
elif state['phase'] == 'reveal':
    flow._render_two_player_reveal(room, state, 'a', st.session_state.player, False)
'''


class TwoPlayerUITests(unittest.TestCase):
    @patch('ui.game_flow.common.rerun')
    @patch('ui.game_flow.st')
    def test_answer_suggestion_uses_the_storyteller_name(self, st, rerun):
        st.session_state = {}
        st.button.side_effect = lambda _label, **kwargs: '_suggest_answer_' in kwargs.get('key', '')
        llm = Mock()
        llm.suggest_answer.return_value = SimpleNamespace(answer='Coffee')
        flow = GameFlow(Mock(), Mock(), llm)
        room = SimpleNamespace(room_code='TEST', settings=SimpleNamespace(language='en'))
        flow._render_answer_actions(room=room, state={'game_mode': 'standard'}, question='Question?',
                                    current_player_id='listener', storyteller_name='Alex', current_level='shallow',
                                    submissions={}, input_key='input', prefill_key='prefill', editing_key='editing',
                                    storyteller_id='storyteller')
        self.assertEqual(llm.suggest_answer.call_args.kwargs['storyteller_name'], 'Alex')
        self.assertEqual(st.session_state['prefill'], 'Coffee')
        rerun.assert_called_once()

    def test_submitted_answer_waits_and_can_be_modified(self):
        app = AppTest.from_string(APP).run()
        app.text_area[0].input('Coffee').run()
        next(button for button in app.button if button.label == 'Submit answer').click().run()
        app.run()
        self.assertIn('Answer submitted', [item.value for item in app.header])
        self.assertEqual(app.text_area[0].value, 'Coffee')
        self.assertTrue(app.text_area[0].disabled)
        self.assertTrue(any('Waiting for 1 player to answer' in item.value for item in app.get('html')))
        app.button(key='TEST_modify_answer_a').click().run()
        self.assertFalse(app.text_area[0].disabled)
        self.assertEqual(app.text_area[0].value, 'Coffee')
        self.assertFalse(app.exception)

    def test_both_can_submit_same_answer_and_only_storyteller_judges(self):
        app = AppTest.from_string(APP).run()
        self.assertNotIn('Suggest answer', [button.label for button in app.button])
        app.text_area[0].input('Same answer').run()
        next(button for button in app.button if button.label == 'Submit answer').click().run()
        self.assertEqual(app.session_state['game']['answer_submissions'], {'a': 'Same answer'})
        app.session_state['player'] = 'b'
        app.run()
        self.assertNotIn('Same answer', [item.value for item in app.markdown])
        app.text_area[0].input('Same answer').run()
        next(button for button in app.button if button.label == 'Submit answer').click().run()
        self.assertEqual(app.session_state['game']['phase'], 'judgment')
        self.assertFalse(any(button.label in ('Correct', 'Not quite') for button in app.button))
        self.assertNotIn('Same answer', [item.value for item in app.markdown])
        app.session_state['player'] = 'a'
        app.run()
        self.assertIn('Correct', [button.label for button in app.button])
        app.button(key='TEST_judgment_correct').click().run()
        self.assertEqual(app.session_state['game']['scores'], {'a': 0, 'b': 3})
        self.assertEqual(app.session_state['game']['phase'], 'reveal')
        self.assertEqual(app.session_state['game']['round_summary']['winners'], [])
        self.assertFalse(app.exception)


if __name__ == '__main__':
    unittest.main()
