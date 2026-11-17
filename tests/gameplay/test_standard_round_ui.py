"""A three-session UI test using an isolated room and real game services."""
import copy
import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from models import RoomSettings
from services.game_service import GameService
from services.room_service import RoomService
from storage.room_repository import RoomRepository

APP = '''
import streamlit as st
from pathlib import Path
from unittest.mock import Mock
from storage.room_repository import RoomRepository
from services.room_service import RoomService
from services.game_service import GameService
from ui.game_flow import GameFlow
rooms = RoomService(RoomRepository(Path(st.session_state.path)))
GameFlow(rooms, GameService(rooms), Mock()).render()
'''


class StandardRoundUITests(unittest.TestCase):
    def test_two_players_finish_equal_turns_and_reach_results(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rooms.json'
            repo = RoomRepository(path)
            rooms = RoomService(repo)
            room = rooms.create_room('Alex', 'Pair', RoomSettings(max_score=1, max_score_customized=True),
                                     is_private=False, emoji='😀')
            rooms.add_player(room, 'Bea', emoji='🐱')
            game = GameService(rooms)
            game.start_game(room)
            ids = [player.player_id for player in room.players]
            state = copy.deepcopy(room.game_state)
            state.update(storyteller_order=ids, turn_index=0, phase='answer_entry',
                         selected_level='shallow', selected_theme='Random 🎲',
                         question={'question': 'What is your favorite?', 'question_en': 'What is your favorite?'})
            game.set_state(room, state)
            sessions = {}
            for player in room.players:
                app = AppTest.from_string(APP, default_timeout=15)
                app.session_state.path = str(path)
                app.session_state.active_room_code = room.room_code
                app.session_state.player_profile = {'player_id': player.player_id, 'name': player.name}
                sessions[player.player_id] = app

            for turn, storyteller in enumerate(ids):
                if turn:
                    chooser = sessions[storyteller].run()
                    chooser.button(key=f'{room.room_code}_vibe_confirm').click().run()
                    chooser.button(key=f'{room.room_code}_question_confirm').click().run()
                for index, player_id in enumerate(ids):
                    app = sessions[player_id].run()
                    app.text_area[0].input(f'Answer {turn} {index}').run()
                    next(button for button in app.button if button.label == 'Submit answer').click().run()
                    self.assertFalse(app.exception)
                judge = sessions[storyteller].run()
                judge.button(key=f'{room.room_code}_judgment_correct').click().run()
                self.assertFalse(judge.exception)
                self.assertEqual(repo.get_by_code(room.room_code).game_state['phase'], 'reveal')
                if not turn:
                    self.assertFalse(repo.get_by_code(room.room_code).game_state['round_summary']['winners'])
                    judge.button(key=f'{room.room_code}_next_turn_action').click().run()
                    self.assertEqual(repo.get_by_code(room.room_code).game_state['phase'], 'theme_selection')
                    late = sessions[next(pid for pid in ids if pid != storyteller)].run()
                    self.assertIn('The reveal', [header.value for header in late.header])
                    late.button(
                        key=f'{room.room_code}_next_turn_action').click().run()
                else:
                    judge.button(key=f'{room.room_code}_view_results').click().run()
                    self.assertEqual(repo.get_by_code(room.room_code).game_state['phase'], 'results')
                    sessions[next(pid for pid in ids if pid != storyteller)].run().button(
                        key=f'{room.room_code}_view_results').click().run()
            final = repo.get_by_code(room.room_code).game_state
            self.assertEqual(final['phase'], 'results')
            self.assertEqual(set(final['winners']), set(ids))
            for app in sessions.values():
                app.run()
                self.assertIn('Final scoreboard', [header.value for header in app.header])
                self.assertFalse(app.exception)

    def test_legacy_level_step_uses_combined_setup_and_preserves_theme(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rooms.json'
            repo = RoomRepository(path)
            rooms = RoomService(repo)
            room = rooms.create_room('Alex', 'Friends', RoomSettings(), is_private=False, emoji='😀')
            rooms.add_player(room, 'Bea', emoji='🐸')
            GameService(rooms).start_game(room)
            room.game_state['phase'] = 'level_selection'
            room.game_state['selected_theme'] = 'Random 🎲'
            repo.save(room)
            storyteller = room.game_state['storyteller_order'][0]
            player = next(player for player in room.players if player.player_id == storyteller)
            app = AppTest.from_string(APP, default_timeout=15)
            app.session_state.path = str(path)
            app.session_state.active_room_code = room.room_code
            app.session_state.player_profile = {'player_id': player.player_id, 'name': player.name}
            app.run()
            self.assertFalse(app.exception)
            self.assertIn('Set the vibe', [header.value for header in app.header])
            app.button(key=f'{room.room_code}_vibe_confirm').click().run()
            self.assertFalse(app.exception)
            updated = repo.get_by_code(room.room_code).game_state
            self.assertEqual(updated['selected_theme'], 'Random 🎲')
            self.assertEqual(updated['phase'], 'question_generation')

    def test_three_sessions_play_from_theme_selection_to_reveal(self):
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
     patch('ui.game_flow.QuestionEvents', return_value=Mock()):
    Router().render()
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rooms.json'
            repo = RoomRepository(path)
            rooms = RoomService(repo)
            room = rooms.create_room('Alex', 'Friends', RoomSettings(), is_private=False, emoji='😀')
            rooms.add_player(room, 'Bea', emoji='🐸')
            rooms.add_player(room, 'Cee', emoji='🐱')
            GameService(rooms).start_game(room)
            sessions = {}
            for player in room.players:
                app = AppTest.from_string(source, default_timeout=15)
                app.session_state.path = str(path)
                app.session_state.route = 'game'
                app.session_state.active_room_code = room.room_code
                app.session_state.player_profile = {'player_id': player.player_id, 'name': player.name}
                app.run()
                self.assertFalse(app.exception)
                sessions[player.player_id] = app
            storyteller_id = room.game_state['storyteller_order'][0]
            storyteller = sessions[storyteller_id]
            storyteller.button(key=f'{room.room_code}_vibe_confirm').click().run()
            storyteller.button(key=f'{room.room_code}_question_confirm').click().run()
            for player_id, app in sessions.items():
                answer = 'Storyteller answer' if player_id == storyteller_id else f'Answer from {player_id}'
                app.run()
                app.text_area[0].input(answer).run()
                next(button for button in app.button if button.label == 'Submit answer').click().run()
                self.assertFalse(app.exception)
            for player_id, app in sessions.items():
                if player_id == storyteller_id:
                    continue
                app.run()
                self.assertNotIn(f'Answer from {player_id}', app.radio[0].options)
                app.radio[0].set_value('Storyteller answer').run()
                app.button(key=f'{room.room_code}_submit_guess_{player_id}').click().run()
                self.assertFalse(app.exception)
            storyteller.run()
            self.assertIn('The reveal', [header.value for header in storyteller.header])
            self.assertEqual(len(repo.get_by_code(room.room_code).game_state['round_summary']['guesses']), 2)

    def test_host_cannot_skip_to_guessing_without_a_storyteller_answer(self):
        app = AppTest.from_string('''
import streamlit as st
from types import SimpleNamespace
from unittest.mock import Mock
from ui.game_flow import GameFlow
if 'game' not in st.session_state:
    st.session_state.game = {'game_mode':'standard', 'round':1, 'question':{'question':'Question?'},
                             'answer_submissions':{'b':'My answer'}}
players = [SimpleNamespace(player_id='a',name='Alex'), SimpleNamespace(player_id='b',name='Bea'),
           SimpleNamespace(player_id='c',name='Cee')]
room = SimpleNamespace(room_code='TEST',players=players,settings=SimpleNamespace(language='en'))
flow = GameFlow(Mock(),Mock(),Mock())
flow._render_save_question = lambda *args: None
flow._render_answer_phase(room,st.session_state.game,'a','b',True)
''').run()
        self.assertTrue(app.button(key='host_force_guessing').disabled)
        app.session_state.game['answer_submissions']['a'] = 'Storyteller answer'
        app.run()
        self.assertFalse(app.button(key='host_force_guessing').disabled)
        self.assertFalse(app.exception)

    def test_three_players_complete_a_round_and_reach_results(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rooms.json'
            repo = RoomRepository(path)
            rooms = RoomService(repo)
            room = rooms.create_room('Alex', 'Test', RoomSettings(max_score=3, max_score_customized=True),
                                     is_private=False, emoji='😀')
            sam = rooms.add_player(room, 'Sam', emoji='🐱')
            mina = rooms.add_player(room, 'Mina', emoji='🐸')
            game = GameService(rooms)
            game.start_game(room)
            ids = [room.host_id, sam.player_id, mina.player_id]
            state = copy.deepcopy(room.game_state)
            state.update(storyteller_order=ids, turn_index=0, phase='answer_entry',
                         selected_level='shallow', selected_theme='Random 🎲',
                         question={'question': 'What is your favorite?', 'question_en': 'What is your favorite?'})
            game.set_state(room, state)
            sessions = []
            for player in room.players:
                app = AppTest.from_string(APP, default_timeout=15)
                app.session_state.path = str(path)
                app.session_state.active_room_code = room.room_code
                app.session_state.player_profile = {'player_id': player.player_id, 'name': player.name}
                app.run()
                self.assertFalse(app.exception)
                sessions.append(app)
            for app, answer in zip(sessions, ['Coffee', 'Walk', 'Music']):
                app.run()
                app.text_area[0].input(answer).run()
                next(button for button in app.button if button.label == 'Submit answer').click().run()
                self.assertFalse(app.exception)
            self.assertEqual(repo.get_by_code(room.room_code).game_state['phase'], 'guessing')
            for app, guess, own in zip(sessions[1:], ['Coffee', 'Walk'], ['Walk', 'Music']):
                app.run()
                self.assertNotIn(own, app.radio[0].options)
                app.radio[0].set_value(guess).run()
                next(button for button in app.button if button.label == 'Submit my guess').click().run()
                self.assertFalse(app.exception)
            self.assertEqual(repo.get_by_code(room.room_code).game_state['phase'], 'reveal')
            host = sessions[0].run()
            revealed = repo.get_by_code(room.room_code).game_state
            self.assertEqual(revealed['scores'], {ids[0]: 3, ids[1]: 4, ids[2]: 0})
            self.assertEqual(revealed['round_summary']['winners'], [ids[1]])
            self.assertIn('The reveal', [header.value for header in host.header])
            early = sessions[1].run()
            early.button(key=f'{room.room_code}_view_results').click().run()
            self.assertEqual(repo.get_by_code(room.room_code).game_state['phase'], 'reveal')
            self.assertTrue(any('Waiting for the final results' in item.value for item in early.get('html')))
            host.run()
            next(button for button in host.button if button.label == 'View final results').click().run()
            self.assertFalse(host.exception)
            self.assertEqual(repo.get_by_code(room.room_code).game_state['phase'], 'results')
            early.run()
            self.assertIn('Final scoreboard', [header.value for header in early.header])
            late = sessions[2].run()
            self.assertIn('The reveal', [header.value for header in late.header])
            late.button(key=f'{room.room_code}_view_results').click().run()
            self.assertFalse(late.exception)
            host.run()
            self.assertEqual(repo.get_by_code(room.room_code).game_state['phase'], 'results')
            self.assertIn('Final scoreboard', [header.value for header in host.header])
            self.assertNotIn('Room and scores', [expander.label for expander in host.expander])
            self.assertTrue(any('We have a winner!' in item.value and 'Sam' in item.value for item in host.get('html')))
            guest = sessions[1].run()
            self.assertIn('Final scoreboard', [header.value for header in guest.header])
            next(button for button in guest.button if button.label == 'Back to entry').click().run()
            self.assertEqual(guest.session_state.route, 'entry')
            next(button for button in host.button if button.label == 'Return to host lobby').click().run()
            self.assertFalse(host.exception)
            self.assertEqual(host.session_state.route, 'host')
            self.assertFalse(repo.get_by_code(room.room_code).started)


if __name__ == '__main__':
    unittest.main()
