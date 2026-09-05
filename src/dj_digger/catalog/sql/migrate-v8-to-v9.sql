-- DJ Digger catalog migration V8 to V9.
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
CREATE INDEX mastering_analysis_success_lookup ON mastering_analysis(track_id, input_size_bytes, input_mtime_ns, analysis_version, id DESC) WHERE status = 'succeeded';
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
DROP VIEW library_tracks;
CREATE VIEW library_tracks AS
SELECT t.id AS track_id, t.source_id, t.relative_path, t.filename, t.extension, t.size_bytes, t.mtime_ns,
 s.root_path, s.set_eligible, s.analyze AS analysis_enabled, s.enabled AS source_enabled,
 e.title, e.artist, e.album_artist, e.album, e.track_number, e.disc_number, e.genre, e.date, e.year,
 e.composer, e.comment, e.tag_bpm, e.tag_initial_key, e.grouping,
 technical.duration_seconds, technical.sample_rate, technical.channels, technical.codec,
 technical.container, technical.bitrate, technical.lossless, technical.loudness_lufs,
 technical.true_peak_db, technical.dynamic_range,
 current.audio_analysis_id, current.analysis_schema_version, current.analyzer_version,
 current.config_hash, current.analysis_confidence, current.bpm, current.bpm_confidence,
 current.beat_stability, current.key, current.key_confidence, current.sub_energy,
 current.low_energy, current.low_mid_energy, current.updated_at AS analysis_updated_at,
 mastering.integrated_lufs, mastering.loudness_range_lu, mastering.true_peak_dbtp,
 mastering.short_term_lufs_p50, mastering.short_term_lufs_p95, mastering.peak_to_loudness_ratio_db,
 dj.required_gain_db, dj.available_gain_db, dj.gain_deficit_db
FROM tracks AS t JOIN library_sources AS s ON s.source_id = t.source_id
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
