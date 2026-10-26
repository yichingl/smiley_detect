from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import Engine

from app.database import engine
from app.models import Base


def upgrade_saved_column(database_engine: Engine = engine) -> bool:
    """Add the task saved-state column to an existing database without dropping data."""
    Base.metadata.create_all(bind=database_engine)

    columns = {column["name"] for column in inspect(database_engine).get_columns("inference_tasks")}
    if "saved" in columns:
        return False

    try:
        with database_engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE inference_tasks "
                "ADD COLUMN saved INTEGER NOT NULL DEFAULT 0 "
                "CHECK (saved IN (0, 1, 2))"
            )
    except SQLAlchemyError:
        columns = {column["name"] for column in inspect(database_engine).get_columns("inference_tasks")}
        if "saved" in columns:
            return False
        raise
    return True


if __name__ == "__main__":
    changed = upgrade_saved_column()
    print("Added inference_tasks.saved column." if changed else "inference_tasks.saved already exists.")
