import re
from urllib.parse import quote

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import settings

DATABASE_URL = (settings.database_url or "").strip()

# Some providers (Heroku/Railway/Supabase) hand out "postgres://", but
# SQLAlchemy requires the "postgresql://" scheme — normalise it.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]


def _encode_password(url: str) -> str:
    """URL-encode the password so special chars (@, #, /, etc.) don't break
    parsing. Matches scheme://user:password@host... and percent-encodes only
    the password segment. Leaves already-encoded or password-less URLs alone.
    """
    m = re.match(r"^(?P<scheme>[^:]+://)(?P<user>[^:/@]+):(?P<pwd>[^@]*)@(?P<rest>.+)$", url)
    if not m:
        return url
    pwd = m.group("pwd")
    # if it already looks percent-encoded, don't double-encode
    if "%" in pwd:
        return url
    encoded = quote(pwd, safe="")
    return f"{m.group('scheme')}{m.group('user')}:{encoded}@{m.group('rest')}"


DATABASE_URL = _encode_password(DATABASE_URL)

# Guard against an empty/blank DATABASE_URL (would crash create_engine):
# fall back to local SQLite so the app can still boot.
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./bookly.db"

# SQLite needs check_same_thread=False to work with FastAPI's threadpool.
# Postgres rejects this argument, so only pass it for sqlite URLs.
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
