from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.schema import Base


class Connection:
    _session_maker = None

    @classmethod
    def create(cls, url: str):
        """
        Initialize the single database connection session given a url.
        :param url: The url for connecting to a database.
        """
        # Allow for multithreading so we can share this session amoung different threads
        # We do this so UnhandledExceptionHandler can use this session to perform a clean up
        engine = create_engine(url, connect_args={'check_same_thread': False}, echo=False)
        Base.metadata.create_all(engine, checkfirst=True)
        cls._session_maker = sessionmaker(bind=engine)

    @classmethod
    @contextmanager
    def get(cls):
        session = cls._session_maker()
        try:
            yield session
            session.commit()
        except:
            session.rollback()
            raise
        finally:
            session.close()
