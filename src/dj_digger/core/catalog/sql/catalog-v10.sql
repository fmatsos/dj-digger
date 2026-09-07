-- DJ Digger catalog schema V10
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

CREATE UNIQUE INDEX scan_runs_one_running_per_source
    ON scan_runs(source_id)
    WHERE status = 'running';

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
    id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES library_sources(source_id),
    relative_path TEXT NOT NULL,
    presence_status TEXT NOT NULL CHECK (presence_status IN ('present','missing')),
    discovered_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    missing_since TEXT NULL,
    last_seen_scan_id INTEGER NOT NULL,
    FOREIGN KEY (source_id, last_seen_scan_id) REFERENCES scan_runs(source_id, id),
    UNIQUE(source_id, relative_path)
);

CREATE TABLE embedded_metadata (
    track_id INTEGER PRIMARY KEY REFERENCES tracks(id),
    title TEXT NULL,
    artist TEXT NULL,
    album_artist TEXT NULL,
    album TEXT NULL,
    track_number TEXT NULL,
    disc_number TEXT NULL,
    genre TEXT NULL,
    date TEXT NULL,
    year TEXT NULL,
    composer TEXT NULL,
    comment TEXT NULL,
    tag_bpm REAL NULL,
    tag_initial_key TEXT NULL,
    grouping TEXT NULL,
    metadata_extracted_at TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    input_size_bytes INTEGER NULL,
    input_mtime_ns INTEGER NULL,
    normalization_version TEXT NULL
);

CREATE TABLE technical_audio_metadata (
    track_id INTEGER PRIMARY KEY REFERENCES tracks(id),
    duration_seconds REAL NULL,
    sample_rate INTEGER NULL,
    channels INTEGER NULL,
    codec TEXT NULL,
    container TEXT NULL,
    bitrate INTEGER NULL,
    lossless INTEGER NULL,
    loudness_lufs REAL NULL,
    true_peak_db REAL NULL,
    dynamic_range REAL NULL,
    probe_version TEXT NOT NULL,
    probed_at TEXT NOT NULL,
    bit_depth INTEGER NULL,
    input_size_bytes INTEGER NULL,
    input_mtime_ns INTEGER NULL
);

CREATE TABLE library_artifacts (
    id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES library_sources(source_id),
    relative_path TEXT NOT NULL,
    artifact_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    presence_status TEXT NOT NULL CHECK (presence_status IN ('present','missing')),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    missing_since TEXT NULL,
    last_seen_scan_id INTEGER NOT NULL,
    FOREIGN KEY (source_id, last_seen_scan_id) REFERENCES scan_runs(source_id, id),
    UNIQUE(source_id, relative_path)
);

CREATE TABLE analysis_runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT NULL,
    status TEXT NOT NULL,
    eligible INTEGER NOT NULL DEFAULT 0,
    analyzed INTEGER NOT NULL DEFAULT 0,
    reused INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    analysis_schema_version INTEGER NOT NULL,
    analyzer_version TEXT NOT NULL,
    config_hash TEXT NOT NULL
);

CREATE TABLE audio_analysis (
    id INTEGER PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id),
    analysis_run_id INTEGER NOT NULL REFERENCES analysis_runs(id),
    analysis_schema_version INTEGER NOT NULL,
    analyzer_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    input_size_bytes INTEGER NOT NULL,
    input_mtime_ns INTEGER NOT NULL,
    analysis_status TEXT NOT NULL,
    analysis_confidence REAL NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE track_sections (
    id INTEGER PRIMARY KEY,
    audio_analysis_id INTEGER NOT NULL REFERENCES audio_analysis(id) ON DELETE CASCADE,
    section_index INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE(audio_analysis_id, section_index)
);

CREATE TABLE track_events (
    id INTEGER PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id),
    occurred_at TEXT NOT NULL,
    scan_run_id INTEGER NULL REFERENCES scan_runs(id),
    analysis_run_id INTEGER NULL REFERENCES analysis_runs(id),
    event_type TEXT NOT NULL,
    payload_json TEXT NULL
);

CREATE INDEX idx_audio_analysis_success_lookup
ON audio_analysis (
    track_id, input_size_bytes, input_mtime_ns,
    analysis_schema_version, analyzer_version, config_hash
)
WHERE analysis_status = 'succeeded';

CREATE INDEX idx_audio_analysis_run_status
ON audio_analysis (analysis_run_id, analysis_status);

CREATE INDEX idx_audio_analysis_track_history
ON audio_analysis (track_id, id DESC);

CREATE INDEX idx_track_events_analysis_run_type
ON track_events (analysis_run_id, event_type);

