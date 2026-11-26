from datetime import datetime, time, timezone

import pytest
from app.schemas.event import Candidate
from app.db.repository import init_db


@pytest.fixture
def database(tmp_path):
    path=tmp_path/'catalog.sqlite3'
    init_db(path)
    return path


@pytest.fixture
def candidate():
    return Candidate.model_validate(dict(external_id='test-1',title='Mostra sintética de proba',date=dict(start_date='2026-10-28'),source=dict(name='Persona de pruebas'),category='culture'))


@pytest.fixture
def catalogue_clock(candidate):
    return lambda: datetime.combine(candidate.date.start_date, time(12), timezone.utc)
