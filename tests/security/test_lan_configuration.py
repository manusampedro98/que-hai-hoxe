import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.main import create_app


@pytest.mark.parametrize('address',['0.1.2.3','127.0.0.1','169.254.1.2','8.8.8.8','0.0.0.0','224.0.0.1'])
def test_lan_requires_rfc1918(monkeypatch,address):
    monkeypatch.setenv('QHH_LAN_IP',address)
    monkeypatch.setenv('QHH_MOBILE_IP','10.77.0.31')
    with pytest.raises(ValueError):Settings.from_env()


def test_lan_needs_exact_mobile_and_ignores_forwarded_headers(monkeypatch):
    monkeypatch.setenv('QHH_LAN_IP','10.77.0.30')
    monkeypatch.delenv('QHH_MOBILE_IP',raising=False)
    with pytest.raises(ValueError):Settings.from_env()
    monkeypatch.setenv('QHH_MOBILE_IP','10.77.0.31')
    monkeypatch.setenv('QHH_DEMO','1')
    app=create_app(Settings.from_env())
    allowed=TestClient(app,base_url='http://10.77.0.30',client=('10.77.0.31',12345))
    denied=TestClient(app,base_url='http://10.77.0.30',client=('10.77.0.32',12345))
    assert allowed.get('/').status_code==200
    response=denied.get('/',headers={'X-Forwarded-For':'10.77.0.31'})
    assert response.status_code==403 and "script-src 'self'" in response.headers['Content-Security-Policy']
