import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from models import RoomSettings
from services.game_service import GameService
from services.two_player_game import judge_answer, player_statistics
from ui.game_flow import GameFlow


class TwoPlayerTests(unittest.TestCase):
    def new_state(self, target=3):
        return {'scores': {'a': 0, 'b': 0}, 'max_score': target, 'round': 1,
                'selected_level': 'deep', 'answer_submissions': {'a': 'same', 'b': 'same'},
                'completed_rounds': [], 'round_summary': None}

    def test_judgment_points_equal_turns_and_tie(self):
        state = self.new_state()
        judge_answer(state, 'a', 'b', True)
        self.assertEqual(state['scores'], {'a': 0, 'b': 3})
        self.assertEqual(state['round_summary']['winners'], [])
        judge_answer(state, 'a', 'b', True)
        self.assertEqual(state['scores']['b'], 3)
        self.assertEqual(len(state['completed_rounds']), 1)
        state['round'] = 2
        state['round_summary'] = None
        judge_answer(state, 'b', 'a', True)
        self.assertEqual(set(state['round_summary']['winners']), {'a', 'b'})
        self.assertEqual(player_statistics(state, 'a')['deep'], 1)
        self.assertEqual(player_statistics(state, 'b')['accuracy'], 1.0)

    def test_shallow_wrong_and_requires_both_answers(self):
        state = self.new_state(target=1)
        state['selected_level'] = 'shallow'
        judge_answer(state, 'a', 'b', False)
        self.assertEqual(state['scores']['b'], 0)
        state['round_summary'] = None
        state['answer_submissions'] = {'a': 'answer'}
        with self.assertRaises(ValueError):
            judge_answer(state, 'a', 'b', True)

    def test_second_player_can_overtake_first_player_after_target(self):
        state = self.new_state(target=2)
        judge_answer(state, 'a', 'b', True)
        state.update(round=2, round_summary=None, selected_level='shallow')
        judge_answer(state, 'b', 'a', True)
        self.assertEqual(state['round_summary']['winners'], ['b'])
        self.assertEqual(state['scores'], {'a': 1, 'b': 3})

    def test_start_sets_mode_and_default_respects_custom_score(self):
        for players, custom, target, expected in [(2, False, 100, 10), (3, False, 10, 100), (2, True, 25, 25)]:
            with self.subTest(players=players, custom=custom):
                room = SimpleNamespace(room_code='TEST', players=[SimpleNamespace(player_id=str(i)) for i in range(players)],
                                       settings=RoomSettings(max_score=target, max_score_customized=custom),
                                       update_timestamp=Mock(), started=False)
                service = Mock()
                service.repository.update.side_effect = lambda _code, operation: (room, operation(room))
                GameService(service).start_game(room)
                self.assertEqual(room.settings.max_score, expected)
                self.assertEqual(room.game_state['game_mode'], 'two_player' if players == 2 else 'standard')

    def test_two_player_results_have_correct_breakdown_and_escape_names(self):
        flow = GameFlow(Mock(), Mock(), Mock())
        room = SimpleNamespace(players=[SimpleNamespace(player_id='a', name='A < B'), SimpleNamespace(player_id='b', name='Bee')])
        state = self.new_state()
        judge_answer(state, 'a', 'b', True)
        result = flow._build_two_player_statistics_html(room, state)
        self.assertIn('A &lt; B as Listener', result)
        self.assertIn('1 of 1 correct · 100%', result)
        self.assertIn('Shared understanding: 100%', result)
        self.assertNotIn('Best Impostor', result)

    @patch('ui.game_flow.st')
    def test_final_screen_displays_tie_and_matching_ranks(self, st):
        st.button.return_value = False
        flow = GameFlow(Mock(), Mock(), Mock())
        flow._inject_results_arcade_css = Mock()
        room = SimpleNamespace(players=[SimpleNamespace(player_id='a', name='Alex'), SimpleNamespace(player_id='b', name='Bea')])
        state = {'game_mode': 'two_player', 'scores': {'a': 3, 'b': 3}, 'winners': ['a', 'b'], 'completed_rounds': []}
        flow._render_results(room, state, True)
        result = st.html.call_args.args[0]
        self.assertIn('Alex & Bea are the winners', st.success.call_args.args[0])
        self.assertEqual(result.count('<b>#1</b>'), 2)
        self.assertIn('No completed rounds yet.', result)

    def test_standard_scoring_still_awards_three_points_for_one_correct(self):
        flow = GameFlow(Mock(), Mock(), Mock())
        room = SimpleNamespace(players=[SimpleNamespace(player_id='a'), SimpleNamespace(player_id='b'), SimpleNamespace(player_id='c')],
                               settings=SimpleNamespace(max_score=100))
        state = {'scores': {'a': 0, 'b': 0, 'c': 0}, 'selected_level': 'shallow',
                 'multiple_choice': {'options': [{'label': 'A', 'kind': 'true', 'owner_id': 'a'},
                                                 {'label': 'B', 'kind': 'listener', 'owner_id': 'b'}]},
                 'listener_guesses': {'b': {'label': 'A'}, 'c': {'label': 'B'}}}
        flow._compute_scoring(room, state, 'a')
        self.assertEqual(state['scores']['a'], 3)
        self.assertEqual(state['scores']['b'], 4)  # correct guess plus one decoy pick
        self.assertEqual(state['scores']['c'], 0)

    def test_standard_game_awards_win_only_to_highest_scorers(self):
        flow = GameFlow(Mock(), Mock(), Mock())
        room = SimpleNamespace(players=[SimpleNamespace(player_id='a'), SimpleNamespace(player_id='b'), SimpleNamespace(player_id='c')],
                               settings=SimpleNamespace(max_score=3))
        state = {'scores': {'a': 0, 'b': 0, 'c': 0}, 'selected_level': 'shallow',
                 'multiple_choice': {'options': [{'label': 'A', 'kind': 'true', 'owner_id': 'a'},
                                                 {'label': 'B', 'kind': 'listener', 'owner_id': 'b'}]},
                 'listener_guesses': {'b': {'label': 'A'}, 'c': {'label': 'B'}}}
        result = flow._compute_scoring(room, state, 'a')
        self.assertEqual(state['scores'], {'a': 3, 'b': 4, 'c': 0})
        self.assertEqual(result['winners'], ['b'])

    @patch('ui.game_flow.st')
    def test_listener_cannot_see_answers_in_judgment(self, st):
        flow = GameFlow(Mock(), Mock(), Mock())
        flow._render_save_question = Mock()
        state = self.new_state()
        state['question'] = {'question': 'Question?'}
        state['answer_submissions'] = {'a': 'secret storyteller answer', 'b': 'my own answer'}
        room = SimpleNamespace(players=[SimpleNamespace(player_id='a', name='A'), SimpleNamespace(player_id='b', name='B')])
        with patch('ui.game_flow.visual.answer_card') as answer, patch('ui.game_flow.visual.waiting_card') as waiting:
            flow._render_two_player_judgment(room, state, 'a', 'b')
        answer.assert_called_once_with('Your answer', 'my own answer')
        waiting.assert_called_once_with("Waiting for the Storyteller's decision…", '')
        self.assertFalse(any('secret storyteller answer' in str(call) for call in st.mock_calls))

    @patch('ui.game_flow.st')
    def test_duplicate_answer_allowed_and_no_suggestion_for_two_players(self, st):
        st.button.return_value = True
        st.session_state.get.return_value = 'same'
        flow = GameFlow(Mock(), Mock(), Mock())
        flow._save_state = Mock()
        state = {'game_mode': 'two_player', 'answer_submissions': {'a': 'same'}}
        room = SimpleNamespace(room_code='TEST', players=[SimpleNamespace(player_id='a'), SimpleNamespace(player_id='b')])
        flow._render_answer_actions(room=room, state=state, question='Q?', current_player_id='b',
                                    storyteller_name='A', current_level='shallow', submissions={'a': 'same'},
                                    input_key='input', prefill_key='prefill', editing_key='edit', storyteller_id='a')
        self.assertEqual(state['phase'], 'judgment')
        self.assertEqual(state['answer_submissions'], {'a': 'same', 'b': 'same'})
        self.assertFalse(any(call.args[0] == 'Suggest answer' for call in st.button.call_args_list))
        flow.llm_service.suggest_answer.assert_not_called()


if __name__ == '__main__':
    unittest.main()
