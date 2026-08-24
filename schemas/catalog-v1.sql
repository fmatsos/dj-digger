-- DJ Digger catalog schema V1 (planning reference; migrations remain authoritative)
PRAGMA foreign_keys = ON;

CREATE TABLE library_sources (
    source_id TEXT PRIMARY KEY,
    root_path TEXT NOT NULL,
    set_eligible INTEGER NOT NULL CHECK (set_eligible IN (0,1)),
    analyze INTEGER NOT NULL CHECK (analyze IN (0,1)),
    enabled INTEGER NOT NULL CHECK (enabled IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_successful_scan_id INTEGER NULL
);

CREATE TABLE scan_runs (
    id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES library_sources(source_id),
    started_at TEXT NOT NULL,
    finished_at TEXT NULL,
    status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed')),
    files_seen INTEGER NOT NULL DEFAULT 0,
    audio_seen INTEGER NOT NULL DEFAULT 0,
    artifacts_seen INTEGER NOT NULL DEFAULT 0,
    error_stage TEXT NULL,
    error_message TEXT NULL,
    scanner_version TEXT NOT NULL,
    UNIQUE(source_id, id)
);

CREATE TABLE tracks (
    id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES library_sources(source_id),
    relative_path TEXT NOT NULL,
    filename TEXT NOT NULL,
    extension TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    presence_status TEXT NOT NULL CHECK (presence_status IN ('present','missing')),
    discovered_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    missing_since TEXT NULL,
    last_restored_at TEXT NULL,
    created_scan_id INTEGER NOT NULL,
    last_seen_scan_id INTEGER NOT NULL,
    FOREIGN KEY (source_id, created_scan_id) REFERENCES scan_runs(source_id, id),
    FOREIGN KEY (source_id, last_seen_scan_id) REFERENCES scan_runs(source_id, id),
    UNIQUE(source_id, relative_path)
);

CREATE TABLE directories (
    id INTEGER PRIMARY KEY, source_id TEXT NOT NULL REFERENCES library_sources(source_id),
    relative_path TEXT NOT NULL, presence_status TEXT NOT NULL CHECK (presence_status IN ('present','missing')),
    discovered_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, missing_since TEXT NULL,
    last_seen_scan_id INTEGER NOT NULL,
    FOREIGN KEY (source_id, last_seen_scan_id) REFERENCES scan_runs(source_id, id),
    UNIQUE(source_id, relative_path)
);

CREATE TABLE embedded_metadata (
    track_id INTEGER PRIMARY KEY REFERENCES tracks(id), title TEXT NULL, artist TEXT NULL, album_artist TEXT NULL, album TEXT NULL,
    track_number TEXT NULL, disc_number TEXT NULL, genre TEXT NULL, date TEXT NULL, year TEXT NULL, composer TEXT NULL, comment TEXT NULL,
    tag_bpm REAL NULL, tag_initial_key TEXT NULL, grouping TEXT NULL, metadata_extracted_at TEXT NOT NULL, extractor_version TEXT NOT NULL
);

CREATE TABLE technical_audio_metadata (
    track_id INTEGER PRIMARY KEY REFERENCES tracks(id), duration_seconds REAL NULL, sample_rate INTEGER NULL, channels INTEGER NULL,
    codec TEXT NULL, container TEXT NULL, bitrate INTEGER NULL, lossless INTEGER NULL, loudness_lufs REAL NULL, true_peak_db REAL NULL,
    dynamic_range REAL NULL, probe_version TEXT NOT NULL, probed_at TEXT NOT NULL
);

CREATE TABLE library_artifacts (
    id INTEGER PRIMARY KEY, source_id TEXT NOT NULL REFERENCES library_sources(source_id), relative_path TEXT NOT NULL, artifact_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, presence_status TEXT NOT NULL CHECK (presence_status IN ('present','missing')),
    first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, missing_since TEXT NULL, last_seen_scan_id INTEGER NOT NULL,
    FOREIGN KEY (source_id, last_seen_scan_id) REFERENCES scan_runs(source_id, id),
    UNIQUE(source_id, relative_path)
);

CREATE TABLE analysis_runs (
    id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT NULL, status TEXT NOT NULL, eligible INTEGER NOT NULL DEFAULT 0,
    analyzed INTEGER NOT NULL DEFAULT 0, reused INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0, analysis_schema_version INTEGER NOT NULL,
    analyzer_version TEXT NOT NULL, config_hash TEXT NOT NULL
);

CREATE TABLE audio_analysis (
    id INTEGER PRIMARY KEY, track_id INTEGER NOT NULL REFERENCES tracks(id), analysis_run_id INTEGER NOT NULL REFERENCES analysis_runs(id),
    analysis_schema_version INTEGER NOT NULL, analyzer_version TEXT NOT NULL, config_hash TEXT NOT NULL, input_size_bytes INTEGER NOT NULL,
    input_mtime_ns INTEGER NOT NULL, analysis_status TEXT NOT NULL, analysis_confidence REAL NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL,
    UNIQUE(track_id, analysis_schema_version, analyzer_version, config_hash, input_size_bytes, input_mtime_ns)
);

CREATE TABLE track_sections (
    id INTEGER PRIMARY KEY, audio_analysis_id INTEGER NOT NULL REFERENCES audio_analysis(id) ON DELETE CASCADE, section_index INTEGER NOT NULL,
    payload_json TEXT NOT NULL, UNIQUE(audio_analysis_id, section_index)
);

CREATE TABLE track_events (
    id INTEGER PRIMARY KEY, track_id INTEGER NOT NULL REFERENCES tracks(id), occurred_at TEXT NOT NULL, scan_run_id INTEGER NULL REFERENCES scan_runs(id),
    analysis_run_id INTEGER NULL REFERENCES analysis_runs(id), event_type TEXT NOT NULL, payload_json TEXT NULL
);
