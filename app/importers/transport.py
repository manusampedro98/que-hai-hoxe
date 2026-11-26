"""HTTPS cerrado a Axenda. DNS validado y fijado a la conexión TLS real."""
import http.client
import ipaddress
import json
import queue
import socket
import ssl
import threading
import time
from urllib.parse import urlencode

HOST='www.cultura.gal'
PATH='/v1/axenda/eventos'
SPACES_PATH='/v1/axenda/espazos'
MAX_RESPONSE=5*1024*1024


class SourceError(RuntimeError):
    pass


def resolve_public(host,timeout=5):
    result=queue.Queue(maxsize=1)
    def resolve():
        try:result.put(socket.getaddrinfo(host,443,type=socket.SOCK_STREAM))
        except Exception:result.put(None)
    threading.Thread(target=resolve,daemon=True).start()
    try:addresses=result.get(timeout=timeout)
    except queue.Empty:raise SourceError('DNS timeout') from None
    if not addresses:raise SourceError('DNS failed')
    checked=[]
    for family,kind,proto,canonical,sockaddr in addresses:
        address=ipaddress.ip_address(sockaddr[0])
        if not address.is_global or address.is_multicast or address.is_reserved or address.is_unspecified or getattr(address,'ipv4_mapped',None) is not None:
            raise SourceError('Non-public DNS answer')
        if family not in (socket.AF_INET,socket.AF_INET6):raise SourceError('Address family')
        checked.append((family,sockaddr))
    return checked


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,addresses,timeout):
        super().__init__(HOST,443,timeout=timeout,context=ssl.create_default_context())
        self.addresses=addresses

    def connect(self):
        # No second DNS lookup. SNI and certificate verification remain HOST.
        family,sockaddr=self.addresses[0]
        raw=socket.socket(family,socket.SOCK_STREAM)
        try:
            raw.settimeout(self.timeout)
            raw.connect(sockaddr)
            self.sock=self._context.wrap_socket(raw,server_hostname=HOST)
        except BaseException:
            raw.close()
            raise


def read_limited(response,deadline,sock=None):
    if response.getheader('Content-Encoding','identity')!='identity':raise SourceError('Unexpected encoding')
    length=response.getheader('Content-Length')
    if length and (not length.isdigit() or int(length)>MAX_RESPONSE):raise SourceError('Response too large')
    chunks=[]
    count=0
    while True:
        if time.monotonic()>deadline:raise SourceError('Import deadline')
        if sock:sock.settimeout(min(15,max(.01,deadline-time.monotonic())))
        part=response.read1(min(65536,MAX_RESPONSE+1-count))
        if not part:break
        chunks.append(part)
        count+=len(part)
        if count>MAX_RESPONSE:raise SourceError('Response too large')
    try:return json.loads(b''.join(chunks))
    except (ValueError,UnicodeError):raise SourceError('Invalid JSON') from None


def get_page(params,deadline,*,resolver=resolve_public,connection_factory=PinnedHTTPS):
    if set(params)-{'idioma','limite','paxina','inicio','fin','campos'}:raise SourceError('Unapproved parameters')
    if params.get('idioma')!='gl' or type(params.get('limite')) is not int or not 1<=params['limite']<=500 or type(params.get('paxina')) is not int or not 0<=params['paxina']<200:
        raise SourceError('Invalid page parameters')
    return _get_json(PATH,params,deadline,resolver,connection_factory)


def get_spaces(deadline, *, resolver=resolve_public, connection_factory=PinnedHTTPS):
    return _get_json(SPACES_PATH,{'idioma':'gl'},deadline,resolver,connection_factory)


def _get_json(path,params,deadline,resolver,connection_factory):
    for attempt in range(3):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise SourceError('Import deadline')
        addresses=resolver(HOST,timeout=min(5,remaining))
        conn=connection_factory(addresses,min(5,remaining))
        try:
            conn.request('GET',path+'?'+urlencode(params),headers={'Host':HOST,'Accept':'application/json','Accept-Encoding':'identity','User-Agent':'QueHaiHoxe/0.1'})
            if conn.sock:conn.sock.settimeout(min(15,max(.01,deadline-time.monotonic())))
            response=conn.getresponse()
            if response.status in (401,403):raise SourceError('Access denied; no retry')
            if response.status in (429,500,502,503,504):
                retry=response.getheader('Retry-After','1')
                # Long or HTTP-date quotas are not retried automatically.
                if attempt==2 or not retry.isdigit() or int(retry)>30:raise SourceError('Quota or service unavailable')
                wait=max(1,int(retry))
                if time.monotonic()+wait>=deadline:raise SourceError('Import deadline')
                time.sleep(wait)
                continue
            if response.status!=200:raise SourceError('Unexpected HTTP status; redirects forbidden')
            if response.getheader('Content-Type','').split(';')[0].strip().lower()!='application/json':raise SourceError('Unexpected media type')
            return read_limited(response,deadline,conn.sock)
        except (OSError,http.client.HTTPException) as exc:
            if attempt==2:raise SourceError('Network failure') from None
            if time.monotonic()+1>=deadline:raise SourceError('Import deadline') from None
            time.sleep(1)
        finally:conn.close()
    raise SourceError('Retries exhausted')
