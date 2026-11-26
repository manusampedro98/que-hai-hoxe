import copy
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.config import Settings
from app.main import create_app
from app.db.models import ImportRun,EventSource
from app.db.repository import read_catalogue,engine_for
from app.importers.pipeline import import_candidates
from app.importers.manual import read_manual
from app.importers.axenda import fetch_axenda,map_event,local_instant
from app.importers.transport import SourceError
from app.schemas.event import Candidate


def test_idempotence_provenance_and_no_deletion(database,candidate):
    a=import_candidates(database,[candidate],[],'manual')
    events,last=read_catalogue(database)
    first=events[0]['id']
    b=import_candidates(database,[candidate],[],'manual')
    assert a['new']==1 and b['new']==b['updated']==0 and b['unchanged']==1
    assert read_catalogue(database)[0][0]['id']==first
    import_candidates(database,[],[],'manual')
    assert read_catalogue(database)[0][0]['status']=='unknown'
    engine=engine_for(database)
    with Session(engine) as session:
        source=session.scalar(select(EventSource))
        assert source.external_id=='test-1' and source.provenance['source']['name']=='Persona de pruebas'
    engine.dispose()


def test_dry_run_has_no_persistent_changes(database,candidate):
    inventory={p.name:p.read_bytes() for p in database.parent.iterdir()}
    summary=import_candidates(database,[candidate],[],'manual',dry_run=True)
    assert summary['new']==1
    assert {p.name:p.read_bytes() for p in database.parent.iterdir()}==inventory


def test_update_cancel_postpone_and_original_date(database,candidate):
    import_candidates(database,[candidate],[],'manual')
    first=read_catalogue(database)[0][0]['id']
    row=candidate.model_dump(mode='json')
    row.update(status='cancelled',tickets_url='https://www.cultura.gal/entradas')
    cancelled=Candidate.model_validate(row)
    assert import_candidates(database,[cancelled],[],'manual')['updated']==1
    client=TestClient(create_app(Settings(db_path=database)),base_url='http://localhost')
    detail=client.get('/events/'+first).text
    assert 'Cancelado' in detail and 'Ver entradas' not in detail
    row['status']='postponed'
    import_candidates(database,[Candidate.model_validate(row)],[],'manual')
    detail=client.get('/events/'+first).text
    assert 'Nueva fecha pendiente' in detail and 'Ver entradas' not in detail
    row['date']['start_date']='2026-11-02'
    import_candidates(database,[Candidate.model_validate(row)],[],'manual')
    result=read_catalogue(database)[0][0]
    assert result['id']==first and result['original_start_date']=='2026-10-28'
    assert 'Nueva fecha confirmada' in client.get('/events/'+first).text


def test_rollback_preserves_last_success(database,candidate):
    import_candidates(database,[candidate],[],'manual')
    before=read_catalogue(database)
    def crash(session):raise RuntimeError('synthetic write failure')
    changed=candidate.model_copy(update={'title':'Cambio que no se debe publicar'})
    with pytest.raises(RuntimeError):import_candidates(database,[changed],[],'manual',before_commit=crash)
    assert read_catalogue(database)==before
    engine=engine_for(database)
    with Session(engine) as session:assert session.scalars(select(ImportRun.status).order_by(ImportRun.id)).all()==['success','failed']
    engine.dispose()


def test_distinct_sessions_languages_and_manual_namespace(database,candidate):
    a=candidate.model_dump(mode='json')
    b=copy.deepcopy(a);b['occurrence_key']='evening'
    c=copy.deepcopy(a);c['external_id']='different-day';c['date']['start_date']='2026-10-29'
    d=copy.deepcopy(a);d['external_id']='unproven-translation';d['title']='Muestra sintética'
    import_candidates(database,[Candidate.model_validate(r) for r in [a,b,c,d]],[],'manual')
    import_candidates(database,[candidate],[],'axenda')
    assert len(read_catalogue(database)[0])==5


