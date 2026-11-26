"""Build the public edition from the official source into a new static directory."""

import argparse
import hashlib
import json
import re
import shutil
import tempfile
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import unquote, urlsplit

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.importers.axenda import FIELDS, fetch_axenda
from app.importers.transport import HOST, SourceError, get_spaces
from app.services import CATEGORIES, STATUSES, TZ, date_label, now, overlaps, price_label, sort_key

PACKAGE = Path(__file__).resolve().parent
DATASET = "https://abertos.xunta.gal/catalogo/cultura-ocio-deporte/-/dataset/0045/axenda-cultura-galicia"
LICENSE = "https://creativecommons.org/licenses/by-sa/4.0/"
SOURCE_NAME = "Fonte dos datos: Xunta de Galicia · Axenda Cultura Galicia"
PUBLIC_FIELDS = ",".join(field for field in FIELDS.split(",") if field not in {"entrada", "corpo"})
PUBLIC_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' "
    "https://www.ign.es/wmts/ign-base; connect-src 'self'; base-uri 'none'; form-action 'none'"
)
ASSETS = (
    "css/app.css",
    "icons/radar.svg",
    "js/app.js",
    "js/map.js",
    "js/rules.mjs",
    "vendor/leaflet/LICENSE",
    "vendor/leaflet/leaflet.css",
    "vendor/leaflet/leaflet.js",
    "vendor/leaflet/images/empty.gif",
    "vendor/leaflet/images/layers-2x.png",
    "vendor/leaflet/images/layers.png",
    "vendor/leaflet/images/marker-icon-2x.png",
    "vendor/leaflet/images/marker-icon.png",
    "vendor/leaflet/images/marker-shadow.png",
)
CONTACT = re.compile(
    r"@|(?:https?://|www\.)|\b(?:\d[ .-]?){8,}\d\b|"
    r"\b(?:[XYZ][ .-]?\d{7}|\d{8})[ .-]?[A-Z]\b|"
    r"\b(?:[a-z]:[\\/]|(?:10|127|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d+\.)",
    re.IGNORECASE,
)
ADDRESS = re.compile(
    r"(?:^|[,;·(])\s*(?:r[úu]a|calle|avenida|avda|praza|plaza|paseo|estrada|"
    r"carretera|traves[ií]a|cami[ñn]o|camino|lugar|parroquia|ronda|urbanizaci[oó]n)\b"
    r"|^(?:r|c|av|pz)\s*[./]|\bs\s*/\s*n\b|,\s*(?:n[.º°]?\s*)?\d+\s*[a-z]?\s*$",
    re.IGNORECASE,
)


def site_root(value):
    path = value.strip("/")
    if path and not re.fullmatch(r"[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)*", path):
        raise argparse.ArgumentTypeError("Ruta de Pages inválida")
    return f"/{path}/" if path else "/"


def public_text(value):
    if not value:
        return None
    text = unicodedata.normalize("NFC", " ".join(value.split()))
    if CONTACT.search(unicodedata.normalize("NFKC", text)):
        return None
    if any(unicodedata.category(character).startswith("C") for character in text):
        return None
    return text


def event_url(value):
    if not value:
        return None
    url = urlsplit(value)
    if url.scheme != "https" or url.netloc != HOST or url.query or url.fragment:
        return None
    slug = unquote(url.path)
    return value if re.fullmatch(r"/(?:gl|es)/evento/[\w-]+(?:/\d+){0,2}/?", slug) else None


def source_timestamp(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2})?", value):
        return None
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return None
    return value


def venue_directory(payload):
    rows = payload.get("listaTermos") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows or len(rows) != payload.get("totalResultados"):
        raise SourceError("Directorio de recintos incompleto")
    venues = {}
    for row in rows:
        if not isinstance(row, dict) or type(row.get("tid")) is not int or row["tid"] in venues:
            raise SourceError("Identificador de recinto inválido")
        venues[row["tid"]] = row
    return venues


def public_venue(candidate, venues):
    original = candidate.venue
    result = {"municipality": public_text(original.municipality), "name": None,
              "latitude": None, "longitude": None, "coordinates_verified": False}
    space_id = str(candidate.provenance.get("coordinate_space_id"))
    space = venues.get(int(space_id)) if re.fullmatch(r"[0-9]{1,12}", space_id) else None
    if not space or not result["municipality"] or not original.coordinates_verified:
        return result
    name = public_text(space["nome"]) if isinstance(space.get("nome"), str) else None
    coords = space.get("localizacion")
    if not name or ADDRESS.search(name) or name != public_text(original.name) or not isinstance(coords, dict):
        return result
    if (coords.get("latitude"), coords.get("lonxitude")) != (original.latitude, original.longitude):
        return result
    return dict(result, name=name, latitude=original.latitude, longitude=original.longitude, coordinates_verified=True)


