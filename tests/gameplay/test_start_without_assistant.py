"""Core game navigation should not require an assistant API connection."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

from services.llm_service import LLMService
from storage.room_repository import RoomRepository


class AssistantAvailabilityTests(unittest.TestCase):
    def test_provider_is_initialized_only_when_needed(self):
        with patch('services.llm_service.get_llm', return_value=Mock()) as get_llm:
            service = LLMService('gemini-2.5-flash')
            get_llm.assert_not_called()
            self.assertEqual(service.selection_name, 'gemini-2.5-flash')
            service._llm
            service._llm
            get_llm.assert_called_once_with(model_name='gemini-2.5-flash')

    def test_real_entry_point_loads_when_provider_is_unavailable(self):
        app = AppTest.from_string('''
from unittest.mock import Mock, patch
import app
with patch('app.initialize_question_counters'), patch('services.llm_service.get_llm', side_effect=EnvironmentError('missing key')):
    app.main()
''').run()
        self.assertFalse(app.exception)
        self.assertIn('Create room', [button.label for button in app.button])
        self.assertIn('Join room', [button.label for button in app.button])

    def test_two_sessions_can_create_join_and_start_without_provider(self):
        source = '''
import streamlit as st
from pathlib import Path
from unittest.mock import Mock, patch
from services.room_service import RoomService
from storage.room_repository import RoomRepository
from ui.routing import Router
rooms = RoomService(RoomRepository(Path(st.session_state.path)))
with patch('ui.routing.RoomService', return_value=rooms), \\
     patch('services.llm_service.get_llm', side_effect=EnvironmentError('missing key')), \\
     patch('ui.game_flow.QuestionEvents', return_value=Mock()), \\
     patch('ui.host_flow.pick_emoji', return_value=st.session_state.emoji), \\
     patch('ui.join_flow.pick_emoji', return_value=st.session_state.emoji):
    Router().render()
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rooms.json'
            host = AppTest.from_string(source, default_timeout=15)
            host.session_state.path = str(path)
            host.session_state.emoji = '😀'
            host.session_state.route = 'host'
            host.run()
            host.text_input[0].input('Alex').run()
            host.text_input[1].input('Friends').run()
            host.button(key='room_name_next').click().run()
            self.assertFalse(host.exception)
            self.assertIn('Your room', [header.value for header in host.header])

            guest = AppTest.from_string(source, default_timeout=15)
            guest.session_state.path = str(path)
            guest.session_state.emoji = '🐸'
            guest.session_state.route = 'join'
            guest.run()
            guest.button(key='room_list_next').click().run()
            guest.text_input[0].input('Bea').run()
            guest.button(key='player_name_join').click().run()
            self.assertFalse(guest.exception)
            self.assertIn('Your room', [header.value for header in guest.header])

            host.run()
            host.number_input[0].set_value(1).run()
            next(button for button in host.button if button.label == 'Start game').click().run()
            self.assertFalse(host.exception)
            rooms = RoomRepository(path).list_rooms()
            self.assertTrue(rooms[0].started)
            self.assertEqual(rooms[0].game_state['phase'], 'theme_selection')

            guest.run()
            storyteller_id = rooms[0].game_state['storyteller_order'][0]
            storyteller = host if host.session_state.player_profile['player_id'] == storyteller_id else guest
            listener = guest if storyteller is host else host
            code = rooms[0].room_code
            storyteller.run()
            storyteller.button(key=f'{code}_vibe_confirm').click().run()
            self.assertFalse(storyteller.exception)
            self.assertIn('Your question', [header.value for header in storyteller.header])
            storyteller.button(key=f'{code}_question_confirm').click().run()
            for player, answer in ((storyteller, 'Coffee'), (listener, 'A quiet morning')):
                player.run()
                player.text_area[0].input(answer).run()
                next(button for button in player.button if button.label == 'Submit answer').click().run()
                self.assertFalse(player.exception)
            storyteller.run()
            storyteller.button(key=f'{code}_judgment_correct').click().run()
            self.assertFalse(storyteller.exception)
            self.assertEqual(RoomRepository(path).get_by_code(code).game_state['phase'], 'reveal')
            self.assertIn('The reveal', [header.value for header in storyteller.header])
            self.assertFalse(RoomRepository(path).get_by_code(code).game_state['round_summary']['winners'])
            storyteller.button(key=f'{code}_next_turn_action').click().run()
            listener.run().button(key=f'{code}_next_turn_action').click().run()

            second_storyteller, second_listener = listener, storyteller
            second_storyteller.run()
            second_storyteller.button(key=f'{code}_vibe_confirm').click().run()
            second_storyteller.button(key=f'{code}_question_confirm').click().run()
            for player, answer in ((second_storyteller, 'Sunshine'), (second_listener, 'A sunny day')):
                player.run()
                player.text_area[0].input(answer).run()
                next(button for button in player.button if button.label == 'Submit answer').click().run()
                self.assertFalse(player.exception)
            second_storyteller.run()
            second_storyteller.button(key=f'{code}_judgment_correct').click().run()
            summary = RoomRepository(path).get_by_code(code).game_state['round_summary']
            self.assertEqual(len(summary['winners']), 2)
            second_storyteller.button(key=f'{code}_view_results').click().run()
            second_listener.run().button(key=f'{code}_view_results').click().run()
            second_storyteller.run()
            self.assertFalse(second_storyteller.exception)
            self.assertIn('Final scoreboard', [header.value for header in second_storyteller.header])


if __name__ == '__main__':
    unittest.main()
