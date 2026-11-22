import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch
from streamlit.testing.v1 import AppTest

from ui import visual
from ui.game_flow import GameFlow
from services.game_service import GameStateConflictError


class WaitingUITests(unittest.TestCase):
    @patch('ui.game_flow.common.show_player_scores')
    @patch('ui.game_flow.common.show_room_summary')
    @patch('ui.game_flow.st')
    def test_translation_fallback_is_visible_to_listeners(self, st, show_room, show_scores):
        st.button.return_value = False
        st.columns.return_value = [Mock(), Mock()]
        for column in st.columns.return_value:
            column.button.return_value = False
        flow = GameFlow(Mock(), Mock(), Mock())
        flow._render_leave_game = Mock()
        room = SimpleNamespace(room_code='TEST', players=[])
        state = {'phase': 'answer_entry', 'scores': {}, 'question': {'translation_fallback': True}}
        flow._render_board(room, state, SimpleNamespace(name='Alex'), 'Bea', False, False)
        st.info.assert_called_once()
        self.assertIn('shown in English', st.info.call_args.args[0])

    def test_end_game_requires_the_explicit_confirmation_action(self):
        app = AppTest.from_string('''
import streamlit as st
from types import SimpleNamespace
from unittest.mock import Mock, patch
from ui.game_flow import GameFlow
room = SimpleNamespace(room_code='TEST', players=[])
flow = GameFlow(Mock(), Mock(), Mock())
flow._finalize_results = lambda *args, **kwargs: st.session_state.update(ended=True)
with patch('ui.game_flow.common.show_room_summary'), patch('ui.game_flow.common.show_player_scores'):
    flow._render_board(room, {'scores':{}}, None, 'Host', True, False)
''').run()
        self.assertEqual(app.button(key='TEST_open_scores').label, ':material/leaderboard:')
        app.button(key='TEST_open_settings').click().run()
        self.assertNotIn('ended', app.session_state)
        app.button(key='host_end_game').click().run()
        self.assertTrue(app.session_state.ended)
        self.assertFalse(app.exception)

    @patch('ui.visual.st')
    def test_waiting_card_is_noninteractive_and_escapes_text(self, st):
        visual.waiting_card('<Alex> is choosing', 'Hang tight.')
        content = st.html.call_args.args[0]
        self.assertIn('&lt;Alex&gt; is choosing', content)
        self.assertIn('role="status"', content)
        self.assertNotIn('<button', content)

    @patch('ui.visual.st')
    def test_two_player_decision_is_a_noninteractive_status(self, st):
        for correct, label in ((True, 'Correct!'), (False, 'Not quite')):
            with self.subTest(correct=correct):
                visual.decision_status(correct)
                content = st.html.call_args.args[0]
                self.assertIn(label, content)
                self.assertIn('role="status"', content)
                self.assertNotIn('<button', content)

    @patch('ui.game_flow.visual.waiting_card')
    def test_listener_sees_storyteller_name_while_question_is_prepared(self, waiting_card):
        flow = GameFlow(Mock(), Mock(), Mock())
        room = SimpleNamespace(players=[SimpleNamespace(player_id='a', name='Alex')])
        flow._render_theme_phase(room, {}, 'a', 'b')
        waiting_card.assert_called_once_with('Alex is choosing a question', '')

    @patch('ui.game_flow.st')
    def test_storyteller_watches_reveal_for_host_advancing_turn(self, st):
        profile = {'player_id': 'a', 'name': 'Alex'}
        st.session_state.get.side_effect = {'active_room_code': 'TEST', 'player_profile': profile}.get
        state = {'phase': 'reveal', 'game_mode': 'standard', 'storyteller_order': ['a'], 'turn_index': 0}
        room = SimpleNamespace(room_code='TEST', started=True, game_state=state, host_id='b',
                               players=[SimpleNamespace(player_id='a', name='Alex')],
                               updated_at=datetime.fromisoformat('2026-01-01'))
        service = Mock()
        service.get_room_by_code.return_value = room
        flow = GameFlow(service, Mock(), Mock())
        flow._flush_events = Mock()
        flow._watch_room_updates = Mock()
        flow._render_board = Mock()
        flow._render_reveal_phase = Mock()
        flow.render()
        flow._watch_room_updates.assert_called_once_with('TEST', room.updated_at.isoformat())

    @patch('ui.game_flow.st')
    def test_listener_choosing_a_guess_watches_for_early_reveal(self, st):
        profile = {'player_id': 'b', 'name': 'Bea'}
        st.session_state.get.side_effect = {'active_room_code': 'TEST', 'player_profile': profile}.get
        state = {'phase': 'guessing', 'storyteller_order': ['a'], 'turn_index': 0,
                 'listener_guesses': {}}
        room = SimpleNamespace(room_code='TEST', started=True, game_state=state, host_id='a',
                               players=[SimpleNamespace(player_id='a', name='Alex'),
                                        SimpleNamespace(player_id='b', name='Bea')],
                               updated_at=datetime.fromisoformat('2026-01-01'))
        service = Mock()
        service.get_room_by_code.return_value = room
        flow = GameFlow(service, Mock(), Mock())
        flow._flush_events = Mock()
        flow._watch_room_updates = Mock()
        flow._render_board = Mock()
        flow._render_guess_phase = Mock()
        flow.render()
        flow._watch_room_updates.assert_called_once_with('TEST', room.updated_at.isoformat())

    @patch('ui.game_flow.common.rerun')
    @patch('ui.game_flow.st')
    def test_passive_transition_conflict_refreshes_without_error(self, st, rerun):
        game = Mock()
        game.set_state.side_effect = GameStateConflictError('changed')
        flow = GameFlow(Mock(), game, Mock())
        flow._store_state(Mock(), {}, refresh_on_conflict=True)
        rerun.assert_called_once()
        st.error.assert_not_called()


if __name__ == '__main__':
    unittest.main()
