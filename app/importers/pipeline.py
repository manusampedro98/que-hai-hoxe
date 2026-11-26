import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from app.db.models import Event, EventSource, ImportRun
from app.db.repository import engine_for


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def record_failure(path,source,reason):
    engine=engine_for(path,readonly=False)
    try:
        with Session(engine) as session,session.begin():
            stamp=timestamp()
            session.add(ImportRun(source=source,started_at=stamp,finished_at=stamp,status='failed',summary={'reason':reason}))
    finally:engine.dispose()


def import_candidates(path,candidates,rejected,source,*,dry_run=False,before_commit=None):
    started=timestamp()
    engine=engine_for(path,readonly=dry_run)
    try:
        for attempt in range(3):
            try:
                with Session(engine) as session, session.begin():
                    summary=dict(new=0,updated=0,unchanged=0,rejected=len(rejected),possible_duplicates=0,issues=rejected[:100],dry_run=dry_run)
                    identities={}
                    seen=set()
                    # Full validation/preparation happens before opening this brief transaction.
                    for candidate in candidates:
                        identity=(source,candidate.external_id,candidate.occurrence_key)
                        encoded=json.dumps(candidate.model_dump(mode='json'),ensure_ascii=False,sort_keys=True,separators=(',',':'))
                        digest=hashlib.sha256(encoded.encode()).hexdigest()
                        if identity in identities:
                            if identities[identity]!=digest:raise ValueError('Identidad repetida con contenido contradictorio')
                            summary['possible_duplicates']+=1
                            continue
                        identities[identity]=digest
                        existing=session.scalar(select(EventSource).where(EventSource.source_key==source,EventSource.external_id==candidate.external_id,EventSource.occurrence_key==candidate.occurrence_key))
                        summary['unchanged' if existing and existing.content_hash==digest else 'updated' if existing else 'new']+=1
                        # Similar titles with different identities are reviewed, never destructively merged.
                        similarity=(candidate.title.casefold(),candidate.date.model_dump_json(),candidate.venue.municipality,candidate.venue.name)
                        if similarity in seen:summary['possible_duplicates']+=1
                        seen.add(similarity)
                        if dry_run:continue
                        stamp=timestamp()
                        if existing:
                            event=session.get(Event,existing.event_id)
                            data=candidate.dto(event.id,stamp)
                            old=event.payload
                            if not data['original_start_date']:
                                data['original_start_date']=old.get('original_start_date') or (old['date']['start_date'] if old['date']['start_date']!=data['date']['start_date'] or data['status']=='postponed' else None)
                            event.title=candidate.title
                            event.payload=data
                            existing.content_hash=digest
                            existing.last_seen_at=stamp
                            existing.provenance=candidate.model_dump(mode='json')
                        else:
                            eid='evt-'+uuid.uuid4().hex
                            session.add(Event(id=eid,title=candidate.title,payload=candidate.dto(eid,stamp)))
                            session.flush()
                            session.add(EventSource(source_key=source,external_id=candidate.external_id,occurrence_key=candidate.occurrence_key,event_id=eid,content_hash=digest,provenance=candidate.model_dump(mode='json'),last_seen_at=stamp))
                    if not dry_run:
                        if before_commit:before_commit(session)
                        session.add(ImportRun(source=source,started_at=started,finished_at=timestamp(),status='success',summary=summary))
                    return summary
            except OperationalError as exc:
                if 'locked' not in str(exc).lower() or attempt==2:raise
                time.sleep(.2*(attempt+1))
    except Exception as exc:
        if not dry_run:
            record_failure(path,source,'transaction_failed')
            exc.failure_recorded=True
        raise
    finally:engine.dispose()
