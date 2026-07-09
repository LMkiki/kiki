import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def get_engine():
    url = os.environ.get("DATABASE_URL", "mysql+pymysql://root:root@127.0.0.1:3306/move_car")
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


def get_session_factory():
    engine = get_engine()
    return sessionmaker(bind=engine, expire_on_commit=False)
