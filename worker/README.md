# WW3 Risk Model Worker API (`ww3-risk-api`)

Cloudflare Worker providing read-only REST API endpoints backed by Cloudflare D1 database `ww3-risk`.

## Architecture & Technology
- Runtime: Cloudflare Workers (pure JS module, zero dependencies, zero build)
- Storage: Cloudflare D1 (`DB` binding)
- Cache: `Cache-Control: public, max-age=60`
- CORS: `Access-Control-Allow-Origin: *` for all public read queries

## Endpoints

1. `GET /api/risk/latest`
   Latest snapshot overview (Total Index, Stage, 5 Layer scores, Gate multiplier, Peace capacity, Top drivers, and Scenario Probability Bands).

2. `GET /api/risk/history`
   Time-series of all stored snapshots + benchmark historical cases (1913, 1938, 1962, 1990, 2025) explicitly labeled with `retrospective_estimate: true`.

3. `GET /api/risk/layers`
   Detailed breakdown of the 5 structural layers (L1–L5) and peace gate, including all underlying 34 indicator observations with v0.3 data quality tracking fields.

4. `GET /api/data-status`
   System-wide data health report: total indicators, completeness percentage, fresh vs. stale count, and indicator-by-indicator provenance.

*Note: `/api/social-instability` is deliberately NOT implemented per v0.4 specification.*

## Testing

Zero external test frameworks required. Tests execute directly with Node's built-in test runner:

```bash
cd worker
node --test tests/index.test.js
```

Or from repo root:
```bash
node --test worker/tests/index.test.js
```
