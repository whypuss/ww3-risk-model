/**
 * Unit tests for dashboard pure JavaScript functions.
 * Run with: node --test tests/dashboard_pure.test.js
 */

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  parsePolymarketWsMessage,
  isFeedStale,
  computeTrendDrivers,
} from "../src/ww3_risk/dashboard_pure.js";

describe("Dashboard Pure Functions", () => {
  describe("parsePolymarketWsMessage", () => {
    it("parses valid price message correctly", () => {
      const msg = JSON.stringify({
        type: "price",
        asset_id: "token_123",
        midpoint: 0.52,
        timestamp: 1700000000000,
      });
      const result = parsePolymarketWsMessage(msg);
      assert.deepEqual(result, {
        asset_id: "token_123",
        midpoint: 0.52,
        timestamp: 1700000000000,
      });
    });

    it("returns null for non-price type", () => {
      const msg = JSON.stringify({ type: "book", asset_id: "token_123", midpoint: 0.5 });
      assert.equal(parsePolymarketWsMessage(msg), null);
    });

    it("returns null for missing asset_id", () => {
      const msg = JSON.stringify({ type: "price", midpoint: 0.5 });
      assert.equal(parsePolymarketWsMessage(msg), null);
    });

    it("returns null for missing midpoint", () => {
      const msg = JSON.stringify({ type: "price", asset_id: "token_123" });
      assert.equal(parsePolymarketWsMessage(msg), null);
    });

    it("returns null for invalid JSON", () => {
      assert.equal(parsePolymarketWsMessage("not valid json"), null);
    });

    it("returns null for empty string", () => {
      assert.equal(parsePolymarketWsMessage(""), null);
    });
  });

  describe("isFeedStale", () => {
    const now = Date.now();
    const oneMin = 60 * 1000;
    const oneHour = 60 * oneMin;

    it("returns true for missing fetchedAt", () => {
      assert.equal(isFeedStale("gdelt", null), true);
      assert.equal(isFeedStale("gdelt", undefined), true);
      assert.equal(isFeedStale("gdelt", ""), true);
    });

    it("returns true for gdelt/hormuz older than 45 minutes", () => {
      const oldTime = new Date(now - 46 * oneMin).toISOString();
      assert.equal(isFeedStale("gdelt", oldTime), true);
      assert.equal(isFeedStale("hormuz", oldTime), true);
    });

    it("returns false for gdelt/hormuz within 45 minutes", () => {
      const recentTime = new Date(now - 30 * oneMin).toISOString();
      assert.equal(isFeedStale("gdelt", recentTime), false);
      assert.equal(isFeedStale("hormuz", recentTime), false);
    });

    it("returns true for opensky older than 180 minutes (3 hours)", () => {
      const oldTime = new Date(now - 181 * oneMin).toISOString();
      assert.equal(isFeedStale("opensky", oldTime), true);
    });

    it("returns false for opensky within 180 minutes", () => {
      const recentTime = new Date(now - 60 * oneMin).toISOString();
      assert.equal(isFeedStale("opensky", recentTime), false);
    });

    it("returns false for unknown feed ids", () => {
      const oldTime = new Date(now - 1000 * oneMin).toISOString();
      assert.equal(isFeedStale("unknown", oldTime), false);
    });
  });

  describe("computeTrendDrivers", () => {
    const basePoint = {
      date: "2026-10-21",
      composite_index: 83.0,
      structural_index: 83.0,
      pulse_adjustment: 0.0,
      signals: [
        { signal_id: "gdelt_conflict", name: "GDELT", contribution: 0.0, raw_value: 5.0, raw_unit: "%", status: "live" },
        { signal_id: "polymarket_war_risk", name: "Polymarket", contribution: -0.4, raw_value: 12.0, raw_unit: "%", status: "live" },
        { signal_id: "brent_oil_24h", name: "Brent Oil", contribution: 0.1, raw_value: 2.5, raw_unit: "%", status: "live" },
      ],
    };

    it("returns empty array for empty input", () => {
      assert.deepEqual(computeTrendDrivers([]), []);
    });

    it("returns baseline step for single point", () => {
      const points = [{ ...basePoint, date: "2026-10-21" }];
      const result = computeTrendDrivers(points);
      assert.equal(result.length, 1);
      assert.equal(result[0].baseline, true);
      assert.equal(result[0].from_date, "2026-10-21");
      assert.equal(result[0].to_date, "2026-10-21");
      assert.equal(result[0].delta, 0.0);
    });

    it("computes delta and drivers for two points with composite increase", () => {
      const points = [
        { ...basePoint, date: "2026-10-21" },
        {
          ...basePoint,
          date: "2026-10-22",
          composite_index: 85.0,
          structural_index: 84.5,
          pulse_adjustment: 0.5,
          signals: [
            { signal_id: "gdelt_conflict", name: "GDELT", contribution: 0.5, raw_value: 5.5, raw_unit: "%", status: "live" },
            { signal_id: "polymarket_war_risk", name: "Polymarket", contribution: -0.2, raw_value: 10.0, raw_unit: "%", status: "live" },
            { signal_id: "brent_oil_24h", name: "Brent Oil", contribution: 0.2, raw_value: 3.0, raw_unit: "%", status: "live" },
          ],
        },
      ];
      const result = computeTrendDrivers(points);
      assert.equal(result.length, 2);
      assert.equal(result[0].baseline, true);
      assert.equal(result[1].baseline, undefined);
      assert.equal(result[1].from_date, "2026-10-21");
      assert.equal(result[1].to_date, "2026-10-22");
      assert.equal(result[1].delta, 2.0);
      assert.ok(result[1].drivers.length > 0);
      assert.ok(result[1].drivers.length <= 3);
    });

    it("sorts drivers by absolute delta descending", () => {
      const points = [
        { ...basePoint, date: "2026-10-21" },
        {
          ...basePoint,
          date: "2026-10-22",
          composite_index: 90.0,
          structural_index: 88.0,
          pulse_adjustment: 2.0,
          signals: [
            { signal_id: "gdelt_conflict", name: "GDELT", contribution: 2.0, raw_value: 10.0, raw_unit: "%", status: "live" },
            { signal_id: "polymarket_war_risk", name: "Polymarket", contribution: 0.5, raw_value: 15.0, raw_unit: "%", status: "live" },
            { signal_id: "brent_oil_24h", name: "Brent Oil", contribution: 0.1, raw_value: 2.5, raw_unit: "%", status: "live" },
          ],
        },
      ];
      const result = computeTrendDrivers(points);
      const drivers = result[1].drivers;
      assert.ok(Math.abs(drivers[0].delta) >= Math.abs(drivers[1].delta));
      if (drivers.length > 2) {
        assert.ok(Math.abs(drivers[1].delta) >= Math.abs(drivers[2].delta));
      }
    });

    it("limits drivers to top 3", () => {
      const manySignals = [];
      for (let i = 0; i < 5; i++) {
        manySignals.push({
          signal_id: `signal_${i}`,
          name: `Signal ${i}`,
          contribution: (i + 1) * 0.5,
          raw_value: 10 + i,
          raw_unit: "%",
          status: "live",
        });
      }
      const points = [
        { ...basePoint, date: "2026-10-21", signals: manySignals.map(s => ({ ...s, contribution: 0 })) },
        { ...basePoint, date: "2026-10-22", composite_index: 88.0, signals: manySignals },
      ];
      const result = computeTrendDrivers(points);
      assert.equal(result[1].drivers.length, 3);
      assert.equal(result[1].omitted_count, 2);
    });

    it("marks data_gap true when signal status is not live", () => {
      const points = [
        { ...basePoint, date: "2026-10-21" },
        {
          ...basePoint,
          date: "2026-10-22",
          composite_index: 84.0,
          signals: [
            { signal_id: "gdelt_conflict", name: "GDELT", contribution: 0.5, raw_value: 5.5, raw_unit: "%", status: "unavailable" },
            { signal_id: "polymarket_war_risk", name: "Polymarket", contribution: -0.2, raw_value: 10.0, raw_unit: "%", status: "live" },
          ],
        },
      ];
      const result = computeTrendDrivers(points);
      const gdeltDriver = result[1].drivers.find(d => d.label === "GDELT");
      assert.ok(gdeltDriver);
      assert.equal(gdeltDriver.data_gap, true);
    });

    it("includes structural index change as driver", () => {
      const points = [
        { ...basePoint, date: "2026-10-21", structural_index: 83.0 },
        { ...basePoint, date: "2026-10-22", composite_index: 84.0, structural_index: 85.0, pulse_adjustment: -1.0 },
      ];
      const result = computeTrendDrivers(points);
      const structDriver = result[1].drivers.find(d => d.label.includes("結構指數"));
      assert.ok(structDriver);
      assert.equal(structDriver.delta, 2.0);
    });

    it("sets clamp_note when composite differs from structural + pulse", () => {
      const points = [
        { ...basePoint, date: "2026-10-21" },
        {
          ...basePoint,
          date: "2026-10-22",
          composite_index: 100.0,
          structural_index: 95.0,
          pulse_adjustment: 10.0,
        },
      ];
      const result = computeTrendDrivers(points);
      assert.equal(result[1].clamp_note, true);
    });

    it("sets flat true when no drivers", () => {
      const points = [
        { ...basePoint, date: "2026-10-21", signals: [] },
        { ...basePoint, date: "2026-10-22", composite_index: 83.0, structural_index: 83.0, pulse_adjustment: 0.0, signals: [] },
      ];
      const result = computeTrendDrivers(points);
      assert.equal(result[1].flat, true);
    });

    it("handles missing signals array gracefully", () => {
      const points = [
        { ...basePoint, date: "2026-10-21" },
        { ...basePoint, date: "2026-10-22", composite_index: 84.0, signals: null },
      ];
      const result = computeTrendDrivers(points);
      assert.equal(result.length, 2);
      assert.ok(result[1].drivers.length >= 0);
    });
  });
});