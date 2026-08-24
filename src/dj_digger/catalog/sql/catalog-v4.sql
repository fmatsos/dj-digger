-- Remove the v1 uniqueness that prevented append-only retries of failed attempts.
-- Rebuild the dependent sections table first so foreign keys remain enabled.
ALTER TABLE track_sections RENAME TO track_sections_v4_old;
CREATE TABLE track_sections (
    id INTEGER PRIMARY KEY, audio_analysis_id INTEGER NOT NULL REFERENCES audio_analysis(id) ON DELETE CASCADE,
    section_index INTEGER NOT NULL, payload_json TEXT NOT NULL, UNIQUE(audio_analysis_id, section_index)
);
INSERT INTO track_sections SELECT * FROM track_sections_v4_old;
DROP TABLE track_sections_v4_old;

ALTER TABLE audio_analysis RENAME TO audio_analysis_v4_old;
CREATE TABLE audio_analysis (
    id INTEGER PRIMARY KEY, track_id INTEGER NOT NULL REFERENCES tracks(id), analysis_run_id INTEGER NOT NULL REFERENCES analysis_runs(id),
    analysis_schema_version INTEGER NOT NULL, analyzer_version TEXT NOT NULL, config_hash TEXT NOT NULL,
    input_size_bytes INTEGER NOT NULL, input_mtime_ns INTEGER NOT NULL, analysis_status TEXT NOT NULL,
    analysis_confidence REAL NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
);
INSERT INTO audio_analysis SELECT * FROM audio_analysis_v4_old;
DROP TABLE audio_analysis_v4_old;
