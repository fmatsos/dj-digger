CREATE TEMP TABLE curation_creations_backup AS SELECT * FROM curation_creations;
CREATE TEMP TABLE curation_creation_tracks_backup AS SELECT * FROM curation_creation_tracks;
DROP TABLE curation_creation_tracks;
DROP TABLE curation_creations;

CREATE TABLE curation_creations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    kind TEXT NOT NULL CHECK (kind IN ('set','playlist')),
    user_prompt TEXT NOT NULL CHECK (length(trim(user_prompt, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))) > 0),
    report_markdown TEXT NOT NULL CHECK (length(trim(report_markdown, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))) > 0),
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

INSERT INTO curation_creations (
    id,
    name,
    kind,
    user_prompt,
    report_markdown,
    status,
    created_at,
    updated_at,
    validated_at,
    model_config_json
)
SELECT
    id,
    name,
    kind,
    CASE
        WHEN length(trim(user_prompt, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))) > 0 THEN user_prompt
        ELSE 'Legacy prompt unavailable'
    END,
    CASE
        WHEN length(trim(report_markdown, char(9, 10, 11, 12, 13, 28, 29, 30, 31, 32, 133, 160, 5760, 8192, 8193, 8194, 8195, 8196, 8197, 8198, 8199, 8200, 8201, 8202, 8232, 8233, 8239, 8287, 12288))) > 0 THEN report_markdown
        ELSE 'Legacy report unavailable'
    END,
    status,
    created_at,
    updated_at,
    validated_at,
    model_config_json
FROM curation_creations_backup;
INSERT INTO curation_creation_tracks SELECT * FROM curation_creation_tracks_backup;
DROP TABLE curation_creation_tracks_backup;
DROP TABLE curation_creations_backup;

CREATE INDEX curation_creation_tracks_track_idx
    ON curation_creation_tracks(track_id);
