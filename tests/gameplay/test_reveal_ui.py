import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from ui.game_flow import GameFlow


class RevealUITests(unittest.TestCase):
    @patch('ui.game_flow.st')
    def test_thorajit_only_for_one_correct_listener(self, st):
        options = [{'label': 'A', 'text': 'Coffee', 'owner_id': 'a', 'kind': 'true'},
                   {'label': 'B', 'text': 'Tea', 'owner_id': 'b', 'kind': 'listener'}]
        players = {'a': SimpleNamespace(name='Alex', emoji='😀'),
                   'b': SimpleNamespace(name='Bea', emoji='🐱'),
                   'c': SimpleNamespace(name='Cee', emoji='🐸')}
        cases = [({}, False), ({'b': {'label': 'B'}}, False),
                 ({'b': {'label': 'A'}, 'c': {'label': 'B'}}, True),
                 ({'b': {'label': 'A'}, 'c': {'label': 'A'}}, False)]
        for guesses, special in cases:
            with self.subTest(guesses=guesses):
                GameFlow._render_reveal_choices(options, guesses, players)
                markup = st.html.call_args.args[0]
                self.assertEqual('✦ Thorajit!' in markup, special)
                self.assertEqual('thor-moment-shape' in markup, special)
                self.assertEqual('✓ Correct' in markup, not special)

    @patch('ui.game_flow.st')
    def test_vote_fills_and_badges_follow_recorded_guesses(self, st):
        options = [
            {'label': 'A', 'text': 'A < B', 'owner_id': 'a', 'kind': 'true'},
            {'label': 'B', 'text': 'Other', 'owner_id': 'b', 'kind': 'listener'},
        ]
        lookup = {'a': SimpleNamespace(name='Alex', emoji='😀'),
                  'b': SimpleNamespace(name='Bea', emoji='🐸'),
                  'c': SimpleNamespace(name='Cee', emoji='🐱')}
        GameFlow._render_reveal_choices(options, {'b': {'label': 'A'}, 'c': {'label': 'A'}}, lookup)
        result = st.html.call_args.args[0]
        self.assertIn('--share:100.00%', result)
        self.assertIn('--share:0.00%', result)
        self.assertIn('A &lt; B', result)
        self.assertIn('🐸', result)
        self.assertIn('🐱', result)
        self.assertIn('aria-label="Bea voted for this answer"', result)
        self.assertIn('<span class="vote-voter-name">Bea</span>', result)
        self.assertIn('✓ Correct', result)
        self.assertIn('vote-author">😀 Alex', result)

    @patch('ui.game_flow.st')
    def test_no_guesses_and_many_choices(self, st):
        player = SimpleNamespace(name='Alex', emoji='😀')
        options = [{'label': str(i), 'text': str(i), 'owner_id': 'a'} for i in range(8)]
        GameFlow._render_reveal_choices(options, {}, {'a': player})
        result = st.html.call_args.args[0]
        self.assertEqual(result.count('--share:0.00%'), 8)
        self.assertEqual(result.count('class="vote-column"'), 2)
        st.caption.assert_called_once()

    @patch('ui.game_flow.st')
    def test_eight_player_reveal_groups_choices_and_shows_actual_voters(self, st):
        emojis = ['😀', '🐸', '🐱', '🐰', '🐼', '🦊', '🐻', '🐯']
        lookup = {str(i): SimpleNamespace(name=f'Player {i}', emoji=emojis[i]) for i in range(8)}
        options = [{'label': str(i), 'text': f'Answer {i}', 'owner_id': str(i),
                    'kind': 'true' if i == 0 else 'listener'} for i in range(8)]
        guesses = {str(i): {'label': '0' if i in (1, 2) else str(i - 1)} for i in range(1, 8)}
        GameFlow._render_reveal_choices(options, guesses, lookup)
        result = st.html.call_args.args[0]
        columns = result.split('class="vote-column"')[1:]
        self.assertEqual([column.count('class="vote-card') for column in columns], [5, 3])
        first_card = columns[0].split('class="vote-card')[1]
        self.assertIn('--share:28.57%', first_card)
        self.assertIn('Guessed by Player 1, Player 2. 2 of 7 guesses.', first_card)
        self.assertIn('🐸', first_card)
        self.assertIn('🐱', first_card)
        self.assertIn('vote-author">😀 Player 0', first_card)
        self.assertIn('✓ Correct', first_card)
        self.assertIn('vote-author">🦊 Player 5', columns[1])

    @patch('ui.game_flow.visual.question_card')
    @patch('ui.game_flow.st')
    @patch('ui.game_flow.common.show_player_scores')
    def test_two_player_reveal_shows_both_answers_and_both_scores(self, show_scores, st, question_card):
        st.container.return_value = MagicMock()
        st.button.return_value = False
        flow = GameFlow(Mock(), Mock(), Mock())
        flow._render_save_question = Mock()
        players = [SimpleNamespace(player_id='a', name='Alex', emoji='😀'),
                   SimpleNamespace(player_id='b', name='Bea', emoji='🐸')]
        room = SimpleNamespace(room_code='TEST', players=players)
        state = {'question': {'question': 'Question?'}, 'selected_level': 'deep',
                 'answer_submissions': {'a': 'A < B', 'b': 'Other'},
                 'round_summary': {'listener_id': 'b', 'points': 3, 'correct': True}}
        with patch('ui.game_flow.visual.decision_status') as decision:
            flow._render_two_player_reveal(room, state, 'a', 'a', True)
        cards = ' '.join(call.args[0] for call in st.html.call_args_list)
        self.assertIn('A &lt; B', cards)
        self.assertIn('Alex (Storyteller)', cards)
        self.assertIn('Bea (Listener)', cards)
        self.assertIn('😀 Alex (Storyteller)', cards)
        self.assertIn('🐸 Bea (Listener)', cards)
        show_scores.assert_called_once_with(players, {'a': 0, 'b': 3}, prefix='+')
        decision.assert_called_once_with(True)

    @patch('ui.game_flow.visual.question_card')
    @patch('ui.game_flow.st')
    def test_two_player_listener_can_mark_ready_then_wait(self, st, question_card):
        st.container.return_value = MagicMock()
        st.button.return_value = False
        flow = GameFlow(Mock(), Mock(), Mock())
        flow._render_save_question = Mock()
        room = SimpleNamespace(room_code='TEST', players=[SimpleNamespace(player_id='a', name='Alex'),
                                        SimpleNamespace(player_id='b', name='Bea')])
        state = {'question': {'question': 'Question?'}, 'selected_level': 'shallow',
                 'answer_submissions': {'a': 'Story answer', 'b': 'Listener answer'},
                 'round_summary': {'listener_id': 'b', 'points': 1, 'correct': True}}
        with patch('ui.game_flow.visual.waiting_card') as waiting:
            flow._render_two_player_reveal(room, state, 'a', 'b', False)
            st.button.assert_called_once()
            state['reveal_ready'] = ['b']
            flow._render_two_player_reveal(room, state, 'a', 'b', False)
        waiting.assert_called_once_with('Waiting for the next turn…', 'Waiting for the host or Storyteller to continue.')

    @patch('ui.game_flow.visual.question_card')
    @patch('ui.game_flow.st')
    def test_two_player_judgment_escapes_answer_and_name(self, st, question_card):
        st.button.return_value = False
        flow = GameFlow(Mock(), Mock(), Mock())
        flow._render_save_question = Mock()
        room = SimpleNamespace(room_code='TEST', players=[SimpleNamespace(player_id='a', name='Alex'),
                                                         SimpleNamespace(player_id='b', name='B < C')])
        state = {'question': {'question': 'Question?'},
                 'answer_submissions': {'a': '<story>', 'b': '<listener>'}}
        flow._render_two_player_judgment(room, state, 'a', 'a')
        cards = ' '.join(call.args[0] for call in st.html.call_args_list)
        self.assertIn('&lt;story&gt;', cards)
        self.assertIn('B &lt; C', cards)
        self.assertIn('&lt;listener&gt;', cards)
        self.assertIn("Does B &lt; C's answer match what you meant?", cards)
        self.assertEqual([call.args[0] for call in st.button.call_args_list], ['Correct', 'Not quite'])


if __name__ == '__main__':
    unittest.main()
