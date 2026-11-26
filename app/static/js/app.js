import {
  matches,
  priceLabel,
  dateLabel,
  localDay,
  interval,
} from "./rules.mjs";
import { createMapView, hasPosition } from "./map.js";
const $ = (selector) => document.querySelector(selector);
const publicRoot = document.documentElement.dataset.siteRoot;
const home = publicRoot || "/";
const filterSeparator = publicRoot ? "#" : "?";
const eventLink = (id) => `${home}events/${encodeURIComponent(id)}${publicRoot ? "/" : ""}`;
const storageKey = (key) => publicRoot ? `${publicRoot}:${key}` : key;
const categories = {
  music: ["♪", "Música"],
  festival: ["✦", "Fiestas"],
  culture: ["◇", "Cultura"],
};
const statuses = {
  cancelled: "Cancelado",
  postponed: "Aplazado",
  unknown: "Estado no confirmado",
};
const element = (tag, text, cls) => {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (cls) el.className = cls;
  return el;
};
const storage = {
  get(key) {
    try {
      return sessionStorage.getItem(storageKey(key));
    } catch {
      return null;
    }
  },
  set(key, value) {
    try {
      sessionStorage.setItem(storageKey(key), value);
    } catch {
      /* Private browser storage can be disabled. */
    }
  },
};
if ($("#back")) {
  const previous = storage.get("qhh-results");
  if (previous?.startsWith(home + filterSeparator)) $("#back").href = previous;
}
if ($("#cards")) {
  const params = new URLSearchParams(publicRoot ? location.hash.slice(1) : location.search);
  const state = {
    q: (params.get("q") || "").slice(0, 120),
    municipality: params.get("municipality") || "",
    category: params.get("category") || "",
    period: params.get("period") || "week",
    view: params.get("view") === "map" ? "map" : "list",
  };
  if (!["today", "tomorrow", "weekend", "week"].includes(state.period))
    state.period = "week";
  if (!Object.hasOwn(categories, state.category)) state.category = "";
  let data,
    fetched = 0,
    fetchedDay,
    loading = false,
    retryAfter = 0,
    serverOffset = 0;
  $("#search").value = state.q;
  const mapView = createMapView({
    eventLink,
    consentKey: storageKey("qhh-map-consent"),
    getView: () => state.view,
    setView: (view) => {
      state.view = view;
      render();
    },
    onDetail: () => storage.set("qhh-scroll", String(scrollY)),
  });
  function updateURL() {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(state)) if (v) p.set(k, v);
    const resultUrl = home + filterSeparator + p.toString();
    history.replaceState(null, "", resultUrl);
    storage.set("qhh-results", resultUrl);
  }
  function buttons() {
    for (const [id, key] of [
      ["dates", "period"],
      ["categories", "category"],
    ])
      $(`#${id}`)
        .querySelectorAll("button")
        .forEach((b) =>
          b.setAttribute(
            "aria-pressed",
            String(b.dataset.value === state[key]),
          ),
        );
  }
  function card(e) {
    const article = element("article", undefined, "card");
    const top = element("div", undefined, "card-top");
    const [symbol, label] = categories[e.category] || categories.culture;
    const icon = element("span", symbol, "category-icon");
    icon.setAttribute("aria-hidden", "true");
    top.append(icon, element("span", label.toUpperCase(), "category"));
    article.append(top);
    if (statuses[e.status])
      article.append(element("div", statuses[e.status], "state"));
    if (
      e.status === "scheduled" &&
      e.date.ends_at &&
      new Date(e.date.starts_at) < new Date(Date.now() + serverOffset) &&
      new Date(e.date.ends_at) > new Date(Date.now() + serverOffset)
    )
      article.append(element("div", "En curso", "state"));
    const title = element("h3");
    const link = element("a", e.title);
    link.href = eventLink(e.id);
    link.addEventListener("click", () =>
      storage.set("qhh-scroll", String(scrollY)),
    );
    title.append(link);
    const date = element("p");
    const time = element("time", dateLabel(e.date));
    time.dateTime = e.date.starts_at || e.date.start_date;
    date.append(time);
    article.append(
      title,
      date,
      element(
        "p",
        [e.venue.municipality, e.venue.name].filter(Boolean).join(" · ") ||
          "Ubicación no disponible",
      ),
    );
    const price = element("div", undefined, "price-row");
    price.append(
      element("span", priceLabel(e.price), "price"),
      element("span", "↗"),
    );
    article.append(price);
    return article;
  }
  function render() {
    if (!data) return;
    buttons();
    updateURL();
    const today = localDay(new Date(Date.now() + serverOffset));
    const events = data.events.filter((e) => matches(e, state, today));
    $("#cards").replaceChildren(...events.map(card));
    mapView.update(events, data.events.some(hasPosition));
    $("#results-title").textContent =
      `${events.length} ${events.length === 1 ? "evento" : "eventos"}${data.demo_mode ? " de demostración" : ""}`;
    const [a, b] = interval(today, state.period);
    $("#range").textContent =
      `Del ${a.split("-").reverse().join("/")} al ${b.split("-").reverse().join("/")} (fin excluido) · Europe/Madrid`;
    $("#status").replaceChildren();
    if (retryAfter) showLoadError();
    if (!events.length) {
      const box = element("div", undefined, "empty");
      box.append(
        element(
          "h3",
          data.events.length
            ? "No hay eventos con estos filtros"
            : "Todavía no hay eventos importados",
        ),
        element(
          "p",
          data.events.length
            ? "Prueba otra fecha o municipio."
            : publicRoot ? "Vuelve más tarde para consultar el catálogo actualizado." : "El propietario actualiza el catálogo desde la consola del PC.",
        ),
      );
      if (data.events.length) {
        const reset = element("button", "Borrar filtros", "button");
        reset.onclick = clear;
        box.append(reset);
      }
      $("#status").append(box);
    }
    const lastImport = new Date(data.last_successful_import_at);
    const stale = publicRoot ? Date.now() - lastImport.getTime() > 86400000 : data.stale;
    $("#freshness").textContent = data.demo_mode
      ? "Datos ficticios · Sin importación real"
      : data.last_successful_import_at
        ? `Última importación correcta: ${new Intl.DateTimeFormat("es-ES", { timeZone: "Europe/Madrid", dateStyle: "medium", timeStyle: "short" }).format(lastImport)}${stale ? " · Catálogo sin actualizar desde hace más de 24 horas. Confirma con la fuente." : ""}`
        : "Sin importación";
  }
  function clear() {
    Object.assign(state, {
      q: "",
      municipality: "",
      category: "",
      period: "week",
    });
    $("#search").value = "";
    $("#municipality").value = "";
    render();
  }
  function showLoadError() {
    const box = element("div", undefined, "empty");
    box.append(
      element("h3", data ? "No se pudo actualizar el catálogo" : "No se pudo cargar el catálogo"),
      element("p", data
        ? "Sigues viendo la última descarga correcta. Se reintentará automáticamente."
        : publicRoot ? "Se reintentará automáticamente." : "Comprueba que el servidor está encendido y que la base está inicializada."),
    );
    const retry = element("button", "Reintentar", "button");
    retry.onclick = load;
    box.append(retry);
    $("#status").append(box);
  }
  async function load() {
    if (loading) return;
    loading = true;
    const previous = data;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 15000);
    $("#cards").setAttribute("aria-busy", "true");
    if (!data) $("#status").textContent = publicRoot ? "Cargando catálogo…" : "Cargando catálogo local…";
    try {
      const response = await fetch(publicRoot ? `${home}eventos.json` : "/api/events", {
        signal: controller.signal,
        cache: "no-store",
      });
      if (!response.ok) throw Error("api");
      const payload = await response.json();
      if (!Array.isArray(payload.events)) throw Error("schema");
      data = payload;
      retryAfter = 0;
      fetched = Date.now();
      serverOffset = publicRoot ? 0 : new Date(data.server_now).getTime() - Date.now();
      fetchedDay = localDay(new Date(fetched + serverOffset));
      const select = $("#municipality");
      select.replaceChildren(new Option("Todos los municipios", ""));
      [...new Set(data.events.map((e) => e.venue.municipality).filter(Boolean))]
        .sort((a, b) => a.localeCompare(b, "es"))
        .forEach((name) => select.add(new Option(name, name)));
      if (
        state.municipality &&
        !Array.from(select.options).some((o) => o.value === state.municipality)
      )
        select.add(new Option(state.municipality, state.municipality));
      select.value = state.municipality;
      render();
      const saved = Number(storage.get("qhh-scroll"));
      if (saved) {
        requestAnimationFrame(() => scrollTo(0, saved));
        storage.set("qhh-scroll", "0");
      }
    } catch {
      data = previous;
      retryAfter = Date.now() + 60000;
      if (data) render();
      else {
        mapView.update([], false);
        $("#cards").replaceChildren();
        $("#results-title").textContent = "Catálogo no disponible";
        $("#status").replaceChildren();
        showLoadError();
      }
    } finally {
      loading = false;
      clearTimeout(timer);
      $("#cards").setAttribute("aria-busy", "false");
    }
  }
  let debounce;
  $("#search").addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      state.q = $("#search").value;
      render();
    }, 180);
  });
  $("#municipality").addEventListener("change", () => {
    state.municipality = $("#municipality").value;
    render();
  });
  for (const [id, key] of [
    ["dates", "period"],
    ["categories", "category"],
  ])
    $(`#${id}`).addEventListener("click", (event) => {
      const b = event.target.closest("button");
      if (b) {
        state[key] = b.dataset.value;
        render();
      }
    });
  $("#clear").onclick = clear;
  const refresh = () => {
    if (retryAfter) {
      if (Date.now() >= retryAfter) load();
    } else if (localDay(new Date(Date.now() + serverOffset)) !== fetchedDay ||
               Date.now() - fetched >= 900000) load();
  };
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) refresh();
  });
  setInterval(refresh, 60000);
  buttons();
  load();
}
