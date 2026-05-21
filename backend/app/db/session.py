from urllib.parse import urlsplit

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

database_url = settings.sqlalchemy_database_url
parsed_database_url = urlsplit(database_url)

engine_kwargs = {
    "pool_pre_ping": True,
    "pool_timeout": 10,
    "pool_recycle": 1800,
}

if parsed_database_url.scheme.startswith("postgresql"):
    engine_kwargs["connect_args"] = {
        "connect_timeout": 10,
        "options": "-c statement_timeout=25000",
    }

engine = create_engine(database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
