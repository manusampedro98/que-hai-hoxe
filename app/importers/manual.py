import json
from pathlib import Path
from pydantic import ValidationError
from app.schemas.event import Candidate

MAX_FILE=10*1024*1024


def validate_candidates(rows):
    if not isinstance(rows,list) or len(rows)>10000:raise ValueError('Máximo 10000 eventos por lote')
    valid=[]
    rejected=[]
    for index,row in enumerate(rows):
        try:
            valid.append(Candidate.model_validate(row))
        except ValidationError as exc:
            # Never log raw input: may contain malicious text or private content.
            rejected.append({'index':index,'errors':[{'field':'.'.join(map(str,e['loc'])),'reason':e['type']} for e in exc.errors()]})
    return valid,rejected


def read_manual(path: Path):
    with path.open('rb') as file:
        content=file.read(MAX_FILE+1)
    if len(content)>MAX_FILE:raise ValueError('JSON mayor de 10 MiB')
    def unique_keys(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Claves JSON duplicadas')
            result[key]=value
        return result
    payload=json.loads(content.decode('utf-8-sig'),object_pairs_hook=unique_keys,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Número JSON no finito')))
    if not isinstance(payload,dict) or type(payload.get('schema_version')) is not int or payload['schema_version']!=1 or set(payload)!={'schema_version','events'}:
        raise ValueError('Se requieren schema_version: 1 y events')
    return validate_candidates(payload['events'])
