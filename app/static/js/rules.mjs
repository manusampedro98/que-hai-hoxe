export const normalize = (s) =>
  (s || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim()
    .replace(/\s+/g, " ");
export const hasPosition = (event) =>
  event.venue.coordinates_verified === true &&
  Number.isFinite(event.venue.latitude) &&
  Number.isFinite(event.venue.longitude) &&
  event.venue.latitude >= 41.7 &&
  event.venue.latitude <= 43.9 &&
  event.venue.longitude >= -9.6 &&
  event.venue.longitude <= -6.7;
export function shift(day, amount) {
  const d = new Date(day + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() + amount);
  return d.toISOString().slice(0, 10);
}
export function interval(today, period) {
  let start = today,
    length = 1;
  if (period === "tomorrow") start = shift(today, 1);
  if (period === "week") length = 7;
  if (period === "weekend") {
    const day = new Date(today + "T12:00:00Z").getUTCDay();
    start = shift(today, day === 0 ? -1 : 6 - day);
    length = 2;
  }
  return [start, shift(start, length)];
}
export function localDay(instant) {
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Europe/Madrid",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(instant));
}
export function localTime(instant) {
  if (!instant) return null;
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Madrid",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(instant));
}
export function matches(event, state, today) {
  const [start, end] = interval(today, state.period);
  const d = event.date;
  // Calendar comparison preserves unknown hours and inclusive date-only intervals.
  const last = d.ends_at ? localDay(d.ends_at) : d.end_date || d.start_date;
  const endsAtMidnight =
    d.ends_at &&
    new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Madrid",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    }).format(new Date(d.ends_at)) === "00:00:00";
  const overlap =
    d.start_date < end && (last > start || (last === start && !endsAtMidnight));
  const query = normalize(state.q);
  const hourQuery = /^(\d{1,2}):(\d{2})$/.exec(query);
  const textMatches = hourQuery
    ? Number(hourQuery[1]) <= 23 &&
      Number(hourQuery[2]) <= 59 &&
      localTime(d.starts_at) ===
        `${hourQuery[1].padStart(2, "0")}:${hourQuery[2]}`
    : normalize(
        [event.title, event.venue.municipality, event.venue.name].join(" "),
      ).includes(query);
  return (
    overlap &&
    (!state.municipality || event.venue.municipality === state.municipality) &&
    (!state.category || event.category === state.category) &&
    textMatches
  );
}
export function priceLabel(price) {
  if (price.type === "unknown") return "???";
  if (price.type === "free") return "Gratis";
  const n = new Intl.NumberFormat("es-ES", {
    minimumFractionDigits: price.amount_minor % 100 ? 2 : 0,
    maximumFractionDigits: 2,
  }).format(price.amount_minor / 100);
  return (
    (price.type === "from" ? "Desde " : "") +
    n +
    " " +
    (price.currency === "EUR" ? "€" : price.currency)
  );
}
export function dateLabel(d) {
  const fmt = (day) =>
    new Intl.DateTimeFormat("es-ES", {
      day: "numeric",
      month: "short",
      year: "numeric",
      timeZone: "UTC",
    }).format(new Date(day + "T12:00:00Z"));
  const hour = d.starts_at
    ? new Intl.DateTimeFormat("es-ES", {
        timeZone: "Europe/Madrid",
        hour: "2-digit",
        minute: "2-digit",
        hourCycle: "h23",
      }).format(new Date(d.starts_at))
    : "Hora no disponible";
  return (
    fmt(d.start_date) +
    (d.end_date && d.end_date !== d.start_date ? " – " + fmt(d.end_date) : "") +
    " · " +
    hour
  );
}
