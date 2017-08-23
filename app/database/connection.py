from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.schema import Base


class Connection():
    _Session = None

    @classmethod
    def create(cls, url: str):
        """
        Initialize the database connection session given a url.
        :param url: The url for connecting to a database.
        """
        # Allow for multithreading so we can share this session amoung different threads
        # We do this so UnhandledExceptionHandler can use this session to perform a clean up
        engine = create_engine(url, connect_args={'check_same_thread': False}, echo=False)
        Base.metadata.create_all(engine, checkfirst=True)
        cls._Session = sessionmaker(bind=engine)

    @classmethod
    def get(cls):
        return cls._Session() if cls._Session else None
