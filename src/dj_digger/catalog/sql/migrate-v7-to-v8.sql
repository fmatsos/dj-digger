-- DJ Digger catalog migration V7 to V8

ALTER TABLE technical_audio_metadata ADD COLUMN bit_depth INTEGER NULL;
ALTER TABLE technical_audio_metadata ADD COLUMN input_size_bytes INTEGER NULL;
ALTER TABLE technical_audio_metadata ADD COLUMN input_mtime_ns INTEGER NULL;

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