CREATE INDEX idx_tracks_present_reconciliation
ON tracks (source_id, last_seen_scan_id)
WHERE presence_status = 'present';

CREATE INDEX idx_directories_present_reconciliation
ON directories (source_id, last_seen_scan_id)
WHERE presence_status = 'present';

CREATE INDEX idx_library_artifacts_present_reconciliation
ON library_artifacts (source_id, last_seen_scan_id)
WHERE presence_status = 'present';

CREATE TABLE current_track_analysis (
    track_id INTEGER PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
    audio_analysis_id INTEGER NOT NULL UNIQUE REFERENCES audio_analysis(id),
    analysis_schema_version INTEGER NOT NULL,
    analyzer_version TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    analysis_confidence REAL NULL,
    bpm REAL NULL,
    bpm_confidence REAL NULL,
    beat_stability REAL NULL,
    key TEXT NULL,
    key_confidence REAL NULL,
    sub_energy REAL NULL,
    low_energy REAL NULL,
    low_mid_energy REAL NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE audio_fingerprints (
    track_id INTEGER PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    fingerprint_hash TEXT NOT NULL,
    fingerprint_version TEXT NOT NULL,
    input_size_bytes INTEGER NOT NULL,
    input_mtime_ns INTEGER NOT NULL,
    fingerprinted_at TEXT NOT NULL
);

CREATE INDEX audio_fingerprints_group_idx
    ON audio_fingerprints(fingerprint_hash);

CREATE TABLE duplicate_quality_selections (
    source_id TEXT NOT NULL REFERENCES library_sources(source_id),
    fingerprint_hash TEXT NOT NULL,
    preferred_track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    ranking_version TEXT NOT NULL,
    selected_at TEXT NOT NULL,
    PRIMARY KEY (source_id, fingerprint_hash)
);

CREATE TABLE mastering_analysis (
    id INTEGER PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id),
    analysis_version TEXT NOT NULL,
    input_size_bytes INTEGER NOT NULL,
    input_mtime_ns INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('succeeded','failed')),
    error_stage TEXT NULL,
    error_message TEXT NULL,
    analyzed_at TEXT NOT NULL,
    integrated_lufs REAL NULL CHECK (integrated_lufs IS NULL OR abs(integrated_lufs) <= 1.0e308),
    loudness_range_lu REAL NULL CHECK (loudness_range_lu IS NULL OR abs(loudness_range_lu) <= 1.0e308),
    true_peak_dbtp REAL NULL CHECK (true_peak_dbtp IS NULL OR abs(true_peak_dbtp) <= 1.0e308),
    short_term_lufs_p50 REAL NULL CHECK (short_term_lufs_p50 IS NULL OR abs(short_term_lufs_p50) <= 1.0e308),
    short_term_lufs_p95 REAL NULL CHECK (short_term_lufs_p95 IS NULL OR abs(short_term_lufs_p95) <= 1.0e308),
    peak_to_loudness_ratio_db REAL NULL CHECK (peak_to_loudness_ratio_db IS NULL OR abs(peak_to_loudness_ratio_db) <= 1.0e308)
);

CREATE INDEX mastering_analysis_success_lookup
ON mastering_analysis(track_id, input_size_bytes, input_mtime_ns, analysis_version, id DESC)
WHERE status = 'succeeded';
CREATE INDEX mastering_analysis_track_history ON mastering_analysis(track_id, id DESC);

CREATE TABLE current_mastering_analysis (
    track_id INTEGER PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
    mastering_analysis_id INTEGER NOT NULL UNIQUE REFERENCES mastering_analysis(id) ON DELETE CASCADE,
    analysis_version TEXT NOT NULL,
    integrated_lufs REAL NULL CHECK (integrated_lufs IS NULL OR abs(integrated_lufs) <= 1.0e308),
    loudness_range_lu REAL NULL CHECK (loudness_range_lu IS NULL OR abs(loudness_range_lu) <= 1.0e308),
    true_peak_dbtp REAL NULL CHECK (true_peak_dbtp IS NULL OR abs(true_peak_dbtp) <= 1.0e308),
    short_term_lufs_p50 REAL NULL CHECK (short_term_lufs_p50 IS NULL OR abs(short_term_lufs_p50) <= 1.0e308),
    short_term_lufs_p95 REAL NULL CHECK (short_term_lufs_p95 IS NULL OR abs(short_term_lufs_p95) <= 1.0e308),
    peak_to_loudness_ratio_db REAL NULL CHECK (peak_to_loudness_ratio_db IS NULL OR abs(peak_to_loudness_ratio_db) <= 1.0e308),
    updated_at TEXT NOT NULL
);

