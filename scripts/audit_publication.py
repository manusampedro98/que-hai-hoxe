"""Verify the exact static artifact or the source tree prepared for publication."""

import argparse
import json
import re
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from app.pages import ADDRESS, ASSETS, DATASET, LICENSE, PUBLIC_CSP, event_url, public_text, site_root

PRIVATE = {
    "local profile path": re.compile(r"(?:[A-Z]:[\\/]+Users[\\/]|/home/[\w.-]+/|\\\\(?:[A-Z]:)?[\\/]Users[\\/])", re.I),
    "private key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "credential format": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|(?:AKIA|ASIA)[A-Z0-9]{16}|xox[baprs]-[\w-]{12,}|sk-(?:proj-)?[A-Za-z0-9_-]{24,})\b"),
    "URL credentials": re.compile(r"""https?://[^/\s:@'"<>]+:[^/@\s'"<>]+@"""),
    "literal secret assignment": re.compile(r"""(?im)^\s*(?:api_key|access_token|password|secret)\s*[:=]\s*['"][^'"\s]{12,}['"]"""),
}
PUBLIC_EXTERNAL = {
    DATASET, LICENSE, "https://abertos.xunta.gal", "https://abertos.xunta.gal/es/condicions-de-uso",
    "https://www.ign.es/resources/licencia/Condiciones_licenciaUso_IGN.pdf",
    "https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement",
}
BINARY = {".png", ".gif"}
ROOT_SOURCE = {
    ".gitignore", "README.md", "pyproject.toml", "requirements.lock", "requirements-dev.lock",
    "requirements-pages.lock", ".github/workflows/pages.yml", "docs/LEAFLET_MANIFEST.json",
    "scripts/audit_publication.py",
}


def allowed_source(name):
    if name in ROOT_SOURCE:
        return True
    if name.startswith("app/static/"):
        return name.removeprefix("app/static/") in ASSETS
    return bool(re.fullmatch(r"app/(?:[a-z_]+/)*[a-z_]+\.py|app/templates/[a-z_]+\.html|tests/(?:[a-z_]+/)*[a-z_]+\.(?:py|mjs)", name))


def file_map(root):
    files = {}
    for path in root.rglob("*"):
        if path.is_symlink() or path.is_junction():
            raise ValueError("El paquete contiene un enlace de sistema de archivos")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = path
    return files


def scan_text(name, text):
    for label, pattern in PRIVATE.items():
        if pattern.search(text):
            raise ValueError(f"{name}: coincidencia de {label}")


class StaticHTML(HTMLParser):
    def __init__(self, base, files, event_urls):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.files = files
        self.event_urls = event_urls
        self.csp = False
        self.referrer = False

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag in {"iframe", "object", "embed", "base", "form", "style"} or any(name.startswith("on") or name == "style" for name in fields):
            raise ValueError("Etiqueta o atributo activo inesperado")
        if tag == "script" and fields.get("src") != self.base + "static/js/app.js":
            raise ValueError("Script inesperado")
        if tag == "meta":
            policy = (fields.get("http-equiv") or "").lower()
            if policy == "content-security-policy":
                self.csp = fields.get("content") == PUBLIC_CSP
            elif policy:
                raise ValueError("Política HTTP en HTML inesperada")
            if fields.get("name") == "referrer":
                self.referrer = fields.get("content") == "no-referrer"
        for attr in ("href", "src"):
            if value := fields.get(attr):
                if value.startswith("#"):
                    continue
                if value.startswith(self.base) and not value.startswith("//"):
                    name = urlsplit(value).path.removeprefix(self.base)
                    if name.endswith("/") or not name:
                        name += "index.html"
                    if name in self.files:
                        continue
                if tag == "a" and attr == "href" and value in PUBLIC_EXTERNAL | self.event_urls:
                    continue
                raise ValueError("Enlace o recurso fuera de la lista permitida")


def audit_site(root, base):
    files = file_map(root)
    data = json.loads(files["eventos.json"].read_text(encoding="utf-8"))
    assert_keys(data, "events timezone coverage_start coverage_end last_successful_import_at attribution")
    assert_keys(data["attribution"], "source url license license_url changes")
    if data["attribution"]["url"] != DATASET or data["attribution"]["license_url"] != LICENSE:
        raise ValueError("Origen o licencia inesperados")
    expected = {".nojekyll", "index.html", "404.html", "creditos/index.html", "eventos.json"}
    expected.update("static/" + asset for asset in ASSETS)
    event_urls = set()
    for event in data["events"]:
        assert_keys(event, "id title category status date original_start_date venue price source source_updated_at last_verified_at")
        assert_keys(event["date"], "start_date end_date starts_at ends_at timezone precision")
        assert_keys(event["venue"], "municipality name latitude longitude coordinates_verified")
        assert_keys(event["price"], "type amount_minor currency")
        assert_keys(event["source"], "name url")
        if not re.fullmatch(r"ax-[0-9a-f]{32}", event["id"]):
            raise ValueError("Identificador público inválido")
        page = f"events/{event['id']}/index.html"
        if page in expected or not event_url(event["source"]["url"]):
            raise ValueError("Ficha duplicada o enlace de fuente inválido")
        expected.add(page)
        event_urls.add(event["source"]["url"])
        if (venue_name := event["venue"]["name"]) and ADDRESS.search(venue_name):
            raise ValueError("La denominación del recinto parece una dirección")
        for value in (event["title"], event["venue"]["municipality"], event["venue"]["name"]):
            if value is not None and public_text(value) != value:
                raise ValueError("Contacto o texto no autorizado en los datos públicos")
    if not event_urls or set(files) != expected:
        raise ValueError("El artefacto no coincide con la lista de archivos públicos")
    for name, path in files.items():
        suffix = PurePosixPath(name).suffix
        if suffix in BINARY:
            continue
        body = path.read_text(encoding="utf-8")
        scan_text(name, body)
        if suffix == ".html":
            html = StaticHTML(base, files, event_urls)
            html.feed(body)
            html.close()
            if not html.csp or not html.referrer:
                raise ValueError(f"{name}: faltan protecciones del navegador")
    return len(files)


def assert_keys(values, names):
    if not isinstance(values, dict) or set(values) != set(names.split()):
        raise ValueError("Campo no permitido en el catálogo público")


def audit_source(root):
    files = file_map(root)
    if not ROOT_SOURCE <= files.keys():
        raise ValueError("Faltan archivos del repositorio preparado")
    for name, path in files.items():
        if not allowed_source(name):
            raise ValueError(f"Archivo fuera de la lista de código público: {name}")
        if path.suffix not in BINARY:
            scan_text(name, path.read_text(encoding="utf-8"))
    return len(files)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--site", type=Path)
    target.add_argument("--source", type=Path)
    parser.add_argument("--base-path", type=site_root, default="/")
    args = parser.parse_args()
    try:
        count = audit_site(args.site, args.base_path) if args.site else audit_source(args.source)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f"Auditoría detenida: {error}\n")
    print(f"{count} archivos permitidos y revisados.")


if __name__ == "__main__":
    main()
