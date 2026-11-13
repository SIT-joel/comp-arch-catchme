"""Database engine and session management."""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def _engine():
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


engine = _engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def database_kind() -> str:
    """Return 'postgresql', 'sqlite', ... — used to label test coverage honestly."""
    return engine.dialect.name


def check_database(db: Session) -> bool:
    db.execute(text("SELECT 1"))
    return True
