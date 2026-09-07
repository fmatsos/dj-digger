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