CREATE TABLE current_dj_analysis (
    track_id INTEGER PRIMARY KEY REFERENCES tracks(id) ON DELETE CASCADE,
    mastering_analysis_id INTEGER NOT NULL UNIQUE REFERENCES current_mastering_analysis(mastering_analysis_id) ON DELETE CASCADE,
    dj_target_lufs REAL NOT NULL CHECK (abs(dj_target_lufs) <= 1.0e308),
    dj_target_true_peak_dbtp REAL NOT NULL CHECK (abs(dj_target_true_peak_dbtp) <= 1.0e308),
    required_gain_db REAL NULL CHECK (required_gain_db IS NULL OR abs(required_gain_db) <= 1.0e308),
    available_gain_db REAL NULL CHECK (available_gain_db IS NULL OR abs(available_gain_db) <= 1.0e308),
    gain_deficit_db REAL NULL CHECK (gain_deficit_db IS NULL OR abs(gain_deficit_db) <= 1.0e308)
);

CREATE VIEW library_tracks AS
SELECT
    t.id AS track_id,
    t.source_id,
    t.relative_path,
    t.filename,
    t.extension,
    t.size_bytes,
    t.mtime_ns,
    s.root_path,
    s.set_eligible,
    s.analyze AS analysis_enabled,
    s.enabled AS source_enabled,
    e.title,
    e.artist,
    e.album_artist,
    e.album,
    e.track_number,
    e.disc_number,
    e.genre,
    e.date,
    e.year,
    e.composer,
    e.comment,
    e.tag_bpm,
    e.tag_initial_key,
    e.grouping,
    technical.duration_seconds,
    technical.sample_rate,
    technical.channels,
    technical.codec,
    technical.container,
    technical.bitrate,
    technical.lossless,
    technical.loudness_lufs,
    technical.true_peak_db,
    technical.dynamic_range,
    current.audio_analysis_id,
    current.analysis_schema_version,
    current.analyzer_version,
    current.config_hash,
    current.analysis_confidence,
    current.bpm,
    current.bpm_confidence,
    current.beat_stability,
    current.key,
    current.key_confidence,
    current.sub_energy,
    current.low_energy,
    current.low_mid_energy,
    current.updated_at AS analysis_updated_at,
    mastering.integrated_lufs,
    mastering.loudness_range_lu,
    mastering.true_peak_dbtp,
    mastering.short_term_lufs_p50,
    mastering.short_term_lufs_p95,
    mastering.peak_to_loudness_ratio_db,
    dj.required_gain_db,
    dj.available_gain_db,
    dj.gain_deficit_db
FROM tracks AS t
JOIN library_sources AS s ON s.source_id = t.source_id
LEFT JOIN embedded_metadata AS e ON e.track_id = t.id
LEFT JOIN technical_audio_metadata AS technical ON technical.track_id = t.id
LEFT JOIN current_track_analysis AS current ON current.track_id = t.id
LEFT JOIN current_mastering_analysis AS mastering
    ON mastering.track_id = t.id
   AND mastering.analysis_version = 'ffmpeg-ebur128/1'
   AND EXISTS (
       SELECT 1 FROM mastering_analysis AS mastering_attempt
       WHERE mastering_attempt.id = mastering.mastering_analysis_id
         AND mastering_attempt.input_size_bytes = t.size_bytes
         AND mastering_attempt.input_mtime_ns = t.mtime_ns
   )
LEFT JOIN current_dj_analysis AS dj
    ON dj.track_id = t.id
   AND dj.mastering_analysis_id = mastering.mastering_analysis_id
WHERE t.presence_status = 'present';

-- Preserve curation history when a referenced track becomes missing: scans update
-- tracks.presence_status in place. RESTRICT also prevents destructive track deletion.
CREATE TABLE curation_creations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    kind TEXT NOT NULL CHECK (kind IN ('set','playlist')),
    user_prompt TEXT NOT NULL,
    report_markdown TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft','validated')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    validated_at TEXT NULL,
    model_config_json TEXT NOT NULL CHECK (
        json_valid(model_config_json) AND json_type(model_config_json) = 'object'
    ),
    CHECK (
        (status = 'draft' AND validated_at IS NULL)
        OR (status = 'validated' AND validated_at IS NOT NULL)
    )
);

CREATE TABLE curation_creation_tracks (
    creation_id TEXT NOT NULL REFERENCES curation_creations(id) ON DELETE CASCADE,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE RESTRICT,
    position INTEGER NOT NULL CHECK (position > 0),
    PRIMARY KEY (creation_id, track_id),
    UNIQUE (creation_id, position)
);

CREATE INDEX curation_creation_tracks_track_idx
    ON curation_creation_tracks(track_id);
