import unittest
from types import SimpleNamespace
from unittest.mock import patch

from models import PlayerRole
from ui import common


class PlayerColumnsTests(unittest.TestCase):
    def players(self, count):
        return [SimpleNamespace(player_id=str(i), name=f'Player <{i}>', emoji='🐸',
                                role=PlayerRole.HOST if i == 0 else PlayerRole.JOINER)
                for i in range(count)]

    @patch('ui.common.st')
    def test_roster_groups_players_in_order_and_escapes_names(self, st):
        common.show_players(self.players(16), current_player_id='0')
        result = st.html.call_args.args[0]
        columns = result.split('class="player-column"')[1:]
        self.assertEqual(len(columns), 4)
        self.assertEqual([column.count('role="listitem"') for column in columns], [5, 5, 5, 1])
        self.assertIn('Player &lt;0&gt; (Host) (You)', columns[0])
        self.assertIn('Player &lt;5&gt;', columns[1])
        self.assertIn('tabindex="0"', result)
        st.caption.assert_called_once()

    @patch('ui.common.st')
    def test_round_points_include_zero_for_every_player(self, st):
        players = self.players(8)
        common.show_player_scores(players, {'1': 3}, prefix='+')
        result = st.html.call_args.args[0]
        self.assertEqual(result.count('role="listitem"'), 8)
        self.assertEqual(result.count('<strong>+0</strong>'), 7)
        self.assertIn('<strong>+3</strong>', result)


if __name__ == '__main__':
    unittest.main()
