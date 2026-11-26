import sqlite3
import time
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db.models import Base, Event, ImportRun


def engine_for(path: Path, *, readonly=True):
    uri = path.resolve().as_uri() + ("?mode=ro" if readonly else "?mode=rw")

    def connect():
        conn = sqlite3.connect(uri, uri=True, timeout=3, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys=ON")
        if readonly:
            conn.execute("PRAGMA query_only=ON")
            deadline = time.monotonic() + 5
            conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        return conn

    # NullPool makes the query timeout apply separately to each request and releases Windows handles.
    from sqlalchemy.pool import NullPool
    return create_engine("sqlite://", creator=connect, poolclass=NullPool)


def init_db(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation is intentional: existing catalogues are never reset.
    with path.open("xb"):
        pass
    engine = engine_for(path, readonly=False)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()


def read_catalogue(path: Path):
    if not path.is_file():
        raise RuntimeError("Catálogo no inicializado")
    engine = engine_for(path)
    try:
        with Session(engine) as session:
            rows = list(session.scalars(select(Event).limit(10001)))
            if len(rows) > 10000:
                raise RuntimeError("Catálogo demasiado grande; no se trunca")
            events = [row.payload for row in rows]
            last = session.scalar(select(ImportRun.finished_at).where(ImportRun.status == "success").order_by(ImportRun.id.desc()).limit(1))
            return events, last
    finally:
        engine.dispose()
