from datetime import datetime, date
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
from app.services import interval, price_label, TZ


def test_demo_is_explicit_and_prices():
    client = TestClient(create_app(Settings(demo=True)), base_url="http://localhost")
    assert 'Datos de demostración' in client.get('/').text
    data = client.get('/api/events').json()
    assert data['demo_mode'] and len(data['events']) == 7
    assert {price_label(e['price']) for e in data['events']} == {'???', 'Gratis', '15 €', 'Desde 15 €'}
    for event in data['events']:
        detail = client.get('/events/' + event['id'])
        assert detail.status_code == 200
        assert price_label(event['price']) in detail.text
    assert client.get('/events/missing').status_code == 404


def test_local_days_and_dst():
    for today, expected in [('2026-10-30','2026-10-31'), ('2026-10-31','2026-10-31'), ('2026-11-01','2026-10-31'), ('2026-12-31','2027-01-02')]:
        assert interval(date.fromisoformat(today), 'weekend')[0].isoformat() == expected
    for day, hours in [('2026-03-29',23),('2026-10-25',25)]:
        first,last = interval(date.fromisoformat(day), 'today')
        a=datetime.combine(first,datetime.min.time(),TZ)
        b=datetime.combine(last,datetime.min.time(),TZ)
        assert (b.timestamp()-a.timestamp())/3600 == hours
