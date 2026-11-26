import pytest
from sqlalchemy import text
from fastapi.testclient import TestClient
from app.db.repository import init_db, engine_for
from app.main import create_app
from app.config import Settings


def test_no_creation_on_start(tmp_path):
    path=tmp_path/'missing.sqlite3'
    client=TestClient(create_app(Settings(db_path=path)),base_url='http://localhost')
    assert client.get('/').status_code==200
    assert client.get('/api/events').status_code==503
    assert not path.exists()


def test_init_readonly_and_empty_api(tmp_path):
    path=tmp_path/'catalog.sqlite3'
    init_db(path)
    with pytest.raises(FileExistsError):init_db(path)
    engine=engine_for(path)
    with engine.connect() as c:
        assert c.scalar(text('PRAGMA query_only'))==1
        with pytest.raises(Exception):c.execute(text("INSERT INTO events (id,title,payload) VALUES ('x','x','{}')"))
    engine.dispose()
    client=TestClient(create_app(Settings(db_path=path)),base_url='http://localhost')
    response=client.get('/api/events')
    assert response.status_code==200
    assert response.json()['events']==[]
    assert response.json()['last_successful_import_at'] is None
    assert client.get('/api/events/missing').status_code==404
