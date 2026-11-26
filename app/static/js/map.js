import { priceLabel, dateLabel, hasPosition } from "./rules.mjs";
export { hasPosition } from "./rules.mjs";

// Origen cerrado; no acepta URLs de usuario ni de eventos para descargar teselas.
const TILE_URL =
  "https://www.ign.es/wmts/ign-base?SERVICE=WMTS&VERSION=1.0.0&REQUEST=GetTile&LAYER=IGNBaseTodo&STYLE=default&FORMAT=image/jpeg&TILEMATRIXSET=GoogleMapsCompatible&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}";
const node = (tag, text) => {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  return el;
};

export function createMapView({ getView, setView, onDetail, eventLink, consentKey }) {
  const cards = document.querySelector("#cards");
  const controls = node("div");
  controls.className = "view-switch";
  controls.setAttribute("aria-label", "Vista de resultados");
  const list = node("button", "Lista");
  const mapButton = node("button", "Mapa");
  for (const button of [list, mapButton]) {
    button.type = "button";
    controls.append(button);
  }
  document.querySelector(".results-heading").append(controls);
  const host = node("div");
  host.hidden = true;
  cards.before(host);
  host.append(document.querySelector("#map-ui").content.cloneNode(true));
  const $ = (id) => host.querySelector("#" + id);
  let map,
    markers,
    L,
    events = [],
    visible = false,
    loading = false,
    tileFailed = false,
    timer,
    tileLayer,
    resourceAttempt = 0;
  let consent = false;
  try {
    consent = sessionStorage.getItem(consentKey) === "ign-v1";
  } catch {}

  function choose(view) {
    setView(view);
  }
  list.onclick = () => choose("list");
  mapButton.onclick = () => choose("map");
  function destroy() {
    clearTimeout(timer);
    if (map) {
      if (tileLayer) {
        tileLayer.off();
        tileLayer = null;
      }
      map.stop();
      map.remove();
      map = null;
      markers = null;
    }
  }
  function warning(text) {
    $("map-message").textContent = text;
  }
  async function activate() {
    if (loading) return;
    consent = true;
    try {
      sessionStorage.setItem(consentKey, "ign-v1");
    } catch {}
    $("map-consent").hidden = true;
    $("event-map").hidden = false;
    if (!events.some(hasPosition)) {
      warning(
        "No hay ubicaciones verificadas para estos resultados. La lista sigue disponible.",
      );
      return;
    }
    if (!L) {
      loading = true;
      resourceAttempt += 1;
      const script = `../vendor/leaflet/leaflet.js?attempt=${resourceAttempt}`;
      let resourceTimer;
      warning("Cargando recursos locales del mapa…");
      try {
        if (!document.querySelector("#leaflet-style")) {
          const style = node("link");
          style.id = "leaflet-style";
          style.rel = "stylesheet";
          style.href = new URL("../vendor/leaflet/leaflet.css", import.meta.url).href;
          const ready = new Promise((resolve, reject) => {
            style.onload = resolve;
            style.onerror = reject;
          });
          document.head.append(style);
          await Promise.race([
            Promise.all([
              ready,
              import(script),
            ]),
            new Promise((_, reject) => {
              resourceTimer = setTimeout(
                () => reject(Error("Tiempo agotado")),
                10000,
              );
            }),
          ]);
        } else
          await import(script);
        L = window.L;
        if (!L) throw Error("Leaflet no disponible");
      } catch {
        document.querySelector("#leaflet-style")?.remove();
        warning(
          "No se pudieron cargar los recursos del mapa. Puedes seguir usando la lista.",
        );
        $("event-map").hidden = true;
        $("activate-map").textContent = "Reintentar mapa";
        $("map-consent").hidden = false;
        return;
      } finally {
        clearTimeout(resourceTimer);
        loading = false;
      }
    }
    if (visible) draw();
  }
  $("activate-map").onclick = activate;

  function draw() {
    if (!map) {
      map = L.map($("event-map"), {
        scrollWheelZoom: false,
        minZoom: 6,
        maxZoom: 18,
        zoomAnimation: false,
        fadeAnimation: false,
        markerZoomAnimation: false,
      }).setView([42.8, -8.2], 7);
      map.attributionControl.setPrefix(false);
      tileFailed = false;
      warning("Cargando mapa de fondo…");
      const tiles = L.tileLayer(TILE_URL, {
        attribution:
          '<a href="https://www.ign.es/" target="_blank" rel="noopener noreferrer">CC BY 4.0 scne.es · IGN</a>',
        bounds: [
          [41.7, -9.6],
          [43.9, -6.7],
        ],
        noWrap: true,
        keepBuffer: 0,
        updateWhenIdle: true,
        minZoom: 6,
        maxZoom: 18,
      });
      tileLayer = tiles;
      tiles.on("tileerror", () => {
        if (tileLayer !== tiles) return;
        clearTimeout(timer);
        tileFailed = true;
        warning(
          "No se han podido cargar algunas teselas del IGN. La lista completa sigue disponible debajo.",
        );
      });
      tiles.on("tileload", () => {
        if (tileLayer !== tiles) return;
        clearTimeout(timer);
        if (!tileFailed)
          warning("Mapa del IGN. La lista completa sigue disponible debajo.");
      });
      timer = setTimeout(
        () =>
          warning(
            "El mapa de fondo tarda en responder. La lista completa sigue disponible debajo.",
          ),
        15000,
      );
      tiles.addTo(map);
      markers = L.layerGroup().addTo(map);
      map.on("zoomend", renderMarkers);
      map.on("resize", renderMarkers);
    }
    map.invalidateSize();
    const positioned = events.filter(hasPosition);
    if (positioned.length) {
      map.fitBounds(
        L.latLngBounds(
          positioned.map((e) => [e.venue.latitude, e.venue.longitude]),
        ),
        { padding: [30, 30], maxZoom: 13, animate: false },
      );
    }
    renderMarkers();
  }

  function renderMarkers() {
    if (!map || !markers) return;
    markers.clearLayers();
    const positioned = events.filter(hasPosition);
    const groups = [];
    for (const event of positioned) {
      const point = map.latLngToLayerPoint([
        event.venue.latitude,
        event.venue.longitude,
      ]);
      let group = groups.find((g) => g.point.distanceTo(point) < 48);
      if (!group) {
        group = { point, events: [] };
        groups.push(group);
      }
      group.events.push(event);
    }
    for (const cluster of groups) {
      const group = cluster.events;
      const badge = node("span", String(group.length));
      const popup = node("div");
      popup.className = "event-popup";
      for (const event of group) {
        const item = node("section");
        const title = node("a", event.title);
        title.href = eventLink(event.id);
        title.onclick = onDetail;
        const date = node("p", dateLabel(event.date));
        const venue = node(
          "p",
          [event.venue.municipality, event.venue.name]
            .filter(Boolean)
            .join(" · "),
        );
        const price = node("p", priceLabel(event.price));
        price.className = "price";
        item.append(title, date, venue, price);
        popup.append(item);
      }
      L.marker([group[0].venue.latitude, group[0].venue.longitude], {
        icon: L.divIcon({
          className: "event-marker",
          html: badge,
          iconSize: [40, 40],
          iconAnchor: [20, 20],
        }),
        title: `${group.length} ${group.length === 1 ? "evento" : "eventos"} en esta zona`,
        keyboard: true,
      })
        .bindPopup(popup, {
          maxHeight: 260,
          maxWidth: Math.max(
            160,
            Math.min(300, $("event-map").clientWidth - 72),
          ),
        })
        .addTo(markers);
    }
    if (!positioned.length)
      warning(
        "No hay ubicaciones verificadas para estos resultados. La lista sigue disponible.",
      );
  }

  function update(nextEvents, available) {
    events = nextEvents;
    controls.hidden = !available;
    visible = getView() === "map" && available;
    host.hidden = !visible;
    list.setAttribute("aria-pressed", String(!visible));
    mapButton.setAttribute("aria-pressed", String(visible));
    if (!visible) {
      destroy();
      return;
    }
    const count = events.filter(hasPosition).length;
    $("map-count").textContent =
      `${count} de ${events.length} eventos con ubicación en el mapa · ${events.length - count} sin ubicación verificada. Todos aparecen en la lista.`;
    $("map-consent").hidden = consent;
    $("event-map").hidden = !consent || count === 0;
    if (count === 0) {
      destroy();
      warning(
        "No hay ubicaciones verificadas para estos resultados. La lista sigue disponible.",
      );
      return;
    }
    if (consent) activate();
    else
      warning("El mapa no realiza conexiones externas hasta que lo actives.");
  }
  return { update };
}
