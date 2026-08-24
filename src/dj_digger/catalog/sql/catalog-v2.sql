UPDATE scan_runs
SET status = 'failed',
    finished_at = COALESCE(
        finished_at,
        strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now')
    ),
    error_stage = 'migration',
    error_message = 'superseded by V2 single-running invariant'
WHERE status = 'running'
  AND id < (
      SELECT MAX(newer.id)
      FROM scan_runs AS newer
      WHERE newer.source_id = scan_runs.source_id
        AND newer.status = 'running'
  );

CREATE UNIQUE INDEX scan_runs_one_running_per_source
    ON scan_runs(source_id)
    WHERE status = 'running';
