import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

from ui import common
from ui.join_flow import JoinFlow


class RoomSummaryUITests(unittest.TestCase):
    def room(self, private=True):
        return SimpleNamespace(name='Secret <name>', room_code='ABCDE', is_private=private,
                               players=[object(), object()], started=False, game_state={},
                               settings=SimpleNamespace(language='en', max_score=10, llm_model='default'))

    @patch('ui.common.st')
    def test_private_room_name_is_visible_to_players_and_code_to_host(self, st):
        st.container.return_value = MagicMock()
        common.show_room_summary(self.room())
        self.assertIn('Secret &lt;name&gt;', st.html.call_args.args[0])
        self.assertNotIn('ABCDE', st.html.call_args.args[0])
        st.reset_mock()
        st.container.return_value = MagicMock()
        common.show_room_summary(self.room(), show_private_name=True)
        self.assertIn('Secret &lt;name&gt;', st.html.call_args.args[0])
        self.assertIn('<dt>Room code</dt><dd>ABCDE</dd>', st.html.call_args.args[0])

    def test_room_selector_uses_private_code_or_public_name(self):
        flow = JoinFlow(None)
        self.assertEqual(flow._format_room_option(self.room()), 'ABCDE')
        self.assertEqual(flow._format_room_option(self.room(private=False)), 'Secret <name>')
        active = self.room()
        active.started = True
        self.assertEqual(flow._format_room_option(active), 'ABCDE · In game')

    @patch('ui.join_flow.common.show_room_summary')
    @patch('ui.join_flow.st')
    def test_open_lobbies_are_listed_before_games_in_progress(self, st, show_summary):
        active = self.room(private=False)
        active.room_code, active.started, active.updated_at = 'ACTIVE', True, 3
        older = self.room(private=False)
        older.room_code, older.updated_at = 'OLD', 1
        newer = self.room(private=False)
        newer.room_code, newer.updated_at = 'NEW', 2
        service = Mock()
        service.list_rooms.return_value = [active, older, newer]
        st.button.return_value = False
        st.selectbox.side_effect = lambda _label, options, **_kwargs: options[0]
        with patch.object(JoinFlow, 'state', new_callable=lambda: property(lambda self: {})):
            JoinFlow(service)._render_room_list()
        self.assertEqual(st.selectbox.call_args.kwargs['options'], ['NEW', 'OLD', 'ACTIVE'])
        show_summary.assert_called_once_with(newer)


if __name__ == '__main__':
    unittest.main()
