-- DJ Digger catalog migration V6 to V7

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

INSERT INTO current_track_analysis (
    track_id, audio_analysis_id, analysis_schema_version, analyzer_version, config_hash,
    analysis_confidence, bpm, bpm_confidence, beat_stability, key, key_confidence,
    sub_energy, low_energy, low_mid_energy, updated_at
)
SELECT
    analysis.track_id,
    analysis.id,
    analysis.analysis_schema_version,
    analysis.analyzer_version,
    analysis.config_hash,
    analysis.analysis_confidence,
    json_extract(analysis.payload_json, '$.bpm'),
    json_extract(analysis.payload_json, '$.bpm_confidence'),
    json_extract(analysis.payload_json, '$.beat_stability'),
    json_extract(analysis.payload_json, '$.key'),
    json_extract(analysis.payload_json, '$.key_confidence'),
    json_extract(analysis.payload_json, '$.sub_energy'),
    json_extract(analysis.payload_json, '$.low_energy'),
    json_extract(analysis.payload_json, '$.low_mid_energy'),
    analysis.created_at
FROM audio_analysis AS analysis
JOIN (
    SELECT track_id, MAX(id) AS audio_analysis_id
    FROM audio_analysis
    WHERE analysis_status = 'succeeded'
    GROUP BY track_id
) AS latest
    ON latest.audio_analysis_id = analysis.id;

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
    current.updated_at AS analysis_updated_at
FROM tracks AS t
JOIN library_sources AS s ON s.source_id = t.source_id
LEFT JOIN embedded_metadata AS e ON e.track_id = t.id
LEFT JOIN technical_audio_metadata AS technical ON technical.track_id = t.id
LEFT JOIN current_track_analysis AS current ON current.track_id = t.id
WHERE t.presence_status = 'present';
