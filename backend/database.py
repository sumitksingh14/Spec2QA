import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:////tmp/storytotest.db")

# Heroku / older Postgres URLs use postgres:// — SQLAlchemy needs postgresql://
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Use pg8000 (pure-Python, no pg_config needed) when connecting to Postgres
# Fall back to psycopg2 only if explicitly requested via DATABASE_URL query string
if SQLALCHEMY_DATABASE_URL.startswith("postgresql://") or SQLALCHEMY_DATABASE_URL.startswith("postgresql+"):
    # Switch to pg8000 driver if not already specified, avoids pg_config dependency
    if "+" not in SQLALCHEMY_DATABASE_URL.split("://")[0]:
        SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace(
            "postgresql://", "postgresql+pg8000://", 1
        )

connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}

# pg8000 does not support the `channel_binding` query parameter that Neon
# includes by default — strip it so the connection doesn't crash on startup.
if "channel_binding" in SQLALCHEMY_DATABASE_URL:
    import urllib.parse as _urlparse
    _parsed = _urlparse.urlparse(SQLALCHEMY_DATABASE_URL)
    _qs = _urlparse.parse_qs(_parsed.query, keep_blank_values=True)
    _qs.pop("channel_binding", None)
    SQLALCHEMY_DATABASE_URL = _urlparse.urlunparse(
        _parsed._replace(query=_urlparse.urlencode(_qs, doseq=True))
    )

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args=connect_args
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
