/**
 * WW3 Risk Model Cloudflare Worker API
 *
 * Endpoints:
 * - GET /api/risk/latest
 * - GET /api/risk/history
 * - GET /api/risk/layers
 * - GET /api/data-status
 *
 * Zero external dependencies. Uses Cloudflare D1 database binding 'DB'.
 */

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Cache-Control": "public, max-age=60",
};

const HISTORICAL_BENCHMARKS = [
  {
    id: "hist_1913",
    year: 1913,
    title: "1913年 一戰前夕（帝國爭霸與同盟剛性）",
    total_index: 96.1,
    stage: 4,
    layers: { L1: 71.0, L2: 73.8, L3: 63.4, L4: 86.3, L5: 86.3 },
    retrospective_estimate: true,
  },
  {
    id: "hist_1938",
    year: 1938,
    title: "1938年 二戰前夕（大蕭條潰敗、法西斯擴張與國聯崩塌）",
    total_index: 99.6,
    stage: 4,
    layers: { L1: 84.5, L2: 87.3, L3: 82.9, L4: 92.0, L5: 91.5 },
    retrospective_estimate: true,
  },
  {
    id: "hist_1962",
    year: 1962,
    title: "1962年 古巴導彈危機（核邊緣政策與近失案例）",
    total_index: 77.4,
    stage: 3,
    layers: { L1: 56.4, L2: 55.0, L3: 36.0, L4: 94.5, L5: 85.6 },
    retrospective_estimate: true,
  },
  {
    id: "hist_1990",
    year: 1990,
    title: "1990年 冷戰終結（柏林牆倒塌、大和解與新世界秩序）",
    total_index: 23.4,
    stage: 1,
    layers: { L1: 34.0, L2: 37.0, L3: 31.4, L4: 26.5, L5: 21.5 },
    retrospective_estimate: true,
  },
  {
    id: "hist_2025",
    year: 2025,
    title: "2025年 當代前夕（烏克蘭戰事延宕、多極重組與中東外溢）",
    total_index: 81.0,
    stage: 3,
    layers: { L1: 62.3, L2: 71.4, L3: 61.8, L4: 78.2, L5: 71.5 },
    retrospective_estimate: true,
  },
];

function getStageInfo(stageNumber) {
  switch (stageNumber) {
    case 1:
      return {
        number: 1,
        code: "STAGE_1_PRESSURE_BUILDING",
        title: "階段一：結構壓力形成",
        description: "資源、分配或經濟摩擦處於低位累積期，體系彈性充裕，國際制度能有效吸收爭端。",
      };
    case 2:
      return {
        number: 2,
        code: "STAGE_2_CONFLICT_OF_INTERESTS",
        title: "階段二：利益衝突顯性化",
        description: "關鍵產業、地緣勢力範圍或未來預期出現顯著分歧，陣營對立升溫，但常規外交與經貿制衡依然有效。",
      };
    case 3:
      return {
        number: 3,
        code: "STAGE_3_PEACE_MECHANISM_FAILURE",
        title: "階段三：和平解決機制失效",
        description: "外交互信受挫、貿易脫鉤武器化，多邊仲裁癱瘓，安全困境進入自我強化之高危狀態。",
      };
    case 4:
    default:
      return {
        number: 4,
        code: "STAGE_4_VIOLENCE_ACCEPTED",
        title: "階段四：暴力成為被接受選項",
        description: "和平緩衝全面失靈，生存危機、預防性打擊邏輯或體系絕望感壓倒避戰共識，爆發總體戰衝突機率極高。",
      };
  }
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...CORS_HEADERS,
    },
  });
}

function errorUnavailable(message = "No snapshot available in D1 database yet.") {
  return jsonResponse(
    {
      error: "Service Unavailable",
      status: 503,
      message,
    },
    503
  );
}

