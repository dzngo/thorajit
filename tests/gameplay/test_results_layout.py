import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ui.game_flow import GameFlow
from ui import visual


class ResultsLayoutTests(unittest.TestCase):
    @patch('ui.visual.st')
    def test_winner_announcement_includes_ties_scores_and_escaped_names(self, st):
        winners = [SimpleNamespace(player_id='a', name='Alex <friend>', emoji='😀'),
                   SimpleNamespace(player_id='b', name='Bea', emoji='🐱')]
        visual.winner_announcement(winners, {'a': 12, 'b': 12})
        markup = st.html.call_args.args[0]
        self.assertIn("It's a tie!", markup)
        self.assertIn('😀 Alex &lt;friend&gt;', markup)
        self.assertIn('🐱 Bea', markup)
        self.assertEqual(markup.count('12 pts'), 2)
        self.assertIn('role="status"', markup)
        self.assertIn('unfold-shape left', markup)
        self.assertIn('unfold-shape right', markup)
        self.assertNotIn('winner-petal', markup)
    @patch('ui.game_flow.st')
    def test_ending_before_first_completed_round_does_not_announce_winners(self, st):
        st.button.return_value = False
        flow = GameFlow(Mock(), Mock(), Mock())
        flow._save_state = Mock()
        room = SimpleNamespace(room_code='TEST', players=[SimpleNamespace(player_id='a', name='Alex'),
                                        SimpleNamespace(player_id='b', name='Bea')])
        state = {'scores': {'a': 0, 'b': 0}, 'completed_rounds': []}

        flow._finalize_results(room, state, manual=True)
        self.assertEqual(state['winners'], [])
        st.reset_mock()
        st.button.return_value = False
        st.session_state.get.return_value = False
        flow._render_results(room, state, True)

        st.success.assert_not_called()
        st.info.assert_called_once_with('No rounds were completed, so there is no winner yet.')

    def test_besties_are_grouped_by_five_and_names_are_preserved(self):
        players = [SimpleNamespace(player_id=str(i), name=f'Player:{i} <friend>') for i in range(12)]
        room = SimpleNamespace(players=players)
        state = {'completed_rounds': [{'storyteller_id': '0', 'listener_ids': ['1'],
                                       'guesses': {'1': {'label': 'A'}}, 'correct_listener_ids': ['1']}]}
        markup = GameFlow(Mock(), Mock(), Mock())._build_arcade_statistics_html(room, state)
        columns = markup.split("class='wg-results-bestie-column'")[1:]
        self.assertEqual([column.count("class='wg-results-bestie-card'") for column in columns], [5, 5, 2])
        self.assertIn('Player:0 &lt;friend&gt;', columns[0])
        self.assertIn('Player:5 &lt;friend&gt;', columns[1])
        self.assertIn("aria-label='Certified Besties'", markup)
        self.assertIn('Scroll sideways to see all players', markup)
        self.assertEqual(markup.count('<details'), 2)
        self.assertNotIn('<details class=\'wg-results-panel\' open>', markup)
        for title in ('Mind Reader', 'Wrong With Confident', 'Best Impostor', '404 Personality',
                      'No Incognito Mode', 'Group Telepathy Score', 'Certified Besties'):
            with self.subTest(title=title):
                self.assertIn(title, markup)

    def test_empty_game_keeps_all_highlights_and_each_players_bestie_status(self):
        players = [SimpleNamespace(player_id=str(i), name=f'Player {i}') for i in range(8)]
        markup = GameFlow(Mock(), Mock(), Mock())._build_arcade_statistics_html(
            SimpleNamespace(players=players), {'completed_rounds': []})
        self.assertIn('No completed rounds yet.', markup)
        self.assertIn('Certified Besties', markup)
        self.assertEqual(markup.count('No certified bestie yet.'), 8)
        self.assertEqual(markup.count('Not enough data.'), 6)
        for title in ('Mind Reader', 'Wrong With Confident', 'Best Impostor', '404 Personality',
                      'No Incognito Mode', 'Group Telepathy Score'):
            self.assertIn(title, markup)


if __name__ == '__main__':
    unittest.main()
