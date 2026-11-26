import hashlib
import json
import re
import time
from datetime import datetime,timedelta,timezone
from html.parser import HTMLParser
from app.importers.transport import get_page,SourceError
from app.importers.manual import validate_candidates
from app.services import now,TZ

# IDs confirmed against the live official taxonomies on 2026-10-28.
MUSIC={7,8,9,10,11,12,74,75,76,77}
FESTIVAL={26,549,551,2162}
FIELDS='id,nid,traducionId,idioma,data,dataOrixinal,estado,lugarCelebracion,titulo,entrada,corpo,tipoEvento,tipoEntrada,url,dataActualizacion'


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]
        self.ignored=0

    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.ignored+=1
        if tag in ('p','br','div','li'):self.parts.append('\n')

    def handle_endtag(self,tag):
        if tag in ('script','style') and self.ignored:self.ignored-=1
        if tag in ('p','div','li'):self.parts.append('\n')

    def handle_data(self,data):
        if not self.ignored:self.parts.append(data)


def plain(value):
    if value is None:return None
    if not isinstance(value,str) or len(value)>100000:raise ValueError('Text field invalid')
    parser=PlainText();parser.feed(value)
    return '\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip()) or None


def local_instant(value):
    if not isinstance(value,str):raise ValueError('Date missing')
    parsed=datetime.fromisoformat(value)
    if parsed.tzinfo:return parsed.astimezone(TZ)
    # Reject ambiguous/nonexistent local times instead of choosing a DST fold.
    a=parsed.replace(tzinfo=TZ,fold=0)
    b=parsed.replace(tzinfo=TZ,fold=1)
    if a.utcoffset()!=b.utcoffset() or a.astimezone(timezone.utc).astimezone(TZ).replace(tzinfo=None)!=parsed:
        raise ValueError('Ambiguous local date')
    return a


def map_event(raw):
    if not isinstance(raw,dict) or type(raw.get('id')) is not int:raise ValueError('Schema id')
    data=raw['data']
    state=raw.get('estado')
    status='scheduled' if state is None else state.get('chave','unknown') if isinstance(state,dict) else 'unknown'
    if status not in ('scheduled','cancelled','postponed'):status='unknown'
    old=raw.get('dataOrixinal') or {}
    original=local_instant(old['dataInicio']).date().isoformat() if old.get('dataInicio') else None
    start_value=data.get('dataInicio')
    if not start_value and status=='postponed' and old.get('dataInicio'):
        start_value=old['dataInicio']
    first=local_instant(start_value)
    date_only=bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}',start_value))
    finish_value=data.get('dataFin')
    if date_only and finish_value and not re.fullmatch(r'\d{4}-\d{2}-\d{2}',finish_value):raise ValueError('Mixed precision')
    finish=local_instant(finish_value) if finish_value else None
    if finish and finish<first:raise ValueError('Date range invalid')
    # The API represents source dates in MySQL format, including midnight.
    # Preserve literal midnight; it is never silently converted into "unknown".
    location=raw.get('lugarCelebracion') or {}
    town=location.get('concello') or {}
    coordinates=location.get('localizacion') or {}
    lat,lon=coordinates.get('latitude'),coordinates.get('lonxitude')
    valid_coord=isinstance(lat,(int,float)) and isinstance(lon,(int,float)) and 41.7<=lat<=43.9 and -9.6<=lon<=-6.7
    # Many source points are municipality fallbacks. Require an explicit space ID and name.
    verified=bool(valid_coord and location.get('espazoId') and location.get('nome'))
    category=raw.get('tipoEvento') or {}
    tid=category.get('tid')
    free=any(isinstance(p,dict) and p.get('tid')==71 and p.get('nome')=='Entrada de balde' for p in (raw.get('tipoEntrada') or []))
    source_url=raw.get('url')
    description='\n\n'.join(filter(None,[plain(raw.get('entrada')),plain(raw.get('corpo'))])) or None
    return dict(external_id=str(raw['id']),title=plain(raw.get('titulo')) or '',description=description,
        category='music' if tid in MUSIC else 'festival' if tid in FESTIVAL else 'culture',
        date=dict(start_date=first.date().isoformat(),end_date=finish.date().isoformat() if finish and finish>first else None,
            starts_at=None if date_only else first.isoformat(),ends_at=finish.isoformat() if finish and finish>first and not date_only else None,precision='date' if date_only else 'datetime'),
        venue=dict(name=location.get('nome') or None,municipality=town.get('nome') or None,municipality_code=str(town['cod_ine']) if town.get('cod_ine') else None,
            latitude=lat if valid_coord else None,longitude=lon if valid_coord else None,coordinates_verified=verified),
        price=dict(type='free',amount_minor=0,currency=None,evidence='Axenda: tipoEntrada tid=71, Entrada de balde') if free else dict(type='unknown'),
        source=dict(name='Fonte dos datos: Xunta de Galicia · Axenda Cultura Galicia',url=source_url),
        status=status,original_start_date=original,
        provenance=dict(language=raw.get('idioma'),node_id=raw.get('nid'),translation_id=raw.get('traducionId'),source_updated_at=raw.get('dataActualizacion'),external_category=category,original_dates=data,original_status=state,coordinate_space_id=location.get('espazoId'),coordinate_check='Source space ID + named venue + Galicia bounds; municipal fallback excluded',license='CC BY-SA 4.0',mapping_version=1))


def fetch_axenda(*,fetch_page=get_page,clock=now,page_size=100,fields=FIELDS):
    start=clock().astimezone(TZ).date()
    end=start+timedelta(days=89)
    deadline=time.monotonic()+300
    rows=[];seen=set();fingerprints=set();total=None
    for page in range(200):
        if time.monotonic()>deadline:raise SourceError('Import deadline')
        payload=fetch_page(dict(idioma='gl',limite=page_size,paxina=page,inicio=start.isoformat(),fin=end.isoformat(),campos=fields),deadline)
        if not isinstance(payload,dict) or type(payload.get('totalResultados')) is not int or not isinstance(payload.get('listaAxenda'),list) or payload.get('elementosPorPaxina')!=page_size:
            raise SourceError('Schema changed')
        count=payload['totalResultados']
        if count<0 or count>10000 or (total is not None and count!=total):raise SourceError('Unstable or excessive total')
        total=count
        chunk=payload['listaAxenda']
        if len(chunk)>page_size:raise SourceError('Oversized page')
        fingerprint=hashlib.sha256(json.dumps(chunk,sort_keys=True).encode()).hexdigest()
        if chunk and fingerprint in fingerprints:raise SourceError('Repeated page')
        fingerprints.add(fingerprint)
        for row in chunk:
            if not isinstance(row,dict) or type(row.get('id')) is not int or row['id'] in seen:raise SourceError('Duplicate or invalid source identity')
            seen.add(row['id']);rows.append(row)
        if len(rows)>total:raise SourceError('Inconsistent total')
        if len(rows)==total:break
        if len(chunk)<page_size:raise SourceError('Incomplete page')
        time.sleep(.15)
    else:raise SourceError('Page limit')
    mapped=[];rejected=[]
    for index,row in enumerate(rows):
        try:mapped.append(map_event(row))
        except (ValueError,KeyError,TypeError):rejected.append({'index':index,'external_id':str(row['id']),'reason':'invalid_source_record'})
    valid,invalid=validate_candidates(mapped)
    return valid,rejected+invalid
