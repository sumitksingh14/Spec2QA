import os
import ssl
import urllib.parse as _urlparse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:////tmp/storytotest.db")

# Heroku / older Postgres URLs use postgres:// — SQLAlchemy needs postgresql://
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

connect_args = {}

# Use pg8000 (pure-Python, no pg_config needed) when connecting to Postgres
if SQLALCHEMY_DATABASE_URL.startswith("postgresql://") or SQLALCHEMY_DATABASE_URL.startswith("postgresql+"):
    if "+" not in SQLALCHEMY_DATABASE_URL.split("://")[0]:
        SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgresql://", "postgresql+pg8000://", 1)

    # pg8000 expects SSL via ssl_context parameter rather than unsupported query string parameters
    _parsed = _urlparse.urlparse(SQLALCHEMY_DATABASE_URL)
    _qs = _urlparse.parse_qs(_parsed.query, keep_blank_values=True)
    ssl_requested = "sslmode" in _qs or "ssl" in _qs or "neon.tech" in SQLALCHEMY_DATABASE_URL
    _qs.pop("sslmode", None)
    _qs.pop("channel_binding", None)
    _qs.pop("ssl", None)

    SQLALCHEMY_DATABASE_URL = _urlparse.urlunparse(
        _parsed._replace(query=_urlparse.urlencode(_qs, doseq=True))
    )

    if ssl_requested:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl_context"] = ssl_ctx

elif SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
