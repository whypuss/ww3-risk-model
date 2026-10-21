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
  model_version: "0.4.0",
  scenario_id: "baseline_2026",
  total_index: 83.1,
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
            return snapshots.length > 0 ? { ...snapshots[0] } : null;
          }
          return null;
        },
        async all() {
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
    assert.equal(data.stage.number, 3);
    assert.equal(data.stage.code, "STAGE_3_PEACE_MECHANISM_FAILURE");
    assert.equal(data.layers.L1, 63.0);
    assert.equal(data.layers.L4, 74.5);
    assert.equal(data.gate.multiplier, 1.041);
    assert.equal(data.gate.peace_capacity, 44.9);
    assert.equal(data.probability_bands["1y"].central_pct, 8.9);
    assert.equal(data.drivers.length, 3);
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
});
