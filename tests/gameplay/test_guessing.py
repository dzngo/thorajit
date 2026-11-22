import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from ui.game_flow import GameFlow


class GuessingTests(unittest.TestCase):
    def setUp(self):
        self.flow = GameFlow(Mock(), Mock(), Mock())
        self.flow._render_save_question = Mock()
        self.flow._save_state = Mock()
        self.room = SimpleNamespace(room_code='TEST', players=[
            SimpleNamespace(player_id='story', name='Story'),
            SimpleNamespace(player_id='one', name='One'),
            SimpleNamespace(player_id='two', name='Two'),
        ])
        self.state = {'question': {'question': 'Question?'}, 'multiple_choice': {'options': [
            {'label': 'A', 'text': 'Story answer', 'owner_id': 'story'},
            {'label': 'B', 'text': 'One answer', 'owner_id': 'one'},
            {'label': 'C', 'text': 'Two answer', 'owner_id': 'two'},
        ]}, 'listener_guesses': {}}

    @patch('ui.game_flow.st')
    def test_only_other_players_answers_are_selectable(self, st):
        st.container.return_value = MagicMock()
        st.radio.return_value = 'C'
        st.button.side_effect = lambda label, **kwargs: label == 'Submit my guess'
        self.flow._render_guess_phase(self.room, self.state, 'story', 'one', False)
        self.assertEqual(st.radio.call_args.kwargs['options'], ['A', 'C'])
        self.assertEqual(st.radio.call_args.kwargs['format_func']('A'), 'Story answer')
        self.assertEqual(self.state['listener_guesses'], {'one': {'label': 'C'}})

    @patch('ui.game_flow.st')
    def test_rejects_own_answer_even_if_submitted(self, st):
        st.container.return_value = MagicMock()
        st.radio.return_value = 'B'
        st.button.side_effect = lambda label, **kwargs: label == 'Submit my guess'
        self.flow._render_guess_phase(self.room, self.state, 'story', 'one', False)
        self.assertEqual(self.state['listener_guesses'], {})
        self.flow._save_state.assert_not_called()
        st.error.assert_called_once()

    @patch('ui.game_flow.visual.question_card')
    @patch('ui.game_flow.st')
    def test_missing_player_cannot_see_storyteller_answer(self, st, question_card):
        st.container.return_value = MagicMock()
        self.flow._render_guess_phase(self.room, self.state, 'story', None, False)
        self.assertFalse(any('Story answer' in str(call) for call in st.write.call_args_list))
        st.warning.assert_called_once()
        st.radio.assert_not_called()

    @patch('ui.game_flow.visual.waiting_card')
    @patch('ui.game_flow.st')
    def test_listener_choosing_sees_the_same_waiting_card(self, st, waiting):
        st.button.return_value = False
        self.flow._render_guess_phase(self.room, self.state, 'story', 'one', True)
        waiting.assert_called_once_with('Waiting for 2 listeners to choose…', '')

    @patch('ui.game_flow.visual.waiting_card')
    @patch('ui.game_flow.visual.answer_card')
    @patch('ui.game_flow.visual.question_card')
    @patch('ui.game_flow.st')
    def test_submitted_listener_sees_only_their_guess_while_waiting(self, st, question, answer, waiting):
        self.state['listener_guesses'] = {'one': {'label': 'C'}}
        self.flow._render_guess_phase(self.room, self.state, 'story', 'one', False)
        st.header.assert_called_once_with('Guess submitted')
        answer.assert_called_once_with('Your guess', 'Two answer')
        waiting.assert_called_once_with('Waiting for 1 listener to choose…', '')
        st.radio.assert_not_called()

    @patch('ui.game_flow.visual.waiting_card')
    @patch('ui.game_flow.visual.answer_card')
    @patch('ui.game_flow.visual.question_card')
    @patch('ui.game_flow.st')
    def test_storyteller_sees_all_answers_while_listeners_guess(self, st, question, answer, waiting):
        self.state['listener_guesses'] = {'one': {'label': 'C'}}
        self.flow._render_guess_phase(self.room, self.state, 'story', 'story', False)
        st.header.assert_called_once_with('Listeners are guessing')
        markup = st.html.call_args.args[0]
        for text in ('Story answer', 'One answer', 'Two answer', 'Your answer'):
            self.assertIn(text, markup)
        self.assertNotIn('owner_id', markup)
        answer.assert_not_called()
        waiting.assert_called_once_with('Waiting for 1 listener to choose…', '')
        st.radio.assert_not_called()

    @patch('ui.game_flow.st')
    def test_storyteller_answers_use_columns_of_five_and_escape_text(self, st):
        options = [{'text': f'Answer <{i}>', 'owner_id': str(i)} for i in range(8)]
        self.flow._render_storyteller_answers(options, '0')
        markup = st.html.call_args.args[0]
        columns = markup.split('class="story-answer-column"')[1:]
        self.assertEqual([column.count('role="listitem"') for column in columns], [5, 3])
        self.assertIn('Answer &lt;0&gt;', columns[0])
        self.assertIn('Answer &lt;5&gt;', columns[1])
        self.assertEqual(markup.count('Your answer'), 1)


if __name__ == '__main__':
    unittest.main()
