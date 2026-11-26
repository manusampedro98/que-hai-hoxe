from datetime import datetime, timezone

import pytest

from app import pages
from app.importers.axenda import map_event
from app.schemas.event import Candidate
from scripts.audit_publication import audit_site


CHECKED = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)
BASE = "/que-hai-hoxe/"
SPACE = {"tid": 123, "nome": "Teatro de proba", "localizacion": {"latitude": 43.36, "lonxitude": -8.41}}


def official_event(**updates):
    row = {
        "id": 12,
        "titulo": "Música & cultura",
        "data": {"dataInicio": "2026-10-28 18:00:00"},
        "dataActualizacion": "2026-10-27 14:00:00",
        "corpo": "Texto editorial da fonte",
        "url": "https://www.cultura.gal/gl/evento/12/8/20",
        "lugarCelebracion": {"nome": SPACE["nome"], "espazoId": "123", "concello": {"nome": "A Coruña"},
                            "localizacion": SPACE["localizacion"]},
    }
    return Candidate.model_validate(map_event(dict(row, **updates)))


def test_public_pages_reuse_templates_and_minimise_data(tmp_path):
    candidate = official_event()
    venues = pages.venue_directory({"listaTermos": [SPACE], "totalResultados": 1})
    catalogue = pages.public_catalogue([candidate], venues, CHECKED)
    event = catalogue["events"][0]
    assert event["venue"]["coordinates_verified"]
    assert event["source_updated_at"] == "2026-10-27 14:00:00"
    assert {"description", "tickets_url", "provenance", "external_id"}.isdisjoint(event)
    assert pages.public_catalogue([candidate], venues, CHECKED)["events"][0]["id"] == event["id"]
    pages.write_site(tmp_path, BASE, catalogue)
    assert audit_site(tmp_path, BASE) == 20
    detail = (tmp_path / "events" / event["id"] / "index.html").read_text(encoding="utf-8")
    assert "Música &amp; cultura" in detail and "Texto editorial da fonte" not in detail
    assert f'href="{BASE}"' in detail
    (tmp_path / "internal.txt").write_text("Solo de uso local", encoding="utf-8")
    with pytest.raises(ValueError, match="lista"):
        audit_site(tmp_path, BASE)


def test_public_source_rejects_contact_and_limits_position():
    candidate = official_event()
    alternate = official_event(id=13, titulo="Contacto: proba@example.org")
    invalid_link = official_event(id=14, url="https://example.org/gl/evento/14")
    changed_venue = dict(SPACE, localizacion={"latitude": 43.2, "lonxitude": -8.41})
    catalogue = pages.public_catalogue([candidate, alternate, invalid_link], {123: changed_venue}, CHECKED)
    assert len(catalogue["events"]) == 1
    venue = catalogue["events"][0]["venue"]
    assert venue == {"municipality": "A Coruña", "name": None, "latitude": None, "longitude": None, "coordinates_verified": False}


def test_public_venues_with_address_as_name_are_kept_in_list_only():
    address = "Rúa das Probas, 1"
    location = {"nome": address, "espazoId": "123", "concello": {"nome": "A Coruña"},
                "localizacion": SPACE["localizacion"]}
    candidate = official_event(lugarCelebracion=location)
    catalogue = pages.public_catalogue([candidate], {123: dict(SPACE, nome=address)}, CHECKED)
    venue = catalogue["events"][0]["venue"]
    assert venue["municipality"] == "A Coruña"
    assert venue["name"] is None and venue["latitude"] is None


def test_failed_refresh_writes_nothing_and_keeps_previous_files(tmp_path, monkeypatch):
    def unavailable(**options):
        raise pages.SourceError("Fuente no disponible")

    monkeypatch.setattr(pages, "fetch_axenda", unavailable)
    previous = tmp_path / "published.html"
    previous.write_bytes(b"last build")
    output = tmp_path / "next"
    with pytest.raises(SystemExit) as error:
        pages.main(["--output", str(output)])
    assert error.value.code == 1
    assert not output.exists()
    assert previous.read_bytes() == b"last build"
