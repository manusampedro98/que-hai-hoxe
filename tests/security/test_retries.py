import time
import pytest
from app.importers import transport


def test_quota_is_bounded_and_retry_after_respected(monkeypatch):
    calls=[];waits=[]
    class Response:
        status=429
        def getheader(self,key,default=None):return '2' if key=='Retry-After' else default
    class Connection:
        sock=None
        def request(self,*args,**kwargs):calls.append(1)
        def getresponse(self):return Response()
        def close(self):pass
    monkeypatch.setattr(transport.time,'sleep',lambda seconds:waits.append(seconds))
    with pytest.raises(transport.SourceError):transport.get_page({'idioma':'gl','limite':100,'paxina':0},time.monotonic()+60,resolver=lambda *a,**k:[],connection_factory=lambda *a:Connection())
    assert len(calls)==3 and waits==[2,2]


def test_socket_timeouts_abort_after_two_retries(monkeypatch):
    calls=[]
    class Connection:
        sock=None
        def request(self,*args,**kwargs):calls.append(1);raise TimeoutError()
        def close(self):pass
    monkeypatch.setattr(transport.time,'sleep',lambda seconds:None)
    with pytest.raises(transport.SourceError):transport.get_page({'idioma':'gl','limite':100,'paxina':0},time.monotonic()+60,resolver=lambda *a,**k:[],connection_factory=lambda *a:Connection())
    assert len(calls)==3


def test_import_deadline_never_opens_connection():
    def unexpected(*args,**kwargs):raise AssertionError('No network after deadline')
    with pytest.raises(transport.SourceError):transport.get_page({'idioma':'gl','limite':100,'paxina':0},time.monotonic()-1,resolver=unexpected,connection_factory=unexpected)
