import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest
from storage.room_repository import RoomRepository, RoomStorageError
from ui import common

APP = '''
import streamlit as st
from unittest.mock import patch
from storage.room_repository import RoomStorageError
from ui import routing
if 'failed' not in st.session_state:
    st.session_state.failed = True
class Flow:
    def render(self):
        st.text_input('Your name', key='draft')
        if st.session_state.failed:
            raise RoomStorageError('simulated failure')
        st.success('Room available')
with patch('ui.routing.Router', return_value=Flow()):
    routing.run()
'''


class RoomStorageRecoveryTests(unittest.TestCase):
    def test_retry_preserves_setup_input(self):
        app = AppTest.from_string(APP).run()
        app.text_input[0].input('Sam').run()
        self.assertFalse(app.exception)
        self.assertTrue(any("couldn't load or save" in item.value for item in app.error))
        app.session_state.failed = False
        app.button(key='room_storage_retry').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.text_input[0].value, 'Sam')
        self.assertTrue(any('Room available' in item.value for item in app.success))

    @patch('ui.common.st')
    def test_background_poll_reports_failure_and_retries(self, st):
        service = Mock()
        service.get_room_by_code.side_effect = RoomStorageError('offline')
        self.assertFalse(common.room_has_changed(service, 'TEST', 'known'))
        st.warning.assert_called_once()
        service.get_room_by_code.side_effect = None
        service.get_room_by_code.return_value = SimpleNamespace(updated_at=datetime.fromisoformat('2026-01-01'))
        self.assertTrue(common.room_has_changed(service, 'TEST', 'known'))

    def test_invalid_room_data_reports_storage_error_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'rooms.json'
            path.write_text('{broken', encoding='utf-8')
            with self.assertRaises(RoomStorageError):
                RoomRepository(path).list_rooms()
            self.assertEqual(path.read_text(encoding='utf-8'), '{broken')


if __name__ == '__main__':
    unittest.main()