async function handleRiskLatest(db) {
  const row = await db
    .prepare("SELECT * FROM index_snapshots ORDER BY computed_at DESC LIMIT 1")
    .first();

  if (!row) {
    return errorUnavailable();
  }

  let layers = {};
  let drivers = [];
  let pulse = {};
  try {
    layers = JSON.parse(row.layers_json || "{}");
  } catch (e) {
    layers = {};
  }
  try {
    drivers = JSON.parse(row.drivers_json || "[]");
  } catch (e) {
    drivers = [];
  }
  try {
    pulse = JSON.parse(row.pulse_json || "{}");
  } catch (e) {
    pulse = {};
  }

  const structuralIndex =
    row.structural_index !== null && row.structural_index !== undefined
      ? Number(row.structural_index)
      : Number(row.total_index);
  const pulseAdjustment =
    row.pulse_adjustment !== null && row.pulse_adjustment !== undefined
      ? Number(row.pulse_adjustment)
      : 0.0;
  const compositeIndex =
    row.composite_index !== null && row.composite_index !== undefined
      ? Number(row.composite_index)
      : Number(row.total_index);

  return jsonResponse({
    model_version: row.model_version,
    scenario_id: row.scenario_id,
    computed_at: row.computed_at,
    composite_index: compositeIndex,
    structural_index: structuralIndex,
    pulse_adjustment: pulseAdjustment,
    pulse,
    total_index: compositeIndex, // backward compatibility
    stage: getStageInfo(row.stage),
    base_score: Number(row.base_score),
    interaction_bonus: Number(row.interaction_bonus),
    gate: {
      multiplier: Number(row.gate_multiplier),
      peace_capacity: Number(row.peace_capacity),
    },
    layers,
    drivers,
    probability_bands: {
      "1y": { central_pct: Number(row.band_1y) },
      "5y": { central_pct: Number(row.band_5y) },
      "10y": { central_pct: Number(row.band_10y) },
    },
  });
}

async function handlePulseLatest(db) {
  const row = await db
    .prepare("SELECT computed_at, pulse_adjustment, pulse_json FROM index_snapshots ORDER BY computed_at DESC LIMIT 1")
    .first();

  if (!row) {
    return errorUnavailable();
  }

  let pulseObj = {};
  try {
    pulseObj = JSON.parse(row.pulse_json || "{}");
  } catch (e) {
    pulseObj = {};
  }

  const pulseAdj =
    row.pulse_adjustment !== null && row.pulse_adjustment !== undefined
      ? Number(row.pulse_adjustment)
      : 0.0;

  return jsonResponse({
    computed_at: row.computed_at,
    pulse_adjustment: pulseAdj,
    range: [-10.0, 10.0],
    pulse: pulseObj,
  });
}

