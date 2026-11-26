import ipaddress
import socket
import time
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
from app.schemas.event import Candidate,public_link
from app.importers.pipeline import import_candidates
from app.importers.transport import resolve_public,get_page,SourceError,MAX_RESPONSE,read_limited,PinnedHTTPS


@pytest.mark.parametrize('url',['javascript:alert(1)','data:text/html,test','file:///C:/Windows','http://localhost/x','http://127.0.0.1','http://[::1]','http://169.254.169.254/','https://a:'+'b@www.cultura.gal/','https://www.cultura.gal\\@localhost/','http://2130706433','http://0x7f000001','https://a.local/','https://www.cultura.gal/%0a' ])
def test_unsafe_links(url):
    assert public_link(url) is None


def test_xss_sql_and_remote_writes(database,candidate,catalogue_clock):
    row=candidate.model_dump(mode='json')
    row.update(title='<script>alert(1)</script>',description='<img src=x onerror=alert(2)>',tickets_url='javascript:alert(3)',source={'name':'Prueba','url':'file:///secret'})
    import_candidates(database,[Candidate.model_validate(row)],[],'manual')
    client=TestClient(create_app(Settings(db_path=database),clock=catalogue_clock),base_url='http://localhost')
    data=client.get('/api/events').json()['events'];eid=data[0]['id']
    body=client.get('/events/'+eid).text
    assert '<script>alert' not in body and '&lt;script&gt;' in body
    assert '<img src=x' not in body and 'javascript:' not in body
    before=database.read_bytes()
    for path in ['/','/api/events','/api/events/'+eid,'/events/'+eid,'/health','/api/municipalities']:
        for method in ['POST','PUT','PATCH','DELETE']:assert client.request(method,path).status_code==405
    for path in ['/admin','/sync','/import','/upload','/data/catalog.sqlite3','/.env','/h0/README.md','/static/../config.py','/events/%27%20OR%201=1--']:
        assert client.get(path).status_code==404
    assert database.read_bytes()==before


def test_headers_host_and_errors():
    client=TestClient(create_app(Settings(demo=True)),base_url='http://localhost')
    response=client.get('/')
    assert "script-src 'self'" in response.headers['content-security-policy']
    assert "unsafe-inline" not in response.headers['content-security-policy']
    assert response.headers['x-content-type-options']=='nosniff'
    assert response.headers['referrer-policy']=='no-referrer'
    assert 'access-control-allow-origin' not in response.headers
    assert client.get('/',headers={'Host':'evil.example'}).status_code==400
    assert client.get('/',headers={'Host':'localhost.evil.example'}).status_code==400
    assert client.get('/openapi.json').status_code==404
    assert client.get('/docs').status_code==404


@pytest.mark.parametrize('address',['127.0.0.1','10.0.0.1','169.254.169.254','::1','::ffff:127.0.0.1','::ffff:8.8.8.8','192.168.1.2','100.64.0.1','0.0.0.0','224.0.0.1'])
def test_dns_rejects_internal(monkeypatch,address):
    family=socket.AF_INET6 if ':' in address else socket.AF_INET
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(family,socket.SOCK_STREAM,0,'',(address,443))])
    with pytest.raises(SourceError):resolve_public('www.cultura.gal')


def test_dns_all_answers_and_pinned_connection(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,0,'',('8.8.8.8',443)),(socket.AF_INET,socket.SOCK_STREAM,0,'',('127.0.0.1',443))])
    with pytest.raises(SourceError):resolve_public('www.cultura.gal')
    calls=[]
    class Sock:
        def settimeout(self,value):pass
        def connect(self,addr):calls.append(addr)
        def close(self):pass
    class TLS:
        def wrap_socket(self,sock,server_hostname):calls.append(server_hostname);return sock
    monkeypatch.setattr(socket,'socket',lambda *a:Sock())
    conn=PinnedHTTPS([(socket.AF_INET,('8.8.8.8',443))],5)
    conn._context=TLS()
    # The rebinding DNS answer is never re-resolved during connect.
    conn.connect()
    assert calls==[('8.8.8.8',443),'www.cultura.gal']


@pytest.mark.parametrize('status',[301,302,307,308,401,403])
def test_redirects_and_denials_are_not_followed(status):
    calls=[]
    class Response:
        def getheader(self,key,default=None):return {'Content-Type':'application/json','Location':'http://127.0.0.1/secret'}.get(key,default)
    response=Response();response.status=status
    class Connection:
        sock=None
        def request(self,*args,**kwargs):calls.append(args)
        def getresponse(self):return response
        def close(self):pass
    with pytest.raises(SourceError):get_page({'idioma':'gl','limite':100,'paxina':0},time.monotonic()+5,resolver=lambda *a,**k:[],connection_factory=lambda *a:Connection())
    assert len(calls)==1


def test_response_limits():
    class Response:
        def getheader(self,key,default=None):return str(MAX_RESPONSE+1) if key=='Content-Length' else default
    with pytest.raises(SourceError):read_limited(Response(),time.monotonic()+1)
