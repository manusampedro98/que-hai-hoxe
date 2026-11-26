from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Madrid")
CATEGORIES = {"music": "Música", "festival": "Fiestas", "culture": "Cultura"}
STATUSES = {"scheduled": "Programado", "cancelled": "Cancelado", "postponed": "Aplazado", "unknown": "Estado no confirmado"}


def now():
    return datetime.now(timezone.utc)


def interval(today: date, period: str):
    if period == "today":
        start, length = today, 1
    elif period == "tomorrow":
        start, length = today + timedelta(days=1), 1
    elif period == "weekend":
        start = today + timedelta(days=5 - today.weekday())
        length = 2
    elif period == "week":
        start, length = today, 7
    else:
        raise ValueError("Filtro desconocido")
    return start, start + timedelta(days=length)


def overlaps(event, start, end):
    d = event["date"]
    first = date.fromisoformat(d["start_date"])
    if d["ends_at"]:
        finish = datetime.fromisoformat(d["ends_at"]).astimezone(TZ)
        beginning = datetime.fromisoformat(d["starts_at"]).astimezone(TZ)
        return beginning < datetime.combine(end, datetime.min.time(), TZ) and finish > datetime.combine(start, datetime.min.time(), TZ)
    last = date.fromisoformat(d["end_date"] or d["start_date"])
    return first < end and last >= start


def price_label(price):
    kind = price["type"]
    if kind == "unknown":
        return "???"
    if kind == "free":
        return "Gratis"
    amount = price["amount_minor"]
    number = f"{amount // 100}" + (f",{amount % 100:02}" if amount % 100 else "")
    currency = "€" if price["currency"] == "EUR" else price["currency"]
    return ("Desde " if kind == "from" else "") + f"{number} {currency}"


def date_label(event):
    d = event["date"]
    first = date.fromisoformat(d["start_date"]).strftime("%d/%m/%Y")
    if d["end_date"] and d["end_date"] != d["start_date"]:
        first += " – " + date.fromisoformat(d["end_date"]).strftime("%d/%m/%Y")
    hour = datetime.fromisoformat(d["starts_at"]).astimezone(TZ).strftime("%H:%M") if d["starts_at"] else "Hora no disponible"
    return f"{first} · {hour}"


def sort_key(event):
    d = event["date"]
    return d["start_date"], d["starts_at"] is None, d["starts_at"] or "", event["title"].casefold(), event["id"]
