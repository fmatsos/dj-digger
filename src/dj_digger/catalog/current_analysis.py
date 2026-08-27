"""Materialized latest-successful-analysis projection."""

from dj_digger.catalog.database import Database

UPSERT_CURRENT = """
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
WHERE analysis.analysis_status = 'succeeded'
  AND (
      analysis.id = ?
      OR (
          ? IS NULL
          AND analysis.id IN (
              SELECT MAX(id)
              FROM audio_analysis
              WHERE analysis_status = 'succeeded'
              GROUP BY track_id
          )
      )
  )
ORDER BY analysis.track_id
ON CONFLICT(track_id) DO UPDATE SET
    audio_analysis_id = excluded.audio_analysis_id,
    analysis_schema_version = excluded.analysis_schema_version,
    analyzer_version = excluded.analyzer_version,
    config_hash = excluded.config_hash,
    analysis_confidence = excluded.analysis_confidence,
    bpm = excluded.bpm,
    bpm_confidence = excluded.bpm_confidence,
    beat_stability = excluded.beat_stability,
    key = excluded.key,
    key_confidence = excluded.key_confidence,
    sub_energy = excluded.sub_energy,
    low_energy = excluded.low_energy,
    low_mid_energy = excluded.low_mid_energy,
    updated_at = excluded.updated_at
WHERE excluded.audio_analysis_id > current_track_analysis.audio_analysis_id
"""


class CurrentAnalysisProjector:
    """Advance or deterministically rebuild the current successful projection."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def advance(self, audio_analysis_id: int) -> bool:
        """Project one successful attempt when it is newer than the current one."""
        cursor = self._database.execute(
            UPSERT_CURRENT, (audio_analysis_id, audio_analysis_id)
        )
        return cursor.rowcount == 1

    def rebuild(self) -> int:
        """Recreate the projection from the latest successful attempt per track."""
        with self._database.transaction():
            self._database.execute("DELETE FROM current_track_analysis")
            self._database.execute(UPSERT_CURRENT, (None, None))
            count = int(self._database.scalar("SELECT COUNT(*) FROM current_track_analysis"))
        return count
