-- Repair catalogs migrated by the historical v4 ordering, whose sections FK
-- may still point at the dropped audio_analysis_v4_old table.
ALTER TABLE track_sections RENAME TO track_sections_v5_old;
CREATE TABLE track_sections (
    id INTEGER PRIMARY KEY,
    audio_analysis_id INTEGER NOT NULL REFERENCES audio_analysis(id) ON DELETE CASCADE,
    section_index INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE(audio_analysis_id, section_index)
);
INSERT INTO track_sections SELECT * FROM track_sections_v5_old;
DROP TABLE track_sections_v5_old;
