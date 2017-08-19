from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class Connection():
    _Session = None

    @classmethod
    def get(cls, url):
        if cls._Session is None:
            engine = create_engine(url, echo=False)
            cls._Session = sessionmaker(bind=engine)
        return cls._Session()
