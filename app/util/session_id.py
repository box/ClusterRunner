import uuid


class SessionId(object):
    EXPECTED_SESSION_HEADER_KEY = 'Expected-Session-Id'
    SESSION_HEADER_KEY = 'Session-Id'

    _session_id = None

    @classmethod
    def get(cls):
        """
        :return: the unique, generated session id string.
        :rtype: str
        """
        if cls._session_id is None:
            cls._session_id = str(uuid.uuid4())
        return cls._session_id
