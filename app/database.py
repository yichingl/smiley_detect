
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from app.models import Base

# This sets up your local SQLite database file in your project root
SQLALCHEMY_DATABASE_URL = "sqlite:///./smiley_app.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    # 1. Open a new session using your SessionLocal factory
    db = SessionLocal()
    try:
        # 2. Yield it to the FastAPI route / repository
        yield db
    finally:
        # 3. Ensure it always closes when the request finishes
        db.close()