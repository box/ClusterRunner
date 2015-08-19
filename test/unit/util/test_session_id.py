from test.framework.base_unit_test_case import BaseUnitTestCase
from app.util.session_id import SessionId


class TestSessionId(BaseUnitTestCase):
    def test_get_should_return_same_string_on_repeated_calls(self):
        session_id = SessionId.get()
        self.assertEquals(session_id, SessionId.get())
