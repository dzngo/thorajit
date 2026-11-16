import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from models import RoomSettings
from services.room_service import RoomService
from storage.room_repository import RoomRepository


class AtomicRoomSaveTests(unittest.TestCase):
    def test_failed_write_keeps_previous_room_file_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rooms.json'
            rooms = RoomService(RoomRepository(path))
            room = rooms.create_room('Alex', 'Test', RoomSettings(), is_private=False, emoji='😀')
            before = path.read_bytes()
            def fail_after_partial_write(_data, file, **_kwargs):
                file.write('[{')
                raise OSError('simulated storage failure')
            with patch('storage.room_repository.json.dump', side_effect=fail_after_partial_write):
                with self.assertRaises(OSError):
                    rooms.update_max_score(room, 20)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(rooms.get_room_by_code(room.room_code).settings.max_score, 100)
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])


APP = '''
import copy
import streamlit as st
from types import SimpleNamespace
from unittest.mock import Mock
from services.game_service import GameStateConflictError
from ui.game_flow import GameFlow
if 'game' not in st.session_state:
    st.session_state.game = {'phase':'answer_entry', 'round':1, 'game_mode':'two_player',
        'selected_level':'shallow', 'question':{'question':'Question?'},
        'answer_submissions':{'a':'Original answer'}}
players=[SimpleNamespace(player_id='a',name='Alex'),SimpleNamespace(player_id='b',name='Bea')]
room=SimpleNamespace(room_code='TEST',players=players,settings=SimpleNamespace(language='en'))
service=Mock()
service.set_state.side_effect=GameStateConflictError('changed')
flow=GameFlow(Mock(),service,Mock())
flow._render_save_question=lambda *args: None
flow._render_answer_phase(room,copy.deepcopy(st.session_state.game),'a','a',False)
'''

QUESTION_APP = '''
import copy
import streamlit as st
from types import SimpleNamespace
from unittest.mock import Mock
from services.game_service import GameStateConflictError
from ui.game_flow import GameFlow
if 'game' not in st.session_state:
    st.session_state.game = {'phase':'question_generation', 'selected_theme':'Friends',
        'selected_level':'shallow', 'question':{'question':'Original?', 'question_en':'Original?'},
        'storyteller_order':['a'], 'turn_index':0}
room=SimpleNamespace(room_code='TEST', settings=SimpleNamespace(language='en'))
service=Mock()
service.set_state.side_effect=GameStateConflictError('changed')
GameFlow(Mock(),service,Mock())._render_question_phase(room,copy.deepcopy(st.session_state.game),'a','a')
'''


class SaveRecoveryUITests(unittest.TestCase):
    def test_translation_error_keeps_edited_question_and_gives_clear_guidance(self):
        source = QUESTION_APP.replace("SimpleNamespace(language='en')", "SimpleNamespace(language='fr')").replace(
            "GameFlow(Mock(),service,Mock())._render_question_phase(room,copy.deepcopy(st.session_state.game),'a','a')",
            "flow=GameFlow(Mock(),service,Mock())\n"
            "flow.llm_service.translate_text_with_trace.return_value={'error':'provider detail'}\n"
            "flow._render_question_phase(room,copy.deepcopy(st.session_state.game),'a','a')",
        )
        app = AppTest.from_string(source).run()
        app.button(key='TEST_question_edit').click().run()
        app.text_area[0].input('Ma question ?').run()
        app.button(key='TEST_question_confirm').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_area[0].value, 'Ma question ?')
        self.assertTrue(any("couldn't translate" in alert.value for alert in app.error))
        self.assertFalse(any('provider detail' in alert.value for alert in app.error))

    def test_successful_theme_change_leaves_question_editor(self):
        source = QUESTION_APP.replace(
            "service.set_state.side_effect=GameStateConflictError('changed')",
            "def save(room, state):\n    st.session_state.game = state\nservice.set_state.side_effect=save",
        ).replace(
            "GameFlow(Mock(),service,Mock())._render_question_phase(room,copy.deepcopy(st.session_state.game),'a','a')",
            "if st.session_state.game['phase'] == 'question_generation':\n"
            "    GameFlow(Mock(),service,Mock())._render_question_phase(room,copy.deepcopy(st.session_state.game),'a','a')\n"
            "else:\n    st.write('Choose a theme')",
        )
        app = AppTest.from_string(source).run()
        app.button(key='TEST_question_edit').click().run()
        app.text_area[0].input('My edited question?').run()
        app.button(key='TEST_question_change_theme').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state.game['phase'], 'theme_selection')
        self.assertFalse(app.text_area)

    def test_failed_theme_change_preserves_edited_question(self):
        app = AppTest.from_string(QUESTION_APP).run()
        app.button(key='TEST_question_edit').click().run()
        app.text_area[0].input('My edited question?').run()
        app.button(key='TEST_question_change_theme').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('not saved' in alert.value for alert in app.error))
        self.assertEqual(app.text_area[0].value, 'My edited question?')
        self.assertTrue(app.session_state['TEST_question_text_editing'])

    def test_storage_error_keeps_the_edited_answer(self):
        app = AppTest.from_string(APP.replace("GameStateConflictError('changed')", "OSError('offline')")).run()
        app.button(key='TEST_modify_answer_a').click().run()
        app.text_area[0].input('Updated answer').run()
        next(button for button in app.button if button.label == 'Save changes').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('could not be saved' in alert.value for alert in app.error))
        self.assertEqual(app.text_area[0].value, 'Updated answer')
        self.assertFalse(app.text_area[0].disabled)

    def test_conflicted_edit_stays_editable_and_keeps_the_new_text(self):
        app = AppTest.from_string(APP).run()
        app.button(key='TEST_modify_answer_a').click().run()
        app.text_area[0].input('Updated answer').run()
        next(button for button in app.button if button.label == 'Save changes').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any('not saved' in alert.value for alert in app.error))
        self.assertEqual(app.text_area[0].value, 'Updated answer')
        self.assertFalse(app.text_area[0].disabled)
        self.assertTrue(app.session_state['TEST_answer_input_a_1_editing'])


if __name__ == '__main__':
    unittest.main()
