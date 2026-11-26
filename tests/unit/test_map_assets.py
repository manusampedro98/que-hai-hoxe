import hashlib,json
from app.config import ROOT
from app.main import CSP


def test_leaflet_integrity_local_dependencies_and_csp():
    manifest=json.loads((ROOT/'docs/LEAFLET_MANIFEST.json').read_text())
    assert manifest['version']=='1.9.4'
    root=ROOT/'app/static/vendor/leaflet'
    for name,digest in manifest['files'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest
    assert 'https://www.ign.es/wmts/ign-base' in CSP
    assert 'unsafe-inline' not in CSP and 'https://unpkg.com' not in CSP
    assert "connect-src 'self'" in CSP
