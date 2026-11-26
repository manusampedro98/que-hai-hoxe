import re
import json
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.config import Settings
from app.demo import demo_events
from app.services import CATEGORIES, STATUSES, TZ, date_label, now, price_label, sort_key

PACKAGE = Path(__file__).resolve().parent
CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https://www.ign.es/wmts/ign-base; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"


def create_app(settings=None, clock=now):
    settings = settings or Settings.from_env()
    app = FastAPI(debug=False, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
    templates = Jinja2Templates(directory=str(PACKAGE / "templates"))
    templates.env.globals.update(price_label=price_label, date_label=date_label, categories=CATEGORIES, statuses=STATUSES)
    app.mount("/static", StaticFiles(directory=PACKAGE / "static"), name="static")

    @app.middleware("http")
    async def security(request, call_next):
        try:
            if settings.allowed_peers is not None and (not request.client or request.client.host not in settings.allowed_peers):
                response = JSONResponse({"detail": "Acceso no permitido"}, status_code=403)
            else:
                response = await call_next(request)
        except Exception:
            response = JSONResponse({"detail": "Catálogo no disponible. Reinténtalo."}, status_code=503)
        response.headers.update({"Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Cache-Control": "no-store", "Permissions-Policy": "geolocation=(), camera=(), microphone=()"})
        return response

    def catalogue():
        if settings.demo:
            return demo_events(clock()), None
        from app.db.repository import read_catalogue
        return read_catalogue(settings.db_path)

    def metadata():
        current = clock()
        events, last = catalogue()
        if len(json.dumps(events,ensure_ascii=False).encode()) > 20*1024*1024:
            raise RuntimeError('Catálogo excede el límite de respuesta; no se trunca')
        day = current.astimezone(TZ).date()
        end = day + timedelta(days=90)
        from app.services import overlaps
        return dict(events=sorted([e for e in events if overlaps(e, day, end)], key=sort_key), timezone="Europe/Madrid", server_now=current.isoformat(), coverage_start=day.isoformat(), coverage_end=end.isoformat(), last_successful_import_at=last, stale=not last or (current - datetime.fromisoformat(last)).total_seconds() > 86400, demo_mode=settings.demo)

    def get_event(event_id):
        if not re.fullmatch(r"[a-zA-Z0-9-]{1,64}", event_id):
            return None
        events, _ = catalogue()
        return next((e for e in events if e["id"] == event_id), None)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return templates.TemplateResponse(request=request, name="index.html", context={"demo": settings.demo})

    @app.get("/api/events")
    def events():
        return metadata()

    @app.get("/api/municipalities")
    def municipalities():
        return sorted({e["venue"]["municipality"] for e in metadata()["events"] if e["venue"]["municipality"]})

    @app.get("/api/events/{event_id}")
    def event_api(event_id: str):
        event = get_event(event_id)
        return event if event else JSONResponse({"detail": "Evento no encontrado"}, status_code=404)

    @app.get("/events/{event_id}", response_class=HTMLResponse)
    def detail(request: Request, event_id: str):
        event = get_event(event_id)
        return templates.TemplateResponse(request=request, name="detail.html", context={"event": event, "demo": settings.demo}, status_code=200 if event else 404)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app
