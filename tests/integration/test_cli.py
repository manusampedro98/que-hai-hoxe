import json
from app.cli import main
from app.db.repository import read_catalogue


def test_real_cli_manual_dry_run_apply(database,candidate,tmp_path,capsys):
    file=tmp_path/'input.json'
    file.write_text(json.dumps({'schema_version':1,'events':[candidate.model_dump(mode='json')]}),encoding='utf8')
    before=database.read_bytes()
    assert main(['--db',str(database),'import-json','--file',str(file),'--dry-run'])==0
    assert database.read_bytes()==before
    assert main(['--db',str(database),'import-json','--file',str(file)])==0
    assert len(read_catalogue(database)[0])==1
    assert main(['--db',str(database),'import-json','--file',str(file)])==0
    assert len(read_catalogue(database)[0])==1


def test_cli_failed_input_keeps_catalogue(database,candidate,tmp_path,capsys):
    file=tmp_path/'bad.json';file.write_text('{not json',encoding='utf8')
    before=read_catalogue(database)
    assert main(['--db',str(database),'import-json','--file',str(file)])==1
    assert read_catalogue(database)==before
    output=capsys.readouterr().out
    assert str(tmp_path) not in output
