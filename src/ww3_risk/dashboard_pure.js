/**
 * Pure JavaScript functions extracted from dashboard for unit testing.
 * These functions have no DOM dependencies and can be tested with Node.js.
 */

function parsePolymarketWsMessage(msg) {
  try {
    const data = JSON.parse(msg);
    if (data.type !== "price" || !data.asset_id || data.midpoint === undefined) {
      return null;
    }
    return {
      asset_id: data.asset_id,
      midpoint: Number(data.midpoint),
      timestamp: data.timestamp || Date.now(),
    };
  } catch (e) {
    return null;
  }
}

function isFeedStale(feedId, fetchedAt) {
  if (!fetchedAt) return true;
  const fetched = new Date(fetchedAt).getTime();
  const now = Date.now();
  const diffMinutes = (now - fetched) / 60000;
  if (feedId === "gdelt" || feedId === "hormuz") {
    return diffMinutes > 45;
  }
  if (feedId === "opensky") {
    return diffMinutes > 180;
  }
  return false;
}

function computeTrendDrivers(points) {
  if (!points || points.length === 0) return [];

  const steps = [];
  for (let i = 0; i < points.length; i++) {
    const curr = points[i];
    if (i === 0) {
      steps.push({
        from_date: curr.date,
        to_date: curr.date,
        prev_composite: Number(curr.composite_index),
        composite: Number(curr.composite_index),
        delta: 0.0,
        drivers: [],
        baseline: true,
      });
      continue;
    }

    const prev = points[i - 1];
    const prevComposite = Number(prev.composite_index);
    const currComposite = Number(curr.composite_index);
    const delta = currComposite - prevComposite;

    const prevStructural = Number(prev.structural_index);
    const currStructural = Number(curr.structural_index);
    const structuralDelta = currStructural - prevStructural;

    const candidates = [];

    if (Math.abs(structuralDelta) > 0.001) {
      candidates.push({
        label: "結構指數（36 項年度指標）",
        delta: structuralDelta,
        prev_contribution: prevStructural,
        contribution: currStructural,
        prev_raw: prevStructural,
        raw: currStructural,
        raw_unit: "分",
        data_gap: false,
      });
    }

    const prevSignals = (prev.signals && Array.isArray(prev.signals)) ? prev.signals : [];
    const currSignals = (curr.signals && Array.isArray(curr.signals)) ? curr.signals : [];

    const prevSigMap = {};
    for (const s of prevSignals) {
      prevSigMap[s.signal_id] = s;
    }
    const currSigMap = {};
    for (const s of currSignals) {
      currSigMap[s.signal_id] = s;
    }

    const allSignalIds = new Set([...Object.keys(prevSigMap), ...Object.keys(currSigMap)]);

    for (const sid of allSignalIds) {
      const ps = prevSigMap[sid];
      const cs = currSigMap[sid];

      const prevContrib = ps ? Number(ps.contribution) : 0;
      const currContrib = cs ? Number(cs.contribution) : 0;
      const contribDelta = currContrib - prevContrib;

      if (Math.abs(contribDelta) < 0.001) continue;

      const prevRaw = ps && ps.raw_value !== null ? ps.raw_value : null;
      const currRaw = cs && cs.raw_value !== null ? cs.raw_value : null;
      const rawUnit = (cs && cs.raw_unit) || (ps && ps.raw_unit) || "";

      const prevLive = ps && ps.status === "live";
      const currLive = cs && cs.status === "live";
      const dataGap = !prevLive || !currLive;

      const name = (cs && cs.name) || (ps && ps.name) || sid;

      candidates.push({
        label: name,
        delta: contribDelta,
        prev_contribution: prevContrib,
        contribution: currContrib,
        prev_raw: prevRaw,
        raw: currRaw,
        raw_unit: rawUnit,
        data_gap: dataGap,
      });
    }

    candidates.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
    const topDrivers = candidates.slice(0, 3);
    const omittedCount = Math.max(0, candidates.length - 3);

    const sumParts = currStructural + (curr.pulse_adjustment || 0);
    const clampNote = Math.abs(sumParts - currComposite) > 0.01;

    let flat = false;
    if (topDrivers.length === 0) {
      flat = true;
    }

    steps.push({
      from_date: prev.date,
      to_date: curr.date,
      prev_composite: prevComposite,
      composite: currComposite,
      delta: delta,
      drivers: topDrivers,
      flat: flat,
      clamp_note: clampNote,
      omitted_count: omittedCount,
    });
  }
  return steps;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    parsePolymarketWsMessage,
    isFeedStale,
    computeTrendDrivers,
  };
}