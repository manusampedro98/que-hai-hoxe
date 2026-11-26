import baseAssert from "node:assert/strict";
let checks = 0;
const assert = Object.assign(
  (condition) => {
    checks++;
    baseAssert(condition);
  },
  {
    equal(...args) {
      checks++;
      baseAssert.equal(...args);
    },
    deepEqual(...args) {
      checks++;
      baseAssert.deepEqual(...args);
    },
  },
);
import {
  normalize,
  interval,
  matches,
  priceLabel,
  hasPosition,
} from "../app/static/js/rules.mjs";
assert.equal(normalize("  A  CORUÑA "), "a coruna");
for (const [day, start] of [
  ["2026-10-30", "2026-10-31"],
  ["2026-10-31", "2026-10-31"],
  ["2026-11-01", "2026-10-31"],
  ["2026-12-31", "2027-01-02"],
])
  assert.equal(interval(day, "weekend")[0], start);
assert.deepEqual(interval("2026-12-31", "week"), ["2026-12-31", "2027-01-07"]);
assert.equal(priceLabel({ type: "unknown", amount_minor: null }), "???");
assert.equal(priceLabel({ type: "free", amount_minor: 0 }), "Gratis");
assert.equal(
  priceLabel({ type: "exact", amount_minor: 1500, currency: "EUR" }),
  "15 €",
);
assert.equal(
  priceLabel({ type: "from", amount_minor: 1550, currency: "EUR" }),
  "Desde 15,50 €",
);
const event = {
  title: "Concerto",
  category: "music",
  venue: { municipality: "A Coruña", name: "Sala de exemplo" },
  date: {
    start_date: "2026-10-28",
    end_date: null,
    starts_at: null,
    ends_at: null,
  },
};
const state = {
  q: "CORUNA",
  municipality: "A Coruña",
  category: "music",
  period: "today",
};
assert(matches(event, state, "2026-10-28"));
assert(!matches(event, { ...state, category: "festival" }, "2026-10-28"));
assert(!matches(event, state, "2026-10-29"));
assert(!matches(event, { ...state, period: "tomorrow" }, "2026-10-28"));
const ongoing = {
  ...event,
  date: {
    start_date: "2026-10-27",
    end_date: "2026-10-29",
    starts_at: null,
    ends_at: null,
  },
};
assert(matches(ongoing, state, "2026-10-28"));
const midnight = {
  ...event,
  date: {
    start_date: "2026-10-27",
    starts_at: "2026-10-27T20:00:00+01:00",
    ends_at: "2026-10-28T00:00:00+01:00",
  },
};
assert(!matches(midnight, state, "2026-10-28"));
const atEleven = {
  ...event,
  date: { ...event.date, starts_at: "2026-10-28T10:00:00Z" },
};
assert(matches(atEleven, { ...state, q: "11:00" }, "2026-10-28"));
assert(!matches(atEleven, { ...state, q: "10:00" }, "2026-10-28"));
assert(!matches(event, { ...state, q: "11:00" }, "2026-10-28"));
assert(!matches(atEleven, { ...state, q: "24:00" }, "2026-10-28"));
assert(!matches(atEleven, { ...state, q: "11:60" }, "2026-10-28"));
const early = {
  ...atEleven,
  date: { ...event.date, starts_at: "2026-10-28T07:30:00Z" },
};
assert(matches(early, { ...state, q: "8:30" }, "2026-10-28"));
assert(
  !matches(
    atEleven,
    { ...state, q: "11:00", category: "culture" },
    "2026-10-28",
  ),
);
const summer = {
  ...event,
  date: {
    ...event.date,
    start_date: "2026-07-01",
    starts_at: "2026-07-01T09:00:00Z",
  },
};
assert(matches(summer, { ...state, q: "11:00" }, "2026-07-01"));
const located = {
  venue: { latitude: 42.88, longitude: -8.55, coordinates_verified: true },
};
assert(hasPosition(located));
assert(
  !hasPosition({ venue: { ...located.venue, coordinates_verified: false } }),
);
assert(
  !hasPosition({ venue: { ...located.venue, coordinates_verified: "true" } }),
);
assert(!hasPosition({ venue: { ...located.venue, latitude: 0 } }));
assert(!hasPosition({ venue: { ...located.venue, latitude: null } }));
assert(!hasPosition({ venue: { ...located.venue, longitude: NaN } }));
assert(!hasPosition({ venue: { ...located.venue, longitude: 8.55 } }));
console.log(`Reglas JS: ${checks} comprobaciones correctas`);