async function handleRiskHistory(db, granularity = null) {
  if (granularity === "daily") {
    const sql = `
      SELECT s.id,
             s.computed_at,
             substr(s.computed_at, 1, 10) AS date,
             COALESCE(s.composite_index, s.total_index) AS composite_index,
             COALESCE(s.structural_index, s.total_index) AS structural_index,
             COALESCE(s.pulse_adjustment, 0.0) AS pulse_adjustment,
             s.stage
      FROM index_snapshots s
      INNER JOIN (
          SELECT substr(computed_at, 1, 10) AS day, MAX(computed_at) AS max_computed_at
          FROM index_snapshots
          GROUP BY substr(computed_at, 1, 10)
      ) d ON s.computed_at = d.max_computed_at
      ORDER BY s.computed_at ASC
    `;
    const { results } = await db.prepare(sql).all();
    if (!results || results.length === 0) {
      return errorUnavailable();
    }
    const points = results.map((r) => ({
      date: r.date,
      computed_at: r.computed_at,
      composite_index: Number(r.composite_index),
      structural_index: Number(r.structural_index),
      pulse_adjustment: Number(r.pulse_adjustment),
      stage: Number(r.stage),
    }));
    return jsonResponse({
      granularity: "daily",
      timezone: "UTC",
      definition: "當日最後一份快照（UTC 計）之綜合指數與結構指數",
      total_points: points.length,
      points,
    });
  }

  if (granularity === "monthly") {
    const sql = `
      WITH daily_points AS (
          SELECT s.computed_at,
                 substr(s.computed_at, 1, 10) AS date,
                 substr(s.computed_at, 1, 7) AS month,
                 COALESCE(s.composite_index, s.total_index) AS composite_index,
                 COALESCE(s.structural_index, s.total_index) AS structural_index
          FROM index_snapshots s
          INNER JOIN (
              SELECT substr(computed_at, 1, 10) AS day, MAX(computed_at) AS max_computed_at
              FROM index_snapshots
              GROUP BY substr(computed_at, 1, 10)
          ) d ON s.computed_at = d.max_computed_at
      )
      SELECT month,
             COUNT(date) AS n_days,
             ROUND(AVG(composite_index), 2) AS composite_index,
             ROUND(AVG(structural_index), 2) AS structural_index
      FROM daily_points
      GROUP BY month
      ORDER BY month ASC
    `;
    const { results } = await db.prepare(sql).all();
    if (!results || results.length === 0) {
      return errorUnavailable();
    }
    const points = results.map((r) => ({
      month: r.month,
      n_days: Number(r.n_days),
      composite_index: Number(r.composite_index),
      structural_index: Number(r.structural_index),
    }));
    return jsonResponse({
      granularity: "monthly",
      timezone: "UTC",
      definition: "當月所有日點 composite 之算術平均，附帶當月記錄日數 n",
      total_points: points.length,
      points,
    });
  }

  const { results: snapshots } = await db
    .prepare(
      "SELECT id, computed_at, model_version, scenario_id, total_index, structural_index, pulse_adjustment, composite_index, stage, layers_json FROM index_snapshots ORDER BY computed_at ASC"
    )
    .all();

  if (!snapshots || snapshots.length === 0) {
    return errorUnavailable();
  }

  const formattedSnapshots = snapshots.map((s) => {
    let parsedLayers = {};
    try {
      parsedLayers = JSON.parse(s.layers_json || "{}");
    } catch (e) {
      parsedLayers = {};
    }
    const structuralIndex =
      s.structural_index !== null && s.structural_index !== undefined
        ? Number(s.structural_index)
        : Number(s.total_index);
    const pulseAdjustment =
      s.pulse_adjustment !== null && s.pulse_adjustment !== undefined
        ? Number(s.pulse_adjustment)
        : 0.0;
    const compositeIndex =
      s.composite_index !== null && s.composite_index !== undefined
        ? Number(s.composite_index)
        : Number(s.total_index);

    return {
      id: s.id,
      computed_at: s.computed_at,
      model_version: s.model_version,
      scenario_id: s.scenario_id,
      composite_index: compositeIndex,
      structural_index: structuralIndex,
      pulse_adjustment: pulseAdjustment,
      total_index: compositeIndex,
      stage: s.stage,
      layers: parsedLayers,
    };
  });

  return jsonResponse({
    snapshots: formattedSnapshots,
    historical_benchmarks: HISTORICAL_BENCHMARKS,
  });
}

