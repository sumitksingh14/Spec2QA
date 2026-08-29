import os
import ssl
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker, declarative_base

SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:////tmp/storytotest.db")

connect_args = {}

# Convert Postgres URLs to pg8000 and strip unsupported query params (sslmode, channel_binding)
if SQLALCHEMY_DATABASE_URL.startswith("postgres://") or SQLALCHEMY_DATABASE_URL.startswith("postgresql://") or SQLALCHEMY_DATABASE_URL.startswith("postgresql+"):
    url_obj = make_url(SQLALCHEMY_DATABASE_URL)
    engine_url = url_obj.set(drivername="postgresql+pg8000", query={})

    # Neon and cloud Postgres instances require SSL via ssl_context
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    connect_args["ssl_context"] = ssl_ctx

elif SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine_url = SQLALCHEMY_DATABASE_URL
    connect_args["check_same_thread"] = False
else:
    engine_url = SQLALCHEMY_DATABASE_URL

engine = create_engine(engine_url, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def init_db():
    Base.metadata.create_all(bind=engine)
    try:
        with engine.connect() as conn:
            migration_cols = [
                ("stories", "clarified_description", "TEXT"),
                ("stories", "generation_meta_json", "TEXT"),
                ("stories", "excluded_ac_ids_json", "TEXT"),
                ("stories", "content_hash", "VARCHAR(64)"),
                ("stories", "version", "INTEGER DEFAULT 1"),
                ("test_cases", "behavior_context_json", "TEXT"),
                ("test_cases", "run_id", "INTEGER"),
                ("test_cases", "approval_status", "VARCHAR(32) DEFAULT 'Draft'"),
                ("test_cases", "assigned_to", "VARCHAR(255)"),
            ]
            for table, col, col_type in migration_cols:
                try:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type}"))
                    conn.commit()
                except Exception:
                    pass
    except Exception as e:
        print(f"[database] Note on schema auto-migration: {e}")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
