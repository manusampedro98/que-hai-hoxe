from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app
from app.importers.pipeline import import_candidates


def test_http_catalogue_works_without_network(database,candidate,monkeypatch,catalogue_clock):
    import_candidates(database,[candidate],[],'manual')
    import socket
    def no_network(*args,**kwargs):raise AssertionError('La consulta no debe utilizar sockets')
    monkeypatch.setattr(socket,'create_connection',no_network)
    monkeypatch.setattr(socket,'getaddrinfo',no_network)
    client=TestClient(create_app(Settings(db_path=database),clock=catalogue_clock),base_url='http://localhost')
    for path in ['/','/api/events','/api/municipalities','/static/css/app.css','/static/js/app.js','/static/js/rules.mjs','/static/js/map.js','/static/vendor/leaflet/leaflet.js','/static/vendor/leaflet/images/empty.gif','/static/icons/radar.svg']:
        assert client.get(path).status_code==200
    eid=client.get('/api/events').json()['events'][0]['id']
    assert client.get('/events/'+eid).status_code==200
    assert client.get('/api/events/'+eid).status_code==200