async function handleRiskLayers(db) {
  const snap = await db
    .prepare("SELECT id, computed_at, model_version, total_index, layers_json FROM index_snapshots ORDER BY computed_at DESC LIMIT 1")
    .first();

  if (!snap) {
    return errorUnavailable();
  }

  let layerScores = {};
  try {
    layerScores = JSON.parse(snap.layers_json || "{}");
  } catch (e) {
    layerScores = {};
  }

  const { results: obs } = await db
    .prepare(
      "SELECT indicator_id, layer, raw_value, raw_unit, normalized_score, evidence_level, source_name, source_url, observation_date, publication_date, last_checked, stale_after_days, is_stale " +
      "FROM indicator_observations WHERE snapshot_id = ? ORDER BY layer, indicator_id"
    )
    .bind(snap.id)
    .all();

  const grouped = {};
  for (const item of obs || []) {
    const lid = item.layer;
    if (!grouped[lid]) {
      grouped[lid] = {
        layer: lid,
        score: layerScores[lid] !== undefined ? Number(layerScores[lid]) : null,
        indicators: [],
      };
    }
    grouped[lid].indicators.push({
      id: item.indicator_id,
      layer: item.layer,
      raw_value: item.raw_value,
      raw_unit: item.raw_unit || "",
      normalized_score: Number(item.normalized_score),
      evidence_level: item.evidence_level,
      source_name: item.source_name || "",
      source_url: item.source_url || "",
      observation_date: item.observation_date || "",
      publication_date: item.publication_date || "",
      last_checked: item.last_checked || "",
      stale_after_days: Number(item.stale_after_days),
      is_stale: Boolean(item.is_stale),
    });
  }

  return jsonResponse({
    snapshot_id: snap.id,
    computed_at: snap.computed_at,
    model_version: snap.model_version,
    total_index: Number(snap.total_index),
    layers: grouped,
  });
}

async function handleDataStatus(db) {
  const snap = await db
    .prepare("SELECT id, computed_at, model_version FROM index_snapshots ORDER BY computed_at DESC LIMIT 1")
    .first();

  if (!snap) {
    return errorUnavailable();
  }

  const { results: obs } = await db
    .prepare(
      "SELECT indicator_id, layer, raw_value, raw_unit, evidence_level, source_name, publication_date, last_checked, stale_after_days, is_stale " +
      "FROM indicator_observations WHERE snapshot_id = ? ORDER BY layer, indicator_id"
    )
    .bind(snap.id)
    .all();

  const observations = obs || [];
  const total = observations.length;
  const staleCount = observations.filter((o) => Number(o.is_stale) === 1).length;
  const freshCount = total - staleCount;
  const completeness = total > 0 ? 100.0 : 0.0;

  const indicatorSummary = observations.map((o) => ({
    id: o.indicator_id,
    layer: o.layer,
    status: Number(o.is_stale) === 1 ? "stale" : "fresh",
    evidence_level: o.evidence_level,
    source_name: o.source_name || "",
    publication_date: o.publication_date || "",
    last_checked: o.last_checked || "",
    stale_after_days: Number(o.stale_after_days),
  }));

  return jsonResponse({
    model_version: snap.model_version,
    last_computed: snap.computed_at,
    total_indicators: total,
    completeness_pct: completeness,
    fresh_count: freshCount,
    stale_count: staleCount,
    missing_count: 0,
    indicators: indicatorSummary,
  });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const method = request.method.toUpperCase();

    if (method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: CORS_HEADERS,
      });
    }

    if (method !== "GET") {
      return jsonResponse(
        {
          error: "Method Not Allowed",
          message: `Method ${method} is not supported. Only GET is allowed.`,
        },
        405
      );
    }

    const db = env.DB;
    if (!db) {
      return jsonResponse(
        {
          error: "Database Configuration Error",
          message: "D1 database binding 'DB' is missing from environment.",
        },
        500
      );
    }

    try {
      const pathname = url.pathname.replace(/\/+$/, "") || "/";
      const granularity = url.searchParams.get("granularity");

      switch (pathname) {
        case "/api/risk/latest":
          return await handleRiskLatest(db);
        case "/api/pulse/latest":
          return await handlePulseLatest(db);
        case "/api/risk/history":
          return await handleRiskHistory(db, granularity);
        case "/api/risk/layers":
          return await handleRiskLayers(db);
        case "/api/data-status":
          return await handleDataStatus(db);
        default:
          return jsonResponse(
            {
              error: "Not Found",
              status: 404,
              message: `Endpoint '${pathname}' not found. Available: /api/risk/latest, /api/pulse/latest, /api/risk/history, /api/risk/layers, /api/data-status`,
            },
            404
          );
      }
    } catch (err) {
      return jsonResponse(
        {
          error: "Internal Server Error",
          status: 500,
          message: err.message || String(err),
        },
        500
      );
    }
  },
};
