-- Cloudflare D1 Schema for WW3 Risk Model
-- Version: 0.6.0

CREATE TABLE IF NOT EXISTS index_snapshots (
    id TEXT PRIMARY KEY,
    computed_at TEXT NOT NULL,
    model_version TEXT NOT NULL,
    scenario_id TEXT NOT NULL,
    total_index REAL NOT NULL,
    stage INTEGER NOT NULL,
    base_score REAL NOT NULL,
    interaction_bonus REAL NOT NULL,
    gate_multiplier REAL NOT NULL,
    peace_capacity REAL NOT NULL,
    band_1y REAL NOT NULL,
    band_5y REAL NOT NULL,
    band_10y REAL NOT NULL,
    layers_json TEXT NOT NULL,
    drivers_json TEXT NOT NULL,
    structural_index REAL,
    pulse_adjustment REAL DEFAULT 0.0,
    composite_index REAL,
    pulse_json TEXT
);

CREATE TABLE IF NOT EXISTS indicator_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT NOT NULL,
    indicator_id TEXT NOT NULL,
    layer TEXT NOT NULL,
    raw_value TEXT,
    raw_unit TEXT,
    normalized_score REAL NOT NULL,
    evidence_level TEXT NOT NULL,
    source_name TEXT,
    source_url TEXT,
    observation_date TEXT,
    publication_date TEXT,
    last_checked TEXT,
    stale_after_days INTEGER,
    is_stale INTEGER NOT NULL,
    FOREIGN KEY (snapshot_id) REFERENCES index_snapshots(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_snapshots_computed_at ON index_snapshots(computed_at DESC);
CREATE INDEX IF NOT EXISTS idx_observations_snapshot_id ON indicator_observations(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_observations_indicator_id ON indicator_observations(indicator_id);
