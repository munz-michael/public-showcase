"""Database schema migrations."""

from __future__ import annotations

import sqlite3

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    project_type TEXT DEFAULT '',
    description TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    last_scanned_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    file_path TEXT NOT NULL UNIQUE,
    file_type TEXT NOT NULL,
    title TEXT DEFAULT '',
    file_size INTEGER DEFAULT 0,
    line_count INTEGER DEFAULT 0,
    content_hash TEXT DEFAULT '',
    indexed_at TEXT NOT NULL DEFAULT (datetime('now')),
    modified_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    heading TEXT DEFAULT '',
    content TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    heading,
    content,
    content=chunks,
    content_rowid=id,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, heading, content)
    VALUES (new.id, new.heading, new.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, heading, content)
    VALUES('delete', old.id, old.heading, old.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, heading, content)
    VALUES('delete', old.id, old.heading, old.content);
    INSERT INTO chunks_fts(rowid, heading, content)
    VALUES (new.id, new.heading, new.content);
END;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
"""


SCHEMA_V2 = """
-- ============================================
-- COMPOSTING: Entropy tracking & nutrient store
-- ============================================

CREATE TABLE IF NOT EXISTS chunk_entropy (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id INTEGER NOT NULL,
    entropy_score REAL NOT NULL DEFAULT 0.0,
    last_validated_at TEXT NOT NULL DEFAULT (datetime('now')),
    validation_source TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunk_entropy_chunk ON chunk_entropy(chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunk_entropy_score ON chunk_entropy(entropy_score);

CREATE TABLE IF NOT EXISTS nutrients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_chunk_id INTEGER,
    source_document_id INTEGER,
    nutrient_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    usage_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (source_document_id) REFERENCES documents(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_nutrients_type ON nutrients(nutrient_type);

CREATE VIRTUAL TABLE IF NOT EXISTS nutrients_fts USING fts5(
    title, content,
    content=nutrients,
    content_rowid=id,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS nutrients_ai AFTER INSERT ON nutrients BEGIN
    INSERT INTO nutrients_fts(rowid, title, content)
    VALUES (new.id, new.title, new.content);
END;

CREATE TRIGGER IF NOT EXISTS nutrients_ad AFTER DELETE ON nutrients BEGIN
    INSERT INTO nutrients_fts(nutrients_fts, rowid, title, content)
    VALUES('delete', old.id, old.title, old.content);
END;

CREATE TABLE IF NOT EXISTS compost_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    entropy_score_at_composting REAL NOT NULL,
    nutrients_extracted INTEGER DEFAULT 0,
    composted_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================
-- FERMENTATION: Staging area & cross-references
-- ============================================

CREATE TABLE IF NOT EXISTS fermentation_chamber (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_document_id INTEGER,
    raw_content TEXT NOT NULL,
    title TEXT DEFAULT '',
    source_path TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'fermenting',
    confidence_score REAL DEFAULT 0.0,
    fermentation_started_at TEXT NOT NULL DEFAULT (datetime('now')),
    fermentation_duration_hours REAL DEFAULT 24.0,
    promoted_at TEXT,
    cross_ref_count INTEGER DEFAULT 0,
    contradiction_count INTEGER DEFAULT 0,
    enrichment_notes TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ferment_status ON fermentation_chamber(status);

CREATE TABLE IF NOT EXISTS fermentation_cross_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fermentation_id INTEGER NOT NULL,
    related_chunk_id INTEGER NOT NULL,
    relationship_type TEXT NOT NULL,
    similarity_score REAL DEFAULT 0.0,
    explanation TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (fermentation_id) REFERENCES fermentation_chamber(id) ON DELETE CASCADE,
    FOREIGN KEY (related_chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
);

-- ============================================
-- IMMUNE SYSTEM: Threat detection & memory
-- ============================================

CREATE TABLE IF NOT EXISTS immune_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_type TEXT NOT NULL,
    pattern_signature TEXT NOT NULL,
    detection_strategy TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'medium',
    times_detected INTEGER DEFAULT 1,
    times_effective INTEGER DEFAULT 0,
    fitness_score REAL DEFAULT 0.5,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_immune_pattern_type ON immune_patterns(pattern_type);
CREATE INDEX IF NOT EXISTS idx_immune_fitness ON immune_patterns(fitness_score);

CREATE TABLE IF NOT EXISTS immune_scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id INTEGER,
    document_id INTEGER,
    fermentation_id INTEGER,
    threat_type TEXT NOT NULL,
    threat_description TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.0,
    matched_pattern_id INTEGER,
    response_action TEXT DEFAULT 'flag',
    resolved INTEGER DEFAULT 0,
    scanned_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE SET NULL,
    FOREIGN KEY (matched_pattern_id) REFERENCES immune_patterns(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_immune_scan_chunk ON immune_scan_results(chunk_id);
CREATE INDEX IF NOT EXISTS idx_immune_scan_threat ON immune_scan_results(threat_type);

CREATE TABLE IF NOT EXISTS healthy_knowledge_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL UNIQUE,
    metric_value REAL NOT NULL,
    sample_count INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ============================================
-- BENCHMARKS: Results tracking
-- ============================================

CREATE TABLE IF NOT EXISTS benchmark_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    benchmark_name TEXT NOT NULL,
    component TEXT NOT NULL,
    variant TEXT NOT NULL,
    metrics_json TEXT NOT NULL DEFAULT '{}',
    config_json TEXT NOT NULL DEFAULT '{}',
    dataset_size INTEGER DEFAULT 0,
    run_duration_seconds REAL DEFAULT 0.0,
    run_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


SCHEMA_V4 = """
-- ============================================
-- STIGMERGY: Pheromone signals between components
-- ============================================

CREATE TABLE IF NOT EXISTS stigmergy_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_type TEXT NOT NULL,
    domain TEXT NOT NULL,
    intensity REAL NOT NULL DEFAULT 0.5,
    source_component TEXT NOT NULL,
    source_id INTEGER,
    metadata TEXT DEFAULT '',
    reinforcement_count INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    last_reinforced_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_stigmergy_domain ON stigmergy_signals(domain);
CREATE INDEX IF NOT EXISTS idx_stigmergy_type ON stigmergy_signals(signal_type);
CREATE INDEX IF NOT EXISTS idx_stigmergy_active ON stigmergy_signals(active);

-- ============================================
-- QUORUM SENSING: Collective threat events
-- ============================================

CREATE TABLE IF NOT EXISTS quorum_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    threat_type TEXT NOT NULL,
    chunk_count INTEGER NOT NULL,
    avg_confidence REAL NOT NULL,
    recommended_action TEXT NOT NULL,
    affected_chunk_ids TEXT DEFAULT '[]',
    resolved INTEGER DEFAULT 0,
    resolved_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_quorum_domain ON quorum_events(domain);
CREATE INDEX IF NOT EXISTS idx_quorum_resolved ON quorum_events(resolved);

-- ============================================
-- HOMEOSTASIS: Self-regulating parameters & metrics
-- ============================================

CREATE TABLE IF NOT EXISTS homeostasis_params (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parameter TEXT NOT NULL,
    value REAL NOT NULL,
    domain TEXT,
    last_reason TEXT DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(parameter, domain)
);

CREATE TABLE IF NOT EXISTS homeostasis_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_homeostasis_metric ON homeostasis_metrics(metric_name);
CREATE INDEX IF NOT EXISTS idx_homeostasis_time ON homeostasis_metrics(recorded_at);
"""


def _enable_vec_if_available(conn: sqlite3.Connection) -> bool:
    """Try to load sqlite-vec extension. Returns True if available."""
    try:
        import sqlite_vec
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return True
    except (ImportError, Exception):
        return False


def run_migrations(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
    if cursor.fetchone() is None:
        cursor.executescript(SCHEMA_V1)
        cursor.execute("INSERT INTO schema_version (version) VALUES (1)")

    current_version = cursor.execute("SELECT version FROM schema_version").fetchone()[0]

    if current_version < 2:
        cursor.executescript(SCHEMA_V2)
        cursor.execute("UPDATE schema_version SET version = 2")

    if current_version < 3:
        if _enable_vec_if_available(conn):
            from akm.search.embeddings import EMBEDDING_DIM, create_vec_table
            create_vec_table(conn)
        cursor.execute("UPDATE schema_version SET version = 3")

    if current_version < 4:
        cursor.executescript(SCHEMA_V4)
        cursor.execute("UPDATE schema_version SET version = 4")
