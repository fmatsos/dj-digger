"""Validated, source-aware publication of persisted analysis facets."""

import csv
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]

from dj_digger.catalog.database import Database
from dj_digger.exports.formats import (
    fields_for_schema,
    output_path,
    projected,
    select_fields,
    write_object,
    write_rows,
)
from dj_digger.exports.tracks import PublishedFacet


@dataclass(frozen=True)
class _Schemas:
    analysis: dict[str, Any]
    sections: dict[str, Any]
    run: dict[str, Any]


class AnalysisExporter:
    """Project immutable analysis attempts through their current source tracks."""

    def __init__(self, database: Database, *, schemas_directory: Path | None = None) -> None:
        self._database = database
        directory = schemas_directory or Path(__file__).resolve().parents[3] / "schemas"
        if not directory.exists():
            package_schemas = resources.files("dj_digger").joinpath("schemas")
            # Materialize package resources only when a filesystem path is needed.
            directory = Path(str(package_schemas))
        self._schemas = _Schemas(
            **{
                name: cast(dict[str, Any], json.loads((directory / filename).read_text("utf-8")))
                for name, filename in (
                    ("analysis", "dj-analysis.schema.json"),
                    ("sections", "dj-sections.schema.json"),
                    ("run", "dj-analysis-run.schema.json"),
                )
            }
        )
        for schema in (self._schemas.analysis, self._schemas.sections, self._schemas.run):
            Draft202012Validator.check_schema(schema)
        self._analysis_validator = Draft202012Validator(self._schemas.analysis)
        self._sections_validator = Draft202012Validator(self._schemas.sections)
        self._run_validator = Draft202012Validator(
            self._schemas.run, format_checker=FormatChecker()
        )
        self._columns = cast(list[str], self._schemas.analysis["x-tabular"]["columns"])

    def export(
        self,
        destination: Path,
        *,
        format: str | None = None,
        fields: str | None = None,
        leaf_type: str | None = None,
    ) -> list[PublishedFacet]:
        with self._database.read_transaction():
            analyses = self._analysis_rows()
            sections = self._section_rows(analyses)
            run = self._run_summary()

        # Validate every artifact before publishing any of the three atomically.
        for row in analyses:
            self._analysis_validator.validate(row)
        for row in sections:
            self._sections_validator.validate(row)
        self._run_validator.validate(run)

        if format is not None or fields is not None:
            effective_formats = {
                "analysis": format or "tsv",
                "sections": format or "json",
                "run": format or "json",
            }
            if format is not None and format not in {"json", "csv", "tsv"}:
                raise ValueError(f"unknown export format: {format}")
            schema_fields = {
                "analysis": fields_for_schema(self._schemas.analysis),
                "sections": fields_for_schema(self._schemas.sections),
                "run": fields_for_schema(self._schemas.run),
            }
            selected_types = (
                (leaf_type,)
                if leaf_type in {"analysis", "sections", "run"}
                else ("analysis", "sections", "run")
            )
            chosen = select_fields(schema_fields[selected_types[0]], fields)
            paths_by_type = {
                "analysis": output_path(destination / "dj-analysis.tsv", format or "tsv"),
                "sections": output_path(destination / "dj-sections.jsonl", format or "json"),
                "run": output_path(destination / "dj-analysis-run.json", format or "json"),
            }
            # Validate full rows above, then stage every selected artifact before replacement.
            destination.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix=".analysis-publish-", dir=destination) as tmp:
                staged_by_type = {
                    name: Path(tmp) / path.name for name, path in paths_by_type.items()
                }
                if "analysis" in selected_types:
                    write_rows(
                        staged_by_type["analysis"],
                        projected(analyses, chosen),
                        chosen or schema_fields["analysis"],
                        effective_formats["analysis"],
                    )
                if "sections" in selected_types:
                    write_rows(
                        staged_by_type["sections"],
                        projected(sections, chosen),
                        chosen or schema_fields["sections"],
                        effective_formats["sections"],
                    )
                if "run" in selected_types:
                    value = run if chosen is None else {k: run.get(k) for k in chosen}
                    write_object(
                        staged_by_type["run"],
                        value,
                        chosen or schema_fields["run"],
                        effective_formats["run"],
                    )
                custom_backups: list[tuple[Path, Path]] = []
                custom_replaced: list[Path] = []
                try:
                    for name in selected_types:
                        target = paths_by_type[name]
                        if target.exists():
                            backup = Path(tmp) / f"{target.name}.bak"
                            os.replace(target, backup)
                            custom_backups.append((target, backup))
                    for name in selected_types:
                        target = paths_by_type[name]
                        os.replace(staged_by_type[name], target)
                        custom_replaced.append(target)
                except BaseException:
                    for target in custom_replaced:
                        target.unlink(missing_ok=True)
                    for target, backup in custom_backups:
                        if backup.exists():
                            os.replace(backup, target)
                    raise
            counts = {"analysis": len(analyses), "sections": len(sections), "run": 1}
            return [PublishedFacet(paths_by_type[name], counts[name]) for name in selected_types]

        analysis_path = destination / "dj-analysis.tsv"
        sections_path = destination / "dj-sections.jsonl"
        run_path = destination / "dj-analysis-run.json"
        # Stage all three writers first.  Existing facets remain untouched if any
        # writer fails; replacements happen only after every artifact is complete.
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".analysis-publish-", dir=destination) as tmp:
            staged = [Path(tmp) / path.name for path in (analysis_path, sections_path, run_path)]
            self._write_tsv(staged[0], analyses)
            self._write_jsonl(staged[1], sections)
            self._write_json(staged[2], run)
            for path in staged:
                with path.open("rb") as handle:
                    os.fsync(handle.fileno())
            targets = (analysis_path, sections_path, run_path)
            backups: list[tuple[Path, Path]] = []
            replaced: list[Path] = []
            try:
                for target in targets:
                    if target.exists():
                        backup = Path(tmp) / (target.name + ".bak")
                        os.replace(target, backup)
                        backups.append((target, backup))
                for source, target in zip(staged, targets):
                    os.replace(source, target)
                    replaced.append(target)
            except BaseException:
                for target in replaced:
                    target.unlink(missing_ok=True)
                for target, backup in backups:
                    if backup.exists():
                        os.replace(backup, target)
                raise
        return [
            PublishedFacet(analysis_path, len(analyses)),
            PublishedFacet(sections_path, len(sections)),
            PublishedFacet(run_path, 1),
        ]

    def _analysis_rows(self) -> list[dict[str, Any]]:
        rows = self._database.execute(
            """
            WITH current_attempt AS (
                SELECT a.*, ROW_NUMBER() OVER (PARTITION BY a.track_id ORDER BY a.id DESC) AS rank
                FROM audio_analysis a
            )
            SELECT t.source_id, t.id, t.relative_path, t.size_bytes, t.mtime_ns,
                   a.analysis_schema_version, a.analyzer_version, a.config_hash,
                   a.analysis_status, a.analysis_confidence, a.payload_json, a.id
            FROM current_attempt a
            JOIN tracks t ON t.id = a.track_id
            WHERE a.rank = 1 AND t.presence_status = 'present'
            ORDER BY t.source_id, t.relative_path, t.id
            """
        ).fetchall()
        result: list[dict[str, Any]] = []
        for (
            source_id,
            track_id,
            path,
            size,
            mtime,
            version,
            analyzer,
            config,
            status,
            confidence,
            raw,
            _,
        ) in rows:
            payload = _object(raw)
            row: dict[str, Any] = {column: None for column in self._columns}
            row.update(
                {
                    "source_id": str(source_id),
                    "track_id": int(track_id),
                    "path": str(path),
                    "size_bytes": int(size),
                    "mtime": int(mtime),
                    "analysis_schema_version": int(version),
                    "analyzer_version": str(analyzer),
                    "config_hash": str(config),
                    "analysis_status": _public_status(str(status)),
                    "analysis_confidence": confidence,
                }
            )
            row.update({key: value for key, value in payload.items() if key in row})
            # Persisted attempt identity is authoritative over payload duplicates.
            row.update(
                {
                    "source_id": str(source_id),
                    "track_id": int(track_id),
                    "path": str(path),
                    "size_bytes": int(size),
                    "mtime": int(mtime),
                    "analysis_schema_version": int(version),
                    "analyzer_version": str(analyzer),
                    "config_hash": str(config),
                    "analysis_status": _public_status(str(status)),
                    "analysis_confidence": confidence,
                }
            )
            # Minimal/failed attempts have no window facts; represent each
            # unavailable window explicitly while keeping all other facts null.
            for key, value in row.items():
                if key.endswith("_available") and value is None:
                    row[key] = False
            result.append(row)
        return result

    def _section_rows(self, analyses: list[dict[str, Any]]) -> list[dict[str, Any]]:
        analysis_ids = self._database.execute(
            """
            WITH current_attempt AS (
                SELECT a.id, a.track_id,
                       ROW_NUMBER() OVER (PARTITION BY a.track_id ORDER BY a.id DESC) AS rank
                FROM audio_analysis a
            )
            SELECT a.id, t.source_id, t.id, t.relative_path, aa.analysis_schema_version
            FROM current_attempt a JOIN audio_analysis aa ON aa.id = a.id
            JOIN tracks t ON t.id = a.track_id
            WHERE a.rank = 1 AND t.presence_status = 'present'
            ORDER BY t.source_id, t.relative_path, t.id
            """
        ).fetchall()
        result: list[dict[str, Any]] = []
        for analysis_id, source_id, track_id, path, version in analysis_ids:
            records = self._database.execute(
                "SELECT payload_json FROM track_sections WHERE audio_analysis_id = ? "
                "ORDER BY section_index",
                (analysis_id,),
            ).fetchall()
            if records:
                result.append(
                    {
                        "source_id": str(source_id),
                        "track_id": int(track_id),
                        "path": str(path),
                        "analysis_schema_version": int(version),
                        "sections": [_object(record[0]) for record in records],
                    }
                )
        return result

    def _run_summary(self) -> dict[str, Any]:
        row = self._database.execute(
            """
            SELECT id, started_at, finished_at, status, eligible, analyzed, reused, failed,
                   analysis_schema_version, analyzer_version, config_hash
            FROM analysis_runs ORDER BY id DESC LIMIT 1
            """
        ).fetchone()
        if row is None:
            raise ValueError("cannot publish analysis facets without an analysis run")
        (
            run_id,
            started,
            finished,
            status,
            eligible,
            analyzed,
            reused,
            failed,
            version,
            analyzer,
            config,
        ) = row
        failures = self._database.execute(
            """
            SELECT t.source_id, t.id, t.relative_path, e.payload_json
            FROM track_events e JOIN tracks t ON t.id = e.track_id
            WHERE e.analysis_run_id = ? AND e.event_type = 'analysis_failed'
            ORDER BY t.source_id, t.relative_path, t.id, e.id
            """,
            (run_id,),
        ).fetchall()
        return {
            "analysis_schema_version": int(version),
            "catalog_schema_version": 1,
            "started_at": str(started),
            "finished_at": str(finished),
            "status": str(status),
            "eligible": int(eligible),
            "analyzed": int(analyzed),
            "reused": int(reused),
            "failed": int(failed),
            "config_hash": str(config),
            "analyzer_version": str(analyzer),
            "failures": [
                {
                    "source_id": str(source_id),
                    "track_id": int(track_id),
                    "path": str(path),
                    "stage": str(_object(raw).get("stage", "persist")),
                    "error": str(_object(raw).get("error", "analysis failed")),
                }
                for source_id, track_id, path, raw in failures
            ],
        }

    def _write_tsv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=self._columns, delimiter="\t", lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows({key: _serialize(row[key]) for key in self._columns} for row in rows)

    @staticmethod
    def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            for row in rows:
                handle.write(
                    json.dumps(row, allow_nan=False, separators=(",", ":"), sort_keys=True)
                )
                handle.write("\n")

    @staticmethod
    def _write_json(path: Path, row: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(row, allow_nan=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def _object(raw: object) -> Mapping[str, Any]:
    value = json.loads(cast(str, raw))
    if not isinstance(value, dict):
        raise ValueError("analysis payload must be a JSON object")
    return cast(Mapping[str, Any], value)


def _public_status(status: str) -> str:
    return "ok" if status == "succeeded" else status


def _serialize(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return value
