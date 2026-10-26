/**
 * Unit tests for Cloudflare Worker API using Node built-in test runner.
 * Zero external dependencies.
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import worker from "../src/index.js";

// Mock snapshot sample matching C2a D1 schema
const MOCK_SNAPSHOT = {
  id: "snapshot_baseline_2026_test",
  computed_at: "2026-10-21T14:38:00Z",
  model_version: "0.6.0",
  scenario_id: "baseline_2026",
  total_index: 83.1,
  structural_index: 83.5,
  pulse_adjustment: -0.4,
  composite_index: 83.1,
  pulse_json: JSON.stringify({
    computed_at: "2026-10-21T14:38:00Z",
    pulse_adjustment: -0.4,
    signals: {
      polymarket_war_risk: { contribution: -0.4 },
    },
  }),
  stage: 3,
  base_score: 68.8,
  interaction_bonus: 11.43,
  gate_multiplier: 1.041,
  peace_capacity: 44.9,
  band_1y: 8.9,
  band_5y: 30.6,
  band_10y: 48.8,
  layers_json: JSON.stringify({
    L1: 63.0,
    L2: 71.3,
    L3: 64.9,
    L4: 74.5,
    L5: 71.9,
  }),
  drivers_json: JSON.stringify([
    { layer: "L4", id: "l4_military_expenditure_growth", name: "軍費年增率", value: 95.0, weight: 1.0 },
    { layer: "L5", id: "l5_economic_stagnation", name: "長期停滯預期", value: 93.0, weight: 1.0 },
    { layer: "L4", id: "l4_nuclear_breakout", name: "核突破恐慌", value: 90.0, weight: 1.0 },
  ]),
};

const MOCK_OBSERVATIONS = [
  {
    snapshot_id: "snapshot_baseline_2026_test",
    indicator_id: "l1_food_security",
    layer: "L1",
    raw_value: "30.7",
    raw_unit: "% (庫存消費比)",
    normalized_score: 52.0,
    evidence_level: "inference",
    source_name: "FAO Cereal Supply",
    source_url: "https://www.fao.org",
    observation_date: "2024-10",
    publication_date: "2024-10-04",
    last_checked: "2026-10-21",
    stale_after_days: 180,
    is_stale: 1,
  },
  {
    snapshot_id: "snapshot_baseline_2026_test",
    indicator_id: "l4_military_expenditure_growth",
    layer: "L4",
    raw_value: "24430億美元",
    raw_unit: "USD",
    normalized_score: 95.0,
    evidence_level: "verified",
    source_name: "SIPRI",
    source_url: "https://www.sipri.org",
    observation_date: "2024-04",
    publication_date: "2024-04-22",
    last_checked: "2026-10-21",
    stale_after_days: 365,
    is_stale: 0,
  },
  {
    snapshot_id: "snapshot_baseline_2026_test",
    indicator_id: "gate_diplomatic_trust",
    layer: "Gate",
    raw_value: "熱線有限恢復",
    raw_unit: "",
    normalized_score: 35.0,
    evidence_level: "illustrative",
    source_name: "UN Peacemaker",
    source_url: "",
    observation_date: "2026",
    publication_date: "2026",
    last_checked: "2026-10-21",
    stale_after_days: 365,
    is_stale: 0,
  },
];

function createMockDb({ snapshots = [], observations = [] } = {}) {
  return {
    prepare(sql) {
      let boundParams = [];
      return {
        bind(...args) {
          boundParams = args;
          return this;
        },
        async first() {
          if (sql.includes("FROM index_snapshots")) {
            return snapshots.length > 0 ? { ...snapshots[snapshots.length - 1] } : null;
          }
          return null;
        },
        async all() {
          if (sql.includes("substr(computed_at, 1, 10)") && sql.includes("daily_points")) {
            // monthly aggregation query
            const dailyMap = new Map();
            for (const s of snapshots) {
              const day = s.computed_at.slice(0, 10);
              const cur = dailyMap.get(day);
              if (!cur || s.computed_at > cur.computed_at) {
                dailyMap.set(day, s);
              }
            }
            const monthMap = new Map();
            for (const [day, s] of dailyMap.entries()) {
              const month = day.slice(0, 7);
              if (!monthMap.has(month)) {
                monthMap.set(month, { days: [], composites: [], structurals: [] });
              }
              const comp = s.composite_index !== undefined ? s.composite_index : s.total_index;
              const struct = s.structural_index !== undefined ? s.structural_index : s.total_index;
              monthMap.get(month).days.push(day);
              monthMap.get(month).composites.push(comp);
              monthMap.get(month).structurals.push(struct);
            }
            const results = [];
            for (const [month, data] of Array.from(monthMap.entries()).sort()) {
              const avgComp = data.composites.reduce((a, b) => a + b, 0) / data.composites.length;
              const avgStruct = data.structurals.reduce((a, b) => a + b, 0) / data.structurals.length;
              results.push({
                month,
                n_days: data.days.length,
                composite_index: Math.round(avgComp * 100) / 100,
                structural_index: Math.round(avgStruct * 100) / 100,
              });
            }
            return { results };
          }
          if (sql.includes("substr(computed_at, 1, 10)")) {
            // daily aggregation query: group by day, take latest
            const dailyMap = new Map();
            for (const s of snapshots) {
              const day = s.computed_at.slice(0, 10);
              const cur = dailyMap.get(day);
              if (!cur || s.computed_at > cur.computed_at) {
                dailyMap.set(day, s);
              }
            }
            const results = Array.from(dailyMap.values())
              .sort((a, b) => a.computed_at.localeCompare(b.computed_at))
              .map((s) => ({
                id: s.id,
                computed_at: s.computed_at,
                date: s.computed_at.slice(0, 10),
                composite_index: s.composite_index !== undefined ? s.composite_index : s.total_index,
                structural_index: s.structural_index !== undefined ? s.structural_index : s.total_index,
                pulse_adjustment: s.pulse_adjustment !== undefined ? s.pulse_adjustment : 0.0,
                stage: s.stage,
              }));
            return { results };
          }
          if (sql.includes("FROM index_snapshots")) {
            return { results: snapshots.map((s) => ({ ...s })) };
          }
          if (sql.includes("FROM indicator_observations")) {
            if (boundParams.length > 0) {
              const snapId = boundParams[0];
              const filtered = observations.filter((o) => o.snapshot_id === snapId);
              return { results: filtered.map((o) => ({ ...o })) };
            }
            return { results: observations.map((o) => ({ ...o })) };
          }
          return { results: [] };
        },
      };
    },
  };
}

describe("WW3 Risk Model Worker API", () => {
  it("handles OPTIONS preflight with CORS headers", async () => {
    const req = new Request("https://api.ww3risk.org/api/risk/latest", { method: "OPTIONS" });
    const res = await worker.fetch(req, { DB: createMockDb() }, {});

    assert.equal(res.status, 204);
    assert.equal(res.headers.get("Access-Control-Allow-Origin"), "*");
    assert.ok(res.headers.get("Access-Control-Allow-Methods").includes("GET"));
  });

  it("returns 405 for non-GET methods", async () => {
    const req = new Request("https://api.ww3risk.org/api/risk/latest", { method: "POST" });
    const res = await worker.fetch(req, { DB: createMockDb() }, {});

    assert.equal(res.status, 405);
    const body = await res.json();
    assert.equal(body.error, "Method Not Allowed");
  });

  it("returns 404 for unknown endpoints", async () => {
    const req = new Request("https://api.ww3risk.org/api/unknown-endpoint");
    const res = await worker.fetch(req, { DB: createMockDb() }, {});

    assert.equal(res.status, 404);
    const body = await res.json();
    assert.equal(body.error, "Not Found");
  });

  it("returns 503 when D1 has no snapshots", async () => {
    const emptyDb = createMockDb({ snapshots: [], observations: [] });
    const endpoints = [
      "/api/risk/latest",
      "/api/risk/history",
      "/api/risk/layers",
      "/api/data-status",
    ];

    for (const ep of endpoints) {
      const req = new Request(`https://api.ww3risk.org${ep}`);
      const res = await worker.fetch(req, { DB: emptyDb }, {});
      assert.equal(res.status, 503, `Endpoint ${ep} should return 503 when DB is empty`);
      const body = await res.json();
      assert.equal(body.error, "Service Unavailable");
      assert.ok(body.message.includes("No snapshot available"));
    }
  });

  it("GET /api/risk/latest returns valid snapshot summary", async () => {
    const db = createMockDb({ snapshots: [MOCK_SNAPSHOT], observations: MOCK_OBSERVATIONS });
    const req = new Request("https://api.ww3risk.org/api/risk/latest");
    const res = await worker.fetch(req, { DB: db }, {});

    assert.equal(res.status, 200);
    assert.equal(res.headers.get("Access-Control-Allow-Origin"), "*");
    assert.equal(res.headers.get("Cache-Control"), "public, max-age=60");

    const data = await res.json();
    assert.equal(data.total_index, 83.1);
    assert.equal(data.composite_index, 83.1);
    assert.equal(data.structural_index, 83.5);
    assert.equal(data.pulse_adjustment, -0.4);
    assert.ok(data.pulse);
    assert.equal(data.stage.number, 3);
    assert.equal(data.stage.code, "STAGE_3_PEACE_MECHANISM_FAILURE");
    assert.equal(data.layers.L1, 63.0);
    assert.equal(data.layers.L4, 74.5);
    assert.equal(data.gate.multiplier, 1.041);
    assert.equal(data.gate.peace_capacity, 44.9);
    assert.equal(data.probability_bands["1y"].central_pct, 8.9);
    assert.equal(data.drivers.length, 3);
  });

  it("GET /api/pulse/latest returns latest pulse object", async () => {
    const db = createMockDb({ snapshots: [MOCK_SNAPSHOT] });
    const req = new Request("https://api.ww3risk.org/api/pulse/latest");
    const res = await worker.fetch(req, { DB: db }, {});

    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.pulse_adjustment, -0.4);
    assert.deepEqual(data.range, [-10.0, 10.0]);
    assert.ok(data.pulse);
    assert.equal(data.pulse.pulse_adjustment, -0.4);
  });

  it("GET /api/risk/history?granularity=daily aggregates to latest snapshot of each day", async () => {
    const multiSnapshots = [
      {
        id: "s1",
        computed_at: "2026-10-21T08:00:00Z",
        composite_index: 81.0,
        structural_index: 83.5,
        pulse_adjustment: -2.5,
        stage: 3,
      },
      {
        id: "s2",
        computed_at: "2026-10-21T12:00:00Z",
        composite_index: 82.0,
        structural_index: 83.5,
        pulse_adjustment: -1.5,
        stage: 3,
      },
      {
        id: "s3_last_of_day",
        computed_at: "2026-10-21T22:00:00Z",  // Last snapshot of 2026-10-21
        composite_index: 83.1,
        structural_index: 83.5,
        pulse_adjustment: -0.4,
        stage: 3,
      },
      {
        id: "s4",
        computed_at: "2026-10-22T06:00:00Z",
        composite_index: 83.4,
        structural_index: 83.5,
        pulse_adjustment: -0.1,
        stage: 3,
      },
    ];
    const db = createMockDb({ snapshots: multiSnapshots });
    const req = new Request("https://api.ww3risk.org/api/risk/history?granularity=daily");
    const res = await worker.fetch(req, { DB: db }, {});

    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.granularity, "daily");
    assert.equal(data.timezone, "UTC");
    assert.equal(data.total_points, 2);
    assert.equal(data.points.length, 2);

    // Day 1 must select the last snapshot of the day (s3_last_of_day)
    const day1 = data.points[0];
    assert.equal(day1.date, "2026-10-21");
    assert.equal(day1.computed_at, "2026-10-21T22:00:00Z");
    assert.equal(day1.composite_index, 83.1);
    assert.equal(day1.structural_index, 83.5);
    assert.equal(day1.pulse_adjustment, -0.4);

    // Day 2
    const day2 = data.points[1];
    assert.equal(day2.date, "2026-10-22");
    assert.equal(day2.composite_index, 83.4);
  });

  it("GET /api/risk/history?granularity=monthly computes daily points average and verifies n_days", async () => {
    const multiSnapshots = [
      // Month 1 (2026-10): 2 distinct days
      {
        id: "m1_d1",
        computed_at: "2026-10-21T10:00:00Z",
        composite_index: 83.0,
        structural_index: 83.5,
        stage: 3,
      },
      {
        id: "m1_d2",
        computed_at: "2026-10-22T10:00:00Z",
        composite_index: 84.0,
        structural_index: 83.5,
        stage: 3,
      },
      // Month 2 (2026-11): 3 distinct days
      {
        id: "m2_d1",
        computed_at: "2026-11-01T10:00:00Z",
        composite_index: 80.0,
        structural_index: 82.0,
        stage: 3,
      },
      {
        id: "m2_d2",
        computed_at: "2026-11-02T10:00:00Z",
        composite_index: 82.0,
        structural_index: 82.0,
        stage: 3,
      },
      {
        id: "m2_d3",
        computed_at: "2026-11-03T10:00:00Z",
        composite_index: 84.0,
        structural_index: 82.0,
        stage: 3,
      },
    ];
    const db = createMockDb({ snapshots: multiSnapshots });
    const req = new Request("https://api.ww3risk.org/api/risk/history?granularity=monthly");
    const res = await worker.fetch(req, { DB: db }, {});

    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.granularity, "monthly");
    assert.equal(data.total_points, 2);

    const oct = data.points[0];
    assert.equal(oct.month, "2026-10");
    assert.equal(oct.n_days, 2);
    assert.equal(oct.composite_index, 83.5); // (83.0 + 84.0) / 2 = 83.5
    assert.equal(oct.structural_index, 83.5);

    const nov = data.points[1];
    assert.equal(nov.month, "2026-11");
    assert.equal(nov.n_days, 3);
    assert.equal(nov.composite_index, 82.0); // (80.0 + 82.0 + 84.0) / 3 = 82.0
    assert.equal(nov.structural_index, 82.0);
  });

  it("GET /api/risk/history returns snapshots and retrospective historical cases", async () => {
    const db = createMockDb({ snapshots: [MOCK_SNAPSHOT], observations: MOCK_OBSERVATIONS });
    const req = new Request("https://api.ww3risk.org/api/risk/history");
    const res = await worker.fetch(req, { DB: db }, {});

    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.snapshots.length, 1);
    assert.equal(data.snapshots[0].total_index, 83.1);

    // Verify historical benchmarks
    assert.ok(data.historical_benchmarks.length >= 5);
    for (const h of data.historical_benchmarks) {
      assert.equal(h.retrospective_estimate, true, `Historical case ${h.id} must have retrospective_estimate=true`);
      assert.ok(h.year > 0);
      assert.ok(h.total_index > 0);
    }
    const h1913 = data.historical_benchmarks.find((h) => h.id === "hist_1913");
    assert.equal(h1913.total_index, 96.1);
    const h1938 = data.historical_benchmarks.find((h) => h.id === "hist_1938");
    assert.equal(h1938.total_index, 99.6);
  });

  it("GET /api/risk/layers returns layer groupings and observations", async () => {
    const db = createMockDb({ snapshots: [MOCK_SNAPSHOT], observations: MOCK_OBSERVATIONS });
    const req = new Request("https://api.ww3risk.org/api/risk/layers");
    const res = await worker.fetch(req, { DB: db }, {});

    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.snapshot_id, MOCK_SNAPSHOT.id);
    assert.equal(data.total_index, 83.1);
    assert.ok(data.layers.L1);
    assert.equal(data.layers.L1.score, 63.0);
    assert.equal(data.layers.L1.indicators[0].id, "l1_food_security");
    assert.equal(data.layers.L1.indicators[0].is_stale, true);

    assert.ok(data.layers.Gate);
    assert.equal(data.layers.Gate.indicators[0].id, "gate_diplomatic_trust");
  });

  it("GET /api/data-status returns completeness and fresh/stale breakdown", async () => {
    const db = createMockDb({ snapshots: [MOCK_SNAPSHOT], observations: MOCK_OBSERVATIONS });
    const req = new Request("https://api.ww3risk.org/api/data-status");
    const res = await worker.fetch(req, { DB: db }, {});

    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.total_indicators, 3);
    assert.equal(data.fresh_count, 2);
    assert.equal(data.stale_count, 1);
    assert.equal(data.completeness_pct, 100.0);
    assert.equal(data.indicators.length, 3);
  });

  it("GET /api/feeds/latest returns all 4 feeds with correct shape", async () => {
    const mockFeeds = [
      { feed_id: "gdelt", fetched_at: "2026-10-26T06:00:00Z", status: "ok", payload_json: JSON.stringify({ value: 5.2, date: "2026-10-26" }), error: null },
      { feed_id: "opensky", fetched_at: "2026-10-26T05:00:00Z", status: "ok", payload_json: JSON.stringify({ total_visible: 123, boxes: {} }), error: null },
      { feed_id: "hormuz", fetched_at: "2026-10-26T06:15:00Z", status: "ok", payload_json: JSON.stringify({ last24h: { in: 10, out: 8, total: 18, tankers: 5 }, fleet: { vessels: 42 }, feed: { health: "ok" } }), error: null },
      { feed_id: "polymarket", fetched_at: "2026-10-26T06:20:00Z", status: "ok", payload_json: JSON.stringify({ markets: [] }), error: null },
    ];
    const db = createMockDb({ snapshots: [MOCK_SNAPSHOT], observations: MOCK_OBSERVATIONS });
    db.prepare = function(sql) {
      let boundParams = [];
      return {
        bind(...args) { boundParams = args; return this; },
        async first() {
          if (sql.includes("FROM live_feed_snapshots")) {
            const fid = boundParams[0];
            return mockFeeds.find(f => f.feed_id === fid) || null;
          }
          return MOCK_SNAPSHOT;
        },
        async all() { return { results: [] }; },
      };
    };
    const req = new Request("https://api.ww3risk.org/api/feeds/latest");
    const res = await worker.fetch(req, { DB: db }, {});

    assert.equal(res.status, 200);
    const data = await res.json();
    assert.ok(data.feeds);
    assert.equal(data.feeds.length, 4);
    for (const feed of data.feeds) {
      assert.ok(feed.feed_id);
      assert.ok(["gdelt", "opensky", "hormuz", "polymarket"].includes(feed.feed_id));
      assert.ok(["ok", "error", "stale", "never_fetched"].includes(feed.status));
      assert.ok(typeof feed.fetched_at === "string" || feed.fetched_at === null);
      assert.ok(feed.payload === null || typeof feed.payload === "object");
      assert.ok(feed.error === null || typeof feed.error === "string");
    }
  });

  it("GET /api/feeds/latest returns never_fetched for missing feed rows", async () => {
    const db = createMockDb({ snapshots: [MOCK_SNAPSHOT], observations: MOCK_OBSERVATIONS });
    db.prepare = function(sql) {
      let boundParams = [];
      return {
        bind(...args) { boundParams = args; return this; },
        async first() {
          if (sql.includes("FROM live_feed_snapshots")) {
            return null;
          }
          return MOCK_SNAPSHOT;
        },
        async all() { return { results: [] }; },
      };
    };
    const req = new Request("https://api.ww3risk.org/api/feeds/latest");
    const res = await worker.fetch(req, { DB: db }, {});

    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.feeds.length, 4);
    for (const feed of data.feeds) {
      assert.equal(feed.status, "never_fetched");
      assert.equal(feed.fetched_at, null);
      assert.equal(feed.payload, null);
      assert.equal(feed.error, null);
    }
  });

  it("GET /api/feeds/polymarket returns markets with yes_token_id when Gamma succeeds", async () => {
    const mockPulseWithMarkets = {
      ...MOCK_SNAPSHOT,
      pulse_json: JSON.stringify({
        computed_at: "2026-10-21T14:38:00Z",
        pulse_adjustment: -0.4,
        signals: {
          polymarket_war_risk: {
            contribution: -0.4,
            details: {
              monitored_markets: [
                { id: "1124834", name: "US x Russia military clash by December 31, 2026?", short: "US-RU Clash" },
                { id: "2749367", name: "Will Russia invade a NATO country by December 31, 2026?", short: "RU-NATO Invasion" },
                { id: "2749382", name: "NATO/EU troops fighting in Ukraine by December 31, 2026?", short: "NATO Troops in UA" },
              ],
            },
          },
        },
      }),
    };
    const db = createMockDb({ snapshots: [mockPulseWithMarkets], observations: MOCK_OBSERVATIONS });
    // Mock fetch for Gamma API
    const originalFetch = global.fetch;
    global.fetch = async (url) => {
      if (url.includes("gamma-api.polymarket.com/markets/")) {
        const mid = url.split("/").pop();
        const mockMarket = {
          question: "Test Market",
          outcomes: ["No", "Yes"],
          clobTokenIds: ["token_no", "token_yes"],
          outcomePrices: JSON.stringify(["0.95", "0.05"]),
          volume: "1000000",
        };
        return {
          ok: true,
          status: 200,
          json: async () => mockMarket,
        };
      }
      return { ok: false, status: 404 };
    };

    const req = new Request("https://api.ww3risk.org/api/feeds/polymarket");
    const res = await worker.fetch(req, { DB: db }, {});

    global.fetch = originalFetch;

    assert.equal(res.status, 200);
    const data = await res.json();
    assert.ok(data.markets);
    assert.equal(data.markets.length, 3);
    for (const m of data.markets) {
      assert.ok(m.id);
      assert.ok(m.question);
      assert.ok(m.short);
      assert.ok(m.yes_token_id === "token_yes");
      assert.ok(typeof m.midpoint === "string");
      assert.ok(m.fetched_at);
    }
    assert.equal(data.fallback, false);
    assert.equal(data.error, null);
  });

  it("Gamma API string fields: outcomes and clobTokenIds as JSON strings still parse correctly", async () => {
    const mockPulseWithMarkets = {
      ...MOCK_SNAPSHOT,
      pulse_json: JSON.stringify({
        computed_at: "2026-10-21T14:38:00Z",
        pulse_adjustment: -0.4,
        signals: {
          polymarket_war_risk: {
            contribution: -0.4,
            details: {
              monitored_markets: [
                { id: "1124834", name: "Test Market?", short: "Test Market" },
              ],
            },
          },
        },
      }),
    };
    const db = createMockDb({ snapshots: [mockPulseWithMarkets], observations: MOCK_OBSERVATIONS });
    const originalFetch = global.fetch;
    global.fetch = async (url) => {
      if (url.includes("gamma-api.polymarket.com/markets/")) {
        // Return outcomes and clobTokenIds as JSON-encoded STRINGS (the bug scenario)
        const mockMarket = {
          question: "Test Market?",
          outcomes: '["No", "Yes"]', // JSON string, not array
          clobTokenIds: '["token_no", "token_yes"]', // JSON string, not array
          outcomePrices: JSON.stringify(["0.95", "0.05"]),
          volume: "1000000",
        };
        return {
          ok: true,
          status: 200,
          json: async () => mockMarket,
        };
      }
      return { ok: false, status: 404 };
    };

    const req = new Request("https://api.ww3risk.org/api/feeds/polymarket");
    const res = await worker.fetch(req, { DB: db }, {});

    global.fetch = originalFetch;

    assert.equal(res.status, 200);
    const data = await res.json();
    assert.ok(data.markets);
    assert.equal(data.markets.length, 1);
    const m = data.markets[0];
    assert.equal(m.id, "1124834");
    assert.equal(m.yes_token_id, "token_yes"); // Must correctly find Yes token even with string fields
    assert.equal(m.midpoint, "5.00");
    assert.ok(m.short);
    assert.equal(data.fallback, false);
  });

  it("GET /api/feeds/polymarket returns fallback when Gamma fails", async () => {
    const db = createMockDb({ snapshots: [MOCK_SNAPSHOT], observations: MOCK_OBSERVATIONS });
    const originalFetch = global.fetch;
    global.fetch = async () => ({ ok: false, status: 500 });

    const req = new Request("https://api.ww3risk.org/api/feeds/polymarket");
    const res = await worker.fetch(req, { DB: db }, {});

    global.fetch = originalFetch;

    assert.equal(res.status, 200);
    const data = await res.json();
    assert.equal(data.markets.length, 0);
    assert.equal(data.fallback, true);
    assert.ok(data.error && data.error.includes("Gamma API unavailable"));
  });
});