@pytest.mark.parametrize('change',[
    {'title':''}, {'date':{'start_date':'2026-02-30'}},
    {'price':{'type':'exact','amount_minor':-100,'currency':'EUR','evidence':'test'}},
    {'price':{'type':'free','amount_minor':0}},
    {'date':{'start_date':'2026-10-28','precision':'date','starts_at':'2026-10-28T00:00:00Z'}}
])
def test_invalid_records_are_explained(tmp_path,candidate,change):
    row=candidate.model_dump(mode='json');row.update(change)
    file=tmp_path/'manual.json';file.write_text(json.dumps({'schema_version':1,'events':[row]}),encoding='utf8')
    valid,rejected=read_manual(file)
    assert not valid and rejected[0]['errors']


def test_file_limit_and_duplicate_json_keys(tmp_path):
    path=tmp_path/'big.json';path.write_bytes(b' '*(10*1024*1024+1))
    with pytest.raises(ValueError):read_manual(path)
    path.write_text('{"schema_version":1,"schema_version":1,"events":[]}',encoding='utf8')
    with pytest.raises(ValueError):read_manual(path)


def raw_event(eid):
    # Handcrafted contract fixture, not an external full-content payload.
    return dict(id=eid,titulo='Evento sintético',data={'dataInicio':'2026-10-28 18:00:00','dataFin':'2026-10-28 18:00:00'},estado=None,tipoEvento={'tid':7},tipoEntrada=[{'tid':71,'nome':'Entrada de balde'}],lugarCelebracion={'nome':'Recinto sintético','espazoId':'123','concello':{'nome':'A Coruña'},'localizacion':{'latitude':43.36,'lonxitude':-8.41}},corpo='<p>Texto <strong>legible</strong></p><script>hostile()</script>',url='https://www.cultura.gal/gl/evento/123')


def test_source_mapping_and_coarse_coordinates():
    row=raw_event(1)
    result=Candidate.model_validate(map_event(row))
    assert result.category=='music' and result.price.type=='free'
    assert result.venue.coordinates_verified and result.date.ends_at is None
    assert 'hostile' not in result.description and '<p>' not in result.description
    row['tipoEntrada']=[];row['lugarCelebracion']['espazoId']=None
    result=Candidate.model_validate(map_event(row))
    assert result.price.type=='unknown' and not result.venue.coordinates_verified
    with pytest.raises(ValueError):local_instant('2026-10-25 02:30:00')
    with pytest.raises(ValueError):local_instant('2026-03-29 02:30:00')


def test_source_date_only_and_postponed_without_new_date():
    row=raw_event(1)
    row['data']={'dataInicio':'2026-10-28','dataFin':'2026-10-30'}
    result=Candidate.model_validate(map_event(row))
    assert result.date.precision=='date' and result.date.starts_at is None and result.date.ends_at is None
    row.update(estado={'chave':'postponed'},dataOrixinal={'dataInicio':'2026-10-28 18:00:00'},data={'dataInicio':None,'dataFin':None})
    result=Candidate.model_validate(map_event(row))
    assert result.status=='postponed' and result.original_start_date==result.date.start_date


def test_pagination_and_failure_do_not_write(database,candidate):
    import_candidates(database,[candidate],[],'manual');before=read_catalogue(database)
    pages=[]
    def fetch(params,deadline):
        pages.append(params['paxina'])
        return {'totalResultados':3,'elementosPorPaxina':2,'listaAxenda':[raw_event(1),raw_event(2)] if params['paxina']==0 else [raw_event(3)]}
    valid,rejected=fetch_axenda(fetch_page=fetch,page_size=2)
    assert len(valid)==3 and not rejected and pages==[0,1]
    def broken(params,deadline):
        if params['paxina']==1:raise SourceError('synthetic timeout')
        return fetch(params,deadline)
    with pytest.raises(SourceError):fetch_axenda(fetch_page=broken,page_size=2)
    assert read_catalogue(database)==before
    def repeat(params,deadline):return {'totalResultados':4,'elementosPorPaxina':2,'listaAxenda':[raw_event(1),raw_event(2)]}
    with pytest.raises(SourceError):fetch_axenda(fetch_page=repeat,page_size=2)


def test_conflicting_identity_rolls_back(database,candidate):
    conflict=candidate.model_copy(update={'title':'Otro contenido'})
    with pytest.raises(ValueError):import_candidates(database,[candidate,conflict],[],'manual')
    assert read_catalogue(database)[0]==[]
