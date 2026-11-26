from datetime import datetime, timedelta
from app.services import TZ


def demo_events(clock):
    today = clock.astimezone(TZ).date()
    rows = [
        ("Noite de música atlántica · ejemplo", "music", "A Coruña", "Sala de ejemplo", "unknown", None, 0),
        ("Unha festa para toda a vila · ejemplo", "festival", "Vigo", "Plaza de ejemplo", "from", 1500, 1),
        ("Mostra de ilustración galega · ejemplo", "culture", "Lugo", None, "free", 0, 0),
        ("Sesión acústica de outono · ejemplo", "music", "Ourense", "Auditorio de ejemplo", "exact", 1500, 2),
        ("Encontro de teatro e historias do mar cun título moi longo · ejemplo", "culture", "Santiago de Compostela", None, "unknown", None, 3),
        ("Concerto aprazado · ejemplo", "music", "A Coruña", None, "unknown", None, 4),
        ("Festa cancelada · ejemplo", "festival", "Vigo", None, "unknown", None, 5),
    ]
    events = []
    for i, (title, category, municipality, venue, kind, amount, offset) in enumerate(rows):
        day = today + timedelta(days=offset)
        instant = datetime.combine(day, datetime.min.time().replace(hour=20, minute=30), TZ) if i in (0, 1, 3) else None
        events.append(dict(id=f"demo-{i+1}", title=title, category=category,
            description="Evento ficticio para probar la aplicación. Fechas, recintos y precios son ejemplos y no corresponden a una programación real.",
            date=dict(start_date=day.isoformat(), end_date=None, starts_at=instant.isoformat() if instant else None, ends_at=None, timezone="Europe/Madrid", precision="datetime" if instant else "date"),
            venue=dict(name=venue, municipality_code=None, municipality=municipality, address=None, latitude=None, longitude=None, coordinates_verified=False),
            price=dict(type=kind, amount_minor=amount, currency="EUR" if amount is not None else None),
            source=dict(name="Demostración", url=None), tickets_url=None, image_path=None,
            status="postponed" if i == 5 else "cancelled" if i == 6 else "scheduled",
            original_start_date=day.isoformat() if i == 5 else None, last_verified_at=None, is_demo=True))
    return events