def public_catalogue(candidates, venues, checked):
    day = checked.astimezone(TZ).date()
    end = day + timedelta(days=90)
    events = []
    ids = set()
    for candidate in candidates:
        title, url = public_text(candidate.title), event_url(candidate.source.url)
        if not title or not url:
            continue
        identity = json.dumps(["axenda", candidate.external_id, candidate.occurrence_key]).encode()
        event_id = "ax-" + hashlib.sha256(identity).hexdigest()[:32]
        if event_id in ids:
            raise SourceError("Identidad repetida en el catálogo público")
        ids.add(event_id)
        stamp = candidate.provenance.get("source_updated_at")
        updated = source_timestamp(stamp)
        if stamp and not updated:
            raise SourceError("Cambió el formato de fecha de actualización de la fuente")
        event = {
            "id": event_id, "title": title, "category": candidate.category, "status": candidate.status,
            "date": candidate.date.model_dump(mode="json"),
            "original_start_date": candidate.original_start_date.isoformat() if candidate.original_start_date else None,
            "venue": public_venue(candidate, venues),
            "price": candidate.price.model_dump(mode="json", exclude={"evidence"}),
            "source": {"name": SOURCE_NAME, "url": url}, "source_updated_at": updated,
            "last_verified_at": checked.isoformat(),
        }
        if overlaps(event, day, end):
            events.append(event)
    if not events:
        raise SourceError("Catálogo público vacío; se conserva la última edición válida")
    return {
        "events": sorted(events, key=sort_key), "timezone": "Europe/Madrid",
        "coverage_start": day.isoformat(), "coverage_end": end.isoformat(),
        "last_successful_import_at": checked.isoformat(),
        "attribution": {"source": "Xunta de Galicia · Axenda de Cultura de Galicia", "url": DATASET,
                        "license": "CC BY-SA 4.0", "license_url": LICENSE,
                        "changes": "Selección de campos, categorías y fechas normalizadas; verificación de recintos."},
    }


def write_site(root, base, catalogue):
    templates = Environment(loader=FileSystemLoader(PACKAGE / "templates"), autoescape=select_autoescape())
    templates.globals.update(price_label=price_label, date_label=date_label, categories=CATEGORIES, statuses=STATUSES)
    imported_at = catalogue["last_successful_import_at"]
    imported_label = datetime.fromisoformat(imported_at).astimezone(TZ).strftime("%d/%m/%Y, %H:%M")
    context = dict(static_site=True, site_root=base, static_csp=PUBLIC_CSP, demo=False,
                   dataset_url=DATASET, license_url=LICENSE, imported_at=imported_at, imported_label=imported_label)

    def render(name, destination, **data):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(templates.get_template(name).render(**context, **data), encoding="utf-8")

    render("index.html", root / "index.html")
    render("detail.html", root / "404.html", event=None)
    render("credits.html", root / "creditos" / "index.html")
    for event in catalogue["events"]:
        render("detail.html", root / "events" / event["id"] / "index.html", event=event)
    (root / "eventos.json").write_text(json.dumps(catalogue, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    (root / ".nojekyll").touch()
    for asset in ASSETS:
        dest = root / "static" / asset
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PACKAGE / "static" / asset, dest)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-path", type=site_root, default="/")
    parser.add_argument("--output", type=Path, required=True, help="Directorio nuevo de salida")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output.exists():
        parser.error("La salida debe ser nueva; el catálogo anterior se conserva.")
    try:
        candidates, rejected = fetch_axenda(fields=PUBLIC_FIELDS)
        if rejected:
            raise SourceError("La fuente contiene registros incompatibles; se conserva la edición anterior")
        venues = venue_directory(get_spaces(time.monotonic() + 45))
        catalogue = public_catalogue(candidates, venues, now())
    except SourceError as error:
        parser.exit(1, f"Publicación detenida: {error}\n")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pages-", dir=output.parent) as temp:
        build = Path(temp) / "site"
        build.mkdir()
        write_site(build, args.base_path, catalogue)
        build.rename(output)
    count = len(catalogue["events"])
    print(f"{count} eventos públicos, {sum(e['venue']['coordinates_verified'] for e in catalogue['events'])} con posición verificada.")


if __name__ == "__main__":
    main()
