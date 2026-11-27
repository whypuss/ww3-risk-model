/**
 * WW3 Risk Model Cloudflare Worker API
 *
 * Endpoints:
 * - GET /api/risk/latest
 * - GET /api/risk/history
 * - GET /api/risk/layers
 * - GET /api/data-status
 * - GET /api/feeds/latest
 * - GET /api/feeds/polymarket
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
    total_index: compositeIndex,
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
             s.stage,
             s.pulse_json
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
    const points = results.map((r) => {
      let signals = [];
      try {
        const pulse = JSON.parse(r.pulse_json || "{}");
        if (pulse && pulse.signals && typeof pulse.signals === "object") {
          for (const [signalId, sig] of Object.entries(pulse.signals)) {
            if (sig && typeof sig === "object") {
              signals.push({
                signal_id: signalId,
                name: sig.name || signalId,
                contribution: Number(sig.contribution) || 0,
                status: sig.status || "unavailable",
                raw_value: sig.raw_value !== undefined && sig.raw_value !== null ? Number(sig.raw_value) : null,
                raw_unit: sig.raw_unit || "",
              });
            }
          }
        }
      } catch (e) {
        signals = [];
      }
      return {
        date: r.date,
        computed_at: r.computed_at,
        composite_index: Number(r.composite_index),
        structural_index: Number(r.structural_index),
        pulse_adjustment: Number(r.pulse_adjustment),
        stage: Number(r.stage),
        signals,
      };
    });
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

const FEED_IDS = ["gdelt", "opensky", "hormuz", "polymarket"];

async function upsertFeedSnapshot(db, feedId, status, payload, error = null) {
  const fetchedAt = new Date().toISOString();
  await db
    .prepare(
      "INSERT INTO live_feed_snapshots (feed_id, fetched_at, status, payload_json, error) VALUES (?, ?, ?, ?, ?) " +
      "ON CONFLICT(feed_id) DO UPDATE SET fetched_at = excluded.fetched_at, status = excluded.status, payload_json = excluded.payload_json, error = excluded.error"
    )
    .bind(feedId, fetchedAt, status, JSON.stringify(payload), error)
    .run();
}

const GDELT_DOC_URL =
  "https://api.gdeltproject.org/api/v2/doc/doc?query=(conflict%20OR%20war%20OR%20military%20OR%20protest)&mode=timelinevol&format=json";
const GDELT_V2_LASTUPDATE_URL = "https://storage.googleapis.com/data.gdeltproject.org/gdeltv2/lastupdate.txt";
const GDELT_V2_GCS_PREFIX = "https://storage.googleapis.com/data.gdeltproject.org/";
const GDELT_CONFLICT_ROOT_CODES = new Set(["14", "18", "19", "20"]);
const POLYMARKET_DEFAULT_MARKETS = [
  { id: "1124834", name: "US x Russia military clash by Dec 31, 2026", short: "US-RU Clash" },
  { id: "2749367", name: "Russia invades NATO country by Dec 31, 2026", short: "RU-NATO Invasion" },
  { id: "2749382", name: "NATO/EU troops fighting in Ukraine by Dec 31, 2026", short: "NATO Troops in UA" },
];
const YAHOO_BRENT_URL = "https://query1.finance.yahoo.com/v8/finance/chart/BZ=F?interval=1d&range=5d";

function clamp(val, minVal, maxVal) {
  return Math.max(minVal, Math.min(maxVal, val));
}

async function extractFirstFileFromZip(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);

  // Locate End of Central Directory (PK\x05\x06) to handle both normal and data-descriptor ZIPs
  let eocdOffset = -1;
  const minSearch = Math.max(0, bytes.length - 65557);
  for (let i = bytes.length - 22; i >= minSearch; i--) {
    if (
      bytes[i] === 0x50 &&
      bytes[i + 1] === 0x4b &&
      bytes[i + 2] === 0x05 &&
      bytes[i + 3] === 0x06
    ) {
      eocdOffset = i;
      break;
    }
  }

  let compressionMethod = 0;
  let compressedSize = 0;
  let localHeaderOffset = 0;
  let fileName = "";

  if (eocdOffset >= 0) {
    const cdOffset = view.getUint32(eocdOffset + 16, true);
    if (cdOffset + 46 <= bytes.length && view.getUint32(cdOffset, true) === 0x02014b50) {
      compressionMethod = view.getUint16(cdOffset + 10, true);
      compressedSize = view.getUint32(cdOffset + 20, true);
      const nameLen = view.getUint16(cdOffset + 28, true);
      localHeaderOffset = view.getUint32(cdOffset + 42, true);
      fileName = new TextDecoder().decode(bytes.subarray(cdOffset + 46, cdOffset + 46 + nameLen));
    }
  }

  if (localHeaderOffset + 30 > bytes.length || view.getUint32(localHeaderOffset, true) !== 0x04034b50) {
    throw new Error("Invalid ZIP local file header");
  }

  if (!compressedSize) {
    compressionMethod = view.getUint16(localHeaderOffset + 8, true);
    compressedSize = view.getUint32(localHeaderOffset + 18, true);
  }
  const localNameLen = view.getUint16(localHeaderOffset + 26, true);
  const localExtraLen = view.getUint16(localHeaderOffset + 28, true);
  if (!fileName) {
    fileName = new TextDecoder().decode(
      bytes.subarray(localHeaderOffset + 30, localHeaderOffset + 30 + localNameLen)
    );
  }
  const dataStart = localHeaderOffset + 30 + localNameLen + localExtraLen;
  const compressedSlice = bytes.subarray(dataStart, dataStart + compressedSize);

  let text = "";
  if (compressionMethod === 0) {
    text = new TextDecoder().decode(compressedSlice);
  } else if (compressionMethod === 8) {
    const ds = new DecompressionStream("deflate-raw");
    const writer = ds.writable.getWriter();
    const writePromise = writer.write(compressedSlice).then(() => writer.close());
    const resp = new Response(ds.readable);
    const [decodedText] = await Promise.all([resp.text(), writePromise]);
    text = decodedText;
  } else {
    throw new Error(`Unsupported ZIP compression method: ${compressionMethod}`);
  }

  return { fileName, text };
}

function parseGdeltEventsCsvText(csvText) {
  const lines = csvText.split(/\r?\n/);
  let totalEvents = 0;
  let conflictEvents = 0;
  let latestSqldate = "";

  for (const line of lines) {
    if (!line) continue;
    const cols = line.split("\t");
    if (cols.length <= 30) continue;
    totalEvents += 1;
    if (!latestSqldate && cols[1]) {
      latestSqldate = cols[1].trim();
    }
    const rootCode = cols[28].trim();
    const quadClass = cols[29].trim();
    if (quadClass === "4" || GDELT_CONFLICT_ROOT_CODES.has(rootCode)) {
      conflictEvents += 1;
    }
  }
  return { totalEvents, conflictEvents, latestSqldate };
}

async function fetchGdeltV2EventsFallback(docError = null) {
  const luController = new AbortController();
  const luTimer = setTimeout(() => luController.abort(), 8000);
  let lastUpdateText = "";
  try {
    const luResp = await fetch(GDELT_V2_LASTUPDATE_URL, {
      headers: { "User-Agent": "WW3-Risk-Worker/1.0" },
      signal: luController.signal,
    });
    if (luResp.status !== 200) {
      throw new Error(`GDELT lastupdate HTTP ${luResp.status}`);
    }
    lastUpdateText = await luResp.text();
  } finally {
    clearTimeout(luTimer);
  }

  let exportUrl = "";
  for (const line of lastUpdateText.split(/\r?\n/)) {
    const parts = line.trim().split(/\s+/);
    if (parts.length >= 3 && parts[2].endsWith(".export.CSV.zip")) {
      exportUrl = parts[2];
      break;
    }
  }
  if (!exportUrl) {
    throw new Error("GDELT lastupdate missing export.CSV.zip URL");
  }
  exportUrl = exportUrl
    .replace("http://data.gdeltproject.org/", GDELT_V2_GCS_PREFIX)
    .replace("https://data.gdeltproject.org/", GDELT_V2_GCS_PREFIX);

  const zipController = new AbortController();
  const zipTimer = setTimeout(() => zipController.abort(), 12000);
  let zipBuf;
  try {
    const zipResp = await fetch(exportUrl, {
      headers: { "User-Agent": "WW3-Risk-Worker/1.0" },
      signal: zipController.signal,
    });
    if (zipResp.status !== 200) {
      throw new Error(`GDELT export ZIP HTTP ${zipResp.status}`);
    }
    zipBuf = await zipResp.arrayBuffer();
  } finally {
    clearTimeout(zipTimer);
  }

  const { fileName, text } = await extractFirstFileFromZip(zipBuf);
  const { totalEvents, conflictEvents, latestSqldate } = parseGdeltEventsCsvText(text);
  if (totalEvents === 0) {
    throw new Error("GDELT export CSV contained zero events");
  }

  const conflictPct = Number(((conflictEvents / totalEvents) * 100).toFixed(4));
  const tsMatch = /^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})/.exec(fileName);
  const dateLabel = tsMatch
    ? `${tsMatch[1]}-${tsMatch[2]}-${tsMatch[3]}T${tsMatch[4]}:${tsMatch[5]}:${tsMatch[6]}Z`
    : (latestSqldate || fileName.slice(0, 14));
  return {
    value: conflictPct,
    date: dateLabel,
    history_points: totalEvents,
    conflict_events: conflictEvents,
    source: "gdelt_v2_events_15m",
    source_url: exportUrl,
    export_file: fileName,
    fallback_reason: docError,
  };
}

async function fetchGdelt() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 6000);
  let docErr = null;
  try {
    const response = await fetch(GDELT_DOC_URL, {
      headers: { "User-Agent": "WW3-Risk-Worker/1.0" },
      signal: controller.signal,
    });
    if (response.status !== 200) {
      throw new Error(`GDELT HTTP ${response.status}`);
    }
    const data = await response.json();
    const timeline = data?.timeline?.[0]?.data || [];
    if (!timeline.length) {
      throw new Error("GDELT response missing timeline data");
    }
    const latest = timeline[timeline.length - 1];
    const prior = timeline.slice(0, -1).slice(-30);
    const baseline30d = prior.length
      ? Number((prior.reduce((acc, item) => acc + Number(item.value || 0), 0) / prior.length).toFixed(4))
      : 3.5;
    return {
      value: Number(latest.value),
      date: latest.date,
      history_points: timeline.length,
      baseline_30d: baseline30d,
      source: "gdelt_doc_timelinevol",
      source_url: GDELT_DOC_URL,
    };
  } catch (e) {
    docErr = e.name === "AbortError" ? "GDELT Doc API timeout" : (e.message || String(e));
  } finally {
    clearTimeout(timer);
  }

  try {
    return await fetchGdeltV2EventsFallback(docErr);
  } catch (fbErr) {
    throw new Error(`${docErr}; fallback failed: ${fbErr.message || String(fbErr)}`);
  }
}

async function fetchOpenSky() {
  const boxes = [
    { name: "baltic", lamin: 53, lamax: 60, lomin: 10, lomax: 30 },
    { name: "black_sea", lamin: 41, lamax: 47, lomin: 28, lomax: 42 },
    { name: "persian_gulf", lamin: 24, lamax: 30, lomin: 48, lomax: 57 },
    { name: "taiwan_strait", lamin: 22, lamax: 27, lomin: 117, lomax: 121 },
  ];

  const boxPromises = boxes.map(async (box) => {
    const url = `https://opensky-network.org/api/states/all?lamin=${box.lamin}&lamax=${box.lamax}&lomin=${box.lomin}&lomax=${box.lomax}`;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(url, {
        headers: { "User-Agent": "WW3-Risk-Worker/1.0" },
        signal: controller.signal,
      });
      if (response.status === 429) {
        return { name: box.name, rateLimited: true };
      }
      if (response.status !== 200) {
        return { name: box.name, ok: false, result: { error: `HTTP ${response.status}`, visible: 0 } };
      }
      const data = await response.json();
      const states = data?.states || [];
      const visible = states.filter((s) => s[5] !== null && s[6] !== null).length;
      return { name: box.name, ok: true, result: { visible } };
    } catch (e) {
      if (e.name === "AbortError" || e.message?.includes("timeout")) {
        return { name: box.name, ok: false, result: { error: "timeout", visible: 0 } };
      }
      return { name: box.name, ok: false, result: { error: e.message || String(e), visible: 0 } };
    } finally {
      clearTimeout(timeoutId);
    }
  });

  const settled = await Promise.all(boxPromises);
  if (settled.some((item) => item.rateLimited)) {
    throw new Error("OPENSKY_429");
  }

  const results = {};
  let totalVisible = 0;
  let hasSuccess = false;
  for (const item of settled) {
    results[item.name] = item.result;
    if (item.ok) {
      totalVisible += item.result.visible;
      hasSuccess = true;
    }
  }

  if (!hasSuccess) {
    const errorParts = Object.entries(results).map(([name, r]) => `${name} ${r.error}`);
    throw new Error(`OpenSky all boxes failed: ${errorParts.join(", ")}`);
  }

  return { boxes: results, total_visible: totalVisible };
}

async function fetchHormuz() {
  const url = "https://hormuz.now/status.json";
  const response = await fetch(url, { headers: { "User-Agent": "WW3-Risk-Worker/1.0" } });
  if (response.status !== 200) {
    throw new Error(`Hormuz HTTP ${response.status}`);
  }
  const data = await response.json();
  return {
    last24h: data.last24h,
    fleet: data.fleet,
    feed: data.feed,
    generatedAt: data.generatedAt,
  };
}

function parseJsonField(field) {
  if (Array.isArray(field)) return field;
  if (typeof field === "string" && field.trim()) {
    try {
      return JSON.parse(field);
    } catch (e) {
      return [];
    }
  }
  return [];
}

async function fetchPolymarketMarkets(db, marketIds) {
  const results = [];
  for (const mid of marketIds) {
    const url = `https://gamma-api.polymarket.com/markets/${mid}`;
    const response = await fetch(url, { headers: { "User-Agent": "WW3-Risk-Worker/1.0" } });
    if (response.status !== 200) {
      continue;
    }
    const data = await response.json();
    const outcomes = parseJsonField(data?.outcomes);
    const clobTokenIds = parseJsonField(data?.clobTokenIds);
    let yesTokenId = null;
    let yesIndex = -1;
    for (let i = 0; i < outcomes.length; i++) {
      if (outcomes[i] === "Yes" && clobTokenIds[i]) {
        yesTokenId = clobTokenIds[i];
        yesIndex = i;
        break;
      }
    }
    const prices = data?.outcomePrices ? JSON.parse(data.outcomePrices) : [];
    const yesPrice = yesIndex >= 0 && prices[yesIndex] !== undefined ? parseFloat(prices[yesIndex]) : null;
    const rawShort = data?.question?.split("?")[0]?.substring(0, 50) || "";
    const short = rawShort.replace(/,\s*$/, "").trim();
    results.push({
      id: mid,
      question: data?.question || "",
      short,
      yes_token_id: yesTokenId,
      midpoint: yesPrice !== null ? (yesPrice * 100).toFixed(2) : null,
      fetched_at: new Date().toISOString(),
    });
  }
  return results;
}

async function handleFeedsLatest(db) {
  try {
    await db
      .prepare(
        "CREATE TABLE IF NOT EXISTS live_feed_snapshots (feed_id TEXT PRIMARY KEY, fetched_at TEXT, status TEXT, payload_json TEXT, error TEXT)"
      )
      .run();
  } catch (e) {
    // Ignore CREATE TABLE errors, continue to read feeds
  }

  const feedIds = ["gdelt", "opensky", "hormuz", "polymarket"];
  const feeds = [];
  for (const fid of feedIds) {
    try {
      const row = await db.prepare("SELECT * FROM live_feed_snapshots WHERE feed_id = ?").bind(fid).first();
      if (!row) {
        feeds.push({ feed_id: fid, fetched_at: null, status: "never_fetched", payload: null, error: null });
      } else {
        let payload = null;
        try {
          payload = JSON.parse(row.payload_json || "null");
        } catch (e) {
          payload = null;
        }
        feeds.push({
          feed_id: row.feed_id,
          fetched_at: row.fetched_at,
          status: row.status,
          payload,
          error: row.error,
        });
      }
    } catch (e) {
      feeds.push({ feed_id: fid, fetched_at: null, status: "never_fetched", payload: null, error: null });
    }
  }
  return jsonResponse({ feeds });
}

async function handleFeedsPolymarket(db) {
  const snap = await db
    .prepare("SELECT pulse_json FROM index_snapshots ORDER BY computed_at DESC LIMIT 1")
    .first();
  let marketIds = ["1124834", "2749367", "2749382"];
  if (snap?.pulse_json) {
    try {
      const pulse = JSON.parse(snap.pulse_json);
      const details = pulse.signals?.polymarket_war_risk?.details;
      if (details?.monitored_markets) {
        marketIds = details.monitored_markets.map((m) => m.id).filter(Boolean);
      }
    } catch (e) {
    }
  }
  const markets = await fetchPolymarketMarkets(db, marketIds);
  if (markets.length === 0) {
    return jsonResponse({ markets: [], error: "Gamma API unavailable; showing hourly pulse snapshot fallback", fallback: true });
  }
  return jsonResponse({ markets, error: null, fallback: false });
}

function shouldFetchOpenSky(row, now) {
  if (!row) return true;
  if (row.status !== "ok") return true;
  if (!row.fetched_at) return true;
  const fetchedAt = new Date(row.fetched_at);
  const ageMinutes = (now - fetchedAt) / 60000;
  return ageMinutes > 50;
}

async function fetchBrentOilForPulse() {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const resp = await fetch(YAHOO_BRENT_URL, {
      headers: {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
      },
      signal: controller.signal,
    });
    if (resp.status !== 200) {
      throw new Error(`Yahoo Finance HTTP ${resp.status}`);
    }
    const yfData = await resp.json();
    const result = yfData?.chart?.result || [];
    if (!result.length) {
      throw new Error("Yahoo Finance chart response has no result");
    }
    const meta = result[0]?.meta || {};
    let chgPct = meta.regularMarketChangePercent ?? meta.fulldayChangePercent;
    if (chgPct === undefined || chgPct === null) {
      const prev = meta.chartPreviousClose ?? meta.previousClose;
      const cur = meta.regularMarketPrice;
      if (prev && cur) {
        chgPct = ((cur - prev) / prev) * 100.0;
      }
    }
    if (chgPct === undefined || chgPct === null) {
      throw new Error("Missing Brent change percentage");
    }
    return {
      change_pct: Number(chgPct),
      price_usd: Number(meta.regularMarketPrice || 0),
    };
  } finally {
    clearTimeout(timer);
  }
}

async function fetchPolymarketForPulse() {
  const results = [];
  await Promise.all(
    POLYMARKET_DEFAULT_MARKETS.map(async (item) => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 8000);
      try {
        const resp = await fetch(`https://gamma-api.polymarket.com/markets/${item.id}`, {
          headers: { "User-Agent": "WW3-Risk-Worker/1.0" },
          signal: controller.signal,
        });
        if (resp.status !== 200) return;
        const mData = await resp.json();
        const prices = parseJsonField(mData?.outcomePrices);
        const yesPrice = prices.length > 0 ? Number(prices[0]) : null;
        if (yesPrice !== null && !Number.isNaN(yesPrice)) {
          results.push({
            id: item.id,
            question: mData?.question || item.name,
            short: item.short,
            yes_price: yesPrice,
            volume: Number(mData?.volume || 0),
          });
        }
      } catch (e) {
        // Individual market failure does not stop basket
      } finally {
        clearTimeout(timer);
      }
    })
  );
  return results;
}

async function buildWorkerPulse(nowIso, gdeltData = null) {
  const signals = {};

  // 1. GDELT (weight 0.40)
  if (gdeltData && typeof gdeltData.value === "number") {
    const isEventsFeed = gdeltData.source === "gdelt_v2_events_15m";
    const baseline = isEventsFeed ? 13.5 : (Number(gdeltData.baseline_30d) || 3.5);
    const scale = isEventsFeed ? 6.0 : 1.75;
    const normScore = clamp((gdeltData.value - baseline) / scale, -1.0, 1.0);
    const contrib = Number((normScore * 0.4 * 10.0).toFixed(2));
    signals.gdelt_conflict = {
      signal_id: "gdelt_conflict",
      name: "GDELT 全球衝突與動盪新聞聲量強度",
      source: isEventsFeed ? "GDELT 2.0 Events 15-min Feed" : "GDELT 2.0 Doc TimelineVol API",
      source_url: gdeltData.source_url || GDELT_DOC_URL,
      weight: 0.4,
      status: "live",
      fetched_at: nowIso,
      raw_value: Number(gdeltData.value.toFixed(4)),
      raw_unit: isEventsFeed ? "% (15分鐘衝突/抗議事件佔比)" : "% (全球新聞總量佔比)",
      normalized_score: Number(normScore.toFixed(4)),
      contribution: contrib,
      details: {
        latest_date: gdeltData.date || "",
        history_points: gdeltData.history_points || 0,
        baseline_anchor: baseline,
        formula: `clamp((raw - ${baseline.toFixed(2)}) / ${scale.toFixed(2)}, -1.0, 1.0)`,
      },
      error: null,
    };
  } else {
    signals.gdelt_conflict = {
      signal_id: "gdelt_conflict",
      name: "GDELT 全球衝突與動盪新聞聲量強度",
      source: "GDELT 2.0 Doc TimelineVol API",
      source_url: GDELT_DOC_URL,
      weight: 0.4,
      status: "unavailable",
      fetched_at: null,
      raw_value: null,
      raw_unit: "% (全球新聞總量佔比)",
      normalized_score: 0.0,
      contribution: 0.0,
      details: {},
      error: "GDELT unavailable in worker scheduled tick",
    };
  }

  // 2. Polymarket (weight 0.35)
  try {
    const markets = await fetchPolymarketForPulse();
    if (!markets.length) {
      throw new Error("No Polymarket war risk markets returned");
    }
    const avgYes = markets.reduce((sum, m) => sum + m.yes_price, 0) / markets.length;
    const rawPct = avgYes * 100.0;
    const normScore = clamp((avgYes - 0.05) / 0.1, -1.0, 1.0);
    const contrib = Number((normScore * 0.35 * 10.0).toFixed(2));
    signals.polymarket_war_risk = {
      signal_id: "polymarket_war_risk",
      name: "Polymarket 戰爭地緣預測市場綜合機率",
      source: "Polymarket Gamma API",
      source_url: "https://gamma-api.polymarket.com/markets",
      weight: 0.35,
      status: "live",
      fetched_at: nowIso,
      raw_value: Number(rawPct.toFixed(2)),
      raw_unit: "% (Yes 隱含機率)",
      normalized_score: Number(normScore.toFixed(4)),
      contribution: contrib,
      details: {
        monitored_markets: markets,
        baseline_anchor: 0.05,
        formula: "clamp((P_yes - 0.05) / 0.10, -1.0, 1.0)",
      },
      error: null,
    };
  } catch (e) {
    signals.polymarket_war_risk = {
      signal_id: "polymarket_war_risk",
      name: "Polymarket 戰爭地緣預測市場綜合機率",
      source: "Polymarket Gamma API",
      source_url: "https://gamma-api.polymarket.com/markets",
      weight: 0.35,
      status: "unavailable",
      fetched_at: null,
      raw_value: null,
      raw_unit: "% (Yes 隱含機率)",
      normalized_score: 0.0,
      contribution: 0.0,
      details: {},
      error: e.message || String(e),
    };
  }

  // 3. Brent Crude 24h Change (weight 0.25)
  try {
    const oil = await fetchBrentOilForPulse();
    const normScore = clamp(oil.change_pct / 10.0, -1.0, 1.0);
    const contrib = Number((normScore * 0.25 * 10.0).toFixed(2));
    signals.brent_oil_24h = {
      signal_id: "brent_oil_24h",
      name: "Brent 原油近月 24 小時價格變動",
      source: "Yahoo Finance (BZ=F)",
      source_url: YAHOO_BRENT_URL,
      weight: 0.25,
      status: "live",
      fetched_at: nowIso,
      raw_value: Number(oil.change_pct.toFixed(2)),
      raw_unit: "% (24h 漲跌幅)",
      normalized_score: Number(normScore.toFixed(4)),
      contribution: contrib,
      details: {
        price_usd: oil.price_usd,
        scale_anchor_pct: 10.0,
        formula: "clamp(change_pct / 10.0, -1.0, 1.0)",
      },
      error: null,
    };
  } catch (e) {
    signals.brent_oil_24h = {
      signal_id: "brent_oil_24h",
      name: "Brent 原油近月 24 小時價格變動",
      source: "Yahoo Finance (BZ=F)",
      source_url: YAHOO_BRENT_URL,
      weight: 0.25,
      status: "unavailable",
      fetched_at: null,
      raw_value: null,
      raw_unit: "% (24h 漲跌幅)",
      normalized_score: 0.0,
      contribution: 0.0,
      details: {},
      error: e.message || String(e),
    };
  }

  const totalContrib = Object.values(signals).reduce((sum, s) => sum + Number(s.contribution || 0), 0);
  const pulseAdjustment = Number(clamp(totalContrib, -10.0, 10.0).toFixed(2));
  const activeCount = Object.values(signals).filter((s) => s.status === "live").length;

  return {
    version: "0.6.0",
    computed_at: nowIso,
    pulse_adjustment: pulseAdjustment,
    range: [-10.0, 10.0],
    status: activeCount > 0 ? "operational" : "degraded",
    active_signals_count: activeCount,
    total_signals_count: 3,
    source_engine: "cloudflare-worker-fallback",
    weights: {
      gdelt_conflict: 0.4,
      polymarket_war_risk: 0.35,
      brent_oil_24h: 0.25,
    },
    signals,
  };
}

async function maybeDispatchGitHubUpdate(db, env, now) {
  const token = env?.GITHUB_DISPATCH_TOKEN;
  if (!token) {
    return { dispatched: false, reason: "no_token" };
  }

  const latest = await db
    .prepare("SELECT computed_at FROM index_snapshots ORDER BY computed_at DESC LIMIT 1")
    .first();
  if (latest?.computed_at) {
    const ageMinutes = (now - new Date(latest.computed_at)) / 60000;
    if (ageMinutes < 55) {
      return { dispatched: false, reason: "fresh", age_minutes: Math.round(ageMinutes) };
    }
  }

  const prevDispatch = await db
    .prepare("SELECT fetched_at, status FROM live_feed_snapshots WHERE feed_id = ?")
    .bind("github_dispatch")
    .first();
  if (prevDispatch?.fetched_at && prevDispatch.status === "ok") {
    const sinceDispatchMin = (now - new Date(prevDispatch.fetched_at)) / 60000;
    if (sinceDispatchMin < 25) {
      return { dispatched: false, reason: "cooldown", since_dispatch_minutes: Math.round(sinceDispatchMin) };
    }
  }

  const repo = env.GITHUB_REPO || "whypuss/ww3-risk-model";
  const workflow = env.GITHUB_WORKFLOW || "update.yml";
  const url = `https://api.github.com/repos/${repo}/actions/workflows/${workflow}/dispatches`;

  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "WW3-Risk-Worker/1.0",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ref: "main",
        inputs: { deploy_pages: "auto", deploy_worker: "never", run_slow_fetchers: "auto" },
      }),
    });
    if (resp.status === 204 || resp.status === 200) {
      await upsertFeedSnapshot(db, "github_dispatch", "ok", { repo, workflow, http_status: resp.status });
      return { dispatched: true, http_status: resp.status };
    }
    const errText = await resp.text().catch(() => "");
    const errMsg = `GitHub dispatch HTTP ${resp.status}: ${errText.slice(0, 160)}`;
    await upsertFeedSnapshot(db, "github_dispatch", "error", { repo, workflow, http_status: resp.status }, errMsg);
    return { dispatched: false, reason: "http_error", error: errMsg };
  } catch (e) {
    const errMsg = e.message || String(e);
    await upsertFeedSnapshot(db, "github_dispatch", "error", { repo, workflow }, errMsg);
    return { dispatched: false, reason: "network_error", error: errMsg };
  }
}

async function maybeBackfillHourlySnapshot(db, now, gdeltData = null) {
  const latest = await db
    .prepare("SELECT * FROM index_snapshots ORDER BY computed_at DESC LIMIT 1")
    .first();
  if (!latest || !latest.computed_at) {
    return { backfilled: false, reason: "no_base_snapshot" };
  }

  const ageMinutes = (now - new Date(latest.computed_at)) / 60000;
  if (ageMinutes < 70) {
    return { backfilled: false, reason: "fresh", age_minutes: Math.round(ageMinutes) };
  }

  const nowIso = now.toISOString().replace(/\.\d{3}Z$/, "Z");
  const pulse = await buildWorkerPulse(nowIso, gdeltData);
  if (pulse.active_signals_count === 0) {
    return { backfilled: false, reason: "all_pulse_sources_unavailable" };
  }

  const structuralIdx =
    latest.structural_index !== null && latest.structural_index !== undefined
      ? Number(latest.structural_index)
      : Number(latest.total_index);
  const compositeIdx = Number(clamp(structuralIdx + pulse.pulse_adjustment, 0.0, 100.0).toFixed(2));
  const cleanTs = nowIso.replace(/[^0-9a-zA-Z]/g, "");
  const scenarioId = latest.scenario_id || "baseline_2026";
  const newSnapshotId = `snapshot_${scenarioId}_${cleanTs}_worker`;

  await db
    .prepare(
      "INSERT OR REPLACE INTO index_snapshots (" +
        "id, computed_at, model_version, scenario_id, total_index, stage, " +
        "base_score, interaction_bonus, gate_multiplier, peace_capacity, " +
        "band_1y, band_5y, band_10y, layers_json, drivers_json, " +
        "structural_index, pulse_adjustment, composite_index, pulse_json" +
      ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    .bind(
      newSnapshotId,
      nowIso,
      latest.model_version,
      scenarioId,
      compositeIdx,
      Number(latest.stage),
      Number(latest.base_score),
      Number(latest.interaction_bonus),
      Number(latest.gate_multiplier),
      Number(latest.peace_capacity),
      Number(latest.band_1y),
      Number(latest.band_5y),
      Number(latest.band_10y),
      latest.layers_json,
      latest.drivers_json,
      structuralIdx,
      pulse.pulse_adjustment,
      compositeIdx,
      JSON.stringify(pulse)
    )
    .run();

  await db
    .prepare(
      "INSERT INTO indicator_observations (" +
        "snapshot_id, indicator_id, layer, raw_value, raw_unit, " +
        "normalized_score, evidence_level, source_name, source_url, " +
        "observation_date, publication_date, last_checked, stale_after_days, is_stale" +
      ") SELECT ?, indicator_id, layer, raw_value, raw_unit, " +
        "normalized_score, evidence_level, source_name, source_url, " +
        "observation_date, publication_date, last_checked, stale_after_days, is_stale " +
      "FROM indicator_observations WHERE snapshot_id = ?"
    )
    .bind(newSnapshotId, latest.id)
    .run();

  return {
    backfilled: true,
    snapshot_id: newSnapshotId,
    computed_at: nowIso,
    composite_index: compositeIdx,
    pulse_adjustment: pulse.pulse_adjustment,
    active_signals_count: pulse.active_signals_count,
  };
}

async function handleAutomationStatus(db) {
  const latest = await db
    .prepare("SELECT id, computed_at, model_version, composite_index, pulse_adjustment FROM index_snapshots ORDER BY computed_at DESC LIMIT 1")
    .first();

  if (!latest) {
    return errorUnavailable();
  }

  const now = new Date();
  const ageMinutes = Number(((now - new Date(latest.computed_at)) / 60000).toFixed(1));
  const cutoffIso = new Date(now.getTime() - 24 * 3600 * 1000).toISOString();
  const countRow = await db
    .prepare("SELECT COUNT(*) AS cnt FROM index_snapshots WHERE computed_at >= ?")
    .bind(cutoffIso)
    .first();

  let dispatchRow = null;
  try {
    dispatchRow = await db
      .prepare("SELECT fetched_at, status, payload_json, error FROM live_feed_snapshots WHERE feed_id = ?")
      .bind("github_dispatch")
      .first();
  } catch (e) {
    dispatchRow = null;
  }

  return jsonResponse({
    now_utc: now.toISOString(),
    latest_snapshot: {
      id: latest.id,
      computed_at: latest.computed_at,
      age_minutes: ageMinutes,
      source: String(latest.id || "").endsWith("_worker") ? "cloudflare-worker-fallback" : "github-actions",
      composite_index: Number(latest.composite_index),
      pulse_adjustment: Number(latest.pulse_adjustment),
    },
    snapshots_last_24h: Number(countRow?.cnt || 0),
    is_fresh_90m: ageMinutes <= 90,
    github_dispatch: dispatchRow
      ? {
          fetched_at: dispatchRow.fetched_at,
          status: dispatchRow.status,
          error: dispatchRow.error,
        }
      : { fetched_at: null, status: "not_configured", error: null },
  });
}

async function scheduledHandler(event, env, ctx) {
  const db = env.DB;
  if (!db) return;

  await db
    .prepare(
      "CREATE TABLE IF NOT EXISTS live_feed_snapshots (feed_id TEXT PRIMARY KEY, fetched_at TEXT, status TEXT, payload_json TEXT, error TEXT)"
    )
    .run();

  const now = new Date();

  // Every tick: GDELT + Hormuz
  let gdeltData = null;
  try {
    gdeltData = await fetchGdelt();
    await upsertFeedSnapshot(db, "gdelt", "ok", gdeltData);
  } catch (e) {
    await upsertFeedSnapshot(db, "gdelt", "error", null, e.message);
  }

  try {
    const hormuzData = await fetchHormuz();
    await upsertFeedSnapshot(db, "hormuz", "ok", hormuzData);
  } catch (e) {
    await upsertFeedSnapshot(db, "hormuz", "error", null, e.message);
  }

  // OpenSky: freshness gate instead of minute === 0
  const openskyRow = await db
    .prepare("SELECT feed_id, fetched_at, status FROM live_feed_snapshots WHERE feed_id = ?")
    .bind("opensky")
    .first();

  if (shouldFetchOpenSky(openskyRow, now)) {
    try {
      const openskyData = await fetchOpenSky();
      await upsertFeedSnapshot(db, "opensky", "ok", openskyData);
    } catch (e) {
      if (e.message === "OPENSKY_429") {
        await upsertFeedSnapshot(db, "opensky", "stale", null, "rate limited (429)");
      } else {
        await upsertFeedSnapshot(db, "opensky", "error", null, e.message);
      }
    }
  }

  // Optional Cloudflare-driven GitHub workflow_dispatch trigger (when GITHUB_DISPATCH_TOKEN secret is set)
  try {
    await maybeDispatchGitHubUpdate(db, env, now);
  } catch (e) {
    // Never abort cron on dispatch errors
  }

  // Serverless D1 hourly backfill safety net: if GitHub Actions schedule missed > 70 min, keep D1 fresh
  try {
    await maybeBackfillHourlySnapshot(db, now, gdeltData);
  } catch (e) {
    // Never abort cron on backfill errors
  }
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
        case "/api/feeds/latest":
          return await handleFeedsLatest(db);
        case "/api/feeds/polymarket":
          return await handleFeedsPolymarket(db);
        case "/api/automation/status":
          return await handleAutomationStatus(db);
        default:
          return jsonResponse(
            {
              error: "Not Found",
              status: 404,
              message: `Endpoint '${pathname}' not found. Available: /api/risk/latest, /api/pulse/latest, /api/risk/history, /api/risk/layers, /api/data-status, /api/feeds/latest, /api/feeds/polymarket, /api/automation/status`,
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

  async scheduled(event, env, ctx) {
    await scheduledHandler(event, env, ctx);
  },

  // Exported for unit testing
  shouldFetchOpenSky,
  fetchOpenSky,
  fetchGdelt,
  extractFirstFileFromZip,
  parseGdeltEventsCsvText,
  maybeDispatchGitHubUpdate,
  maybeBackfillHourlySnapshot,
};