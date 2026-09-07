from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

import dj_digger.core.exports.curation as curation_export_module
from dj_digger.cli import app
from dj_digger.core.catalog.database import Database
from dj_digger.core.config import LibrarySourceConfig, WorkspaceConfig
from dj_digger.core.curation import CreateCurationDraft, CurationRepository, CurationTrack
from dj_digger.core.exports.curation import CurationExportContent, export_curation


def _fixture(tmp_path: Path, *, multiple_sources: bool = False) -> tuple[Database, WorkspaceConfig]:
    roots = (tmp_path / "source-a", tmp_path / "source-b")
    for root in roots:
        root.mkdir()
    files = (roots[0] / "first.flac", roots[int(multiple_sources)] / "second.flac")
    for position, path in enumerate(files, 1):
        path.write_bytes(bytes([position]))
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    for position, root in enumerate(roots, 1):
        source_id = f"source-{position}"
        database.execute(
            "INSERT INTO library_sources VALUES (?, ?, 1, 1, 1, 'now', 'now', NULL)",
            (source_id, str(root)),
        )
        database.execute(
            "INSERT INTO scan_runs (id, source_id, started_at, status, scanner_version) "
            "VALUES (?, ?, 'now', 'succeeded', 'test')",
            (position, source_id),
        )
    for track_id, path in enumerate(files, 1):
        source_number = 2 if multiple_sources and track_id == 2 else 1
        status = path.stat()
        database.execute(
            """INSERT INTO tracks (
                id, source_id, relative_path, filename, extension, size_bytes, mtime_ns,
                presence_status, discovered_at, last_seen_at, created_scan_id, last_seen_scan_id
            ) VALUES (?, ?, ?, ?, '.flac', ?, ?, 'present', 'now', 'now', ?, ?)""",
            (
                track_id,
                f"source-{source_number}",
                path.name,
                path.name,
                status.st_size,
                status.st_mtime_ns,
                source_number,
                source_number,
            ),
        )
    database.commit()
    CurationRepository(database).create_draft(
        CreateCurationDraft(
            id="export-id",
            name="Ordered export",
            kind="set",
            user_prompt="Create an ordered export",
            report_markdown="# Exact report\n\nNo generated suffix.\n",
            model_config_data={"model": "fixture"},
            tracks=(CurationTrack(track_id=2, position=1), CurationTrack(track_id=1, position=2)),
        )
    )
    config = WorkspaceConfig(
        database=tmp_path / "catalog.sqlite",
        exports=tmp_path / "exports",
        sources=tuple(
            LibrarySourceConfig(f"source-{index}", root, True, True)
            for index, root in enumerate(roots, 1)
        ),
    )
    return database, config


@pytest.mark.parametrize("content", ["playlist", "report", "both"])
@pytest.mark.parametrize("copy_files", [False, True])
def test_all_content_and_copy_combinations(tmp_path: Path, content: str, copy_files: bool) -> None:
    database, config = _fixture(tmp_path)
    output = tmp_path / "published"

    export_curation(
        database,
        config,
        "export-id",
        content=cast(CurationExportContent, content),
        copy_files=copy_files,
        output=output,
    )

    assert (output / "curation.m3u8").exists() is (content in {"playlist", "both"})
    assert (output / "report.md").exists() is (content in {"report", "both"})
    if content in {"report", "both"}:
        assert (output / "report.md").read_text() == "# Exact report\n\nNo generated suffix.\n"
    if content in {"playlist", "both"}:
        lines = (output / "curation.m3u8").read_text().splitlines()[1:]
        assert lines[0].endswith("second.flac")
        assert lines[1].endswith("first.flac")
    assert (output / "tracks").exists() is copy_files


def test_report_only_without_copy_does_not_require_source_files(tmp_path: Path) -> None:
    database, config = _fixture(tmp_path)
    for source in config.sources:
        source.path.rename(source.path.with_name(f"{source.path.name}-offline"))

    output = tmp_path / "report-only"
    export_curation(
        database,
        config,
        "export-id",
        content="report",
        copy_files=False,
        output=output,
    )

    assert (output / "report.md").read_text() == "# Exact report\n\nNo generated suffix.\n"
    assert not (output / "curation.m3u8").exists()
    assert not (output / "tracks").exists()


def test_multi_source_playlist_requires_portable_copy(tmp_path: Path) -> None:
    database, config = _fixture(tmp_path, multiple_sources=True)

    with pytest.raises(ValueError, match="multi-source.*--copy-files"):
        export_curation(
            database,
            config,
            "export-id",
            content="playlist",
            copy_files=False,
            output=tmp_path / "not-published",
        )

    assert not (tmp_path / "not-published").exists()


def test_missing_changed_and_unsafe_tracks_never_publish(tmp_path: Path) -> None:
    database, config = _fixture(tmp_path)
    (tmp_path / "source-a" / "second.flac").unlink()
    with pytest.raises(ValueError, match="missing"):
        export_curation(
            database,
            config,
            "export-id",
            content="both",
            copy_files=True,
            output=tmp_path / "missing",
        )
    database.execute("UPDATE tracks SET relative_path = '../escape.flac' WHERE id = 2")
    database.commit()
    with pytest.raises(ValueError, match="unsafe relative"):
        export_curation(
            database,
            config,
            "export-id",
            content="report",
            copy_files=False,
            output=tmp_path / "unsafe",
        )
    assert not (tmp_path / "missing").exists()
    assert not (tmp_path / "unsafe").exists()


def test_destination_symlink_is_refused(tmp_path: Path) -> None:
    database, config = _fixture(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    output = tmp_path / "published"
    output.symlink_to(external, target_is_directory=True)

    with pytest.raises(ValueError, match="symbolic link"):
        export_curation(
            database,
            config,
            "export-id",
            content="both",
            copy_files=True,
            output=output,
        )
    assert list(external.iterdir()) == []


def test_validated_creation_exports(tmp_path: Path) -> None:
    database, config = _fixture(tmp_path)
    CurationRepository(database).validate("export-id")

    result = export_curation(
        database,
        config,
        "export-id",
        content="report",
        copy_files=False,
        output=tmp_path / "validated",
    )

    assert result.track_count == 2
    assert (result.output / "report.md").read_text() == "# Exact report\n\nNo generated suffix.\n"


def test_copy_failure_cleans_staging_and_publishes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, config = _fixture(tmp_path)
    real_copy = curation_export_module.copy_track_atomic
    calls = 0

    def fail_second(
        source: Path,
        target_dir: Path,
        name: str,
        directory_fd: int | None,
        *,
        expected_size: int,
        expected_mtime_ns: int,
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected copy failure")
        real_copy(
            source,
            target_dir,
            name,
            directory_fd,
            expected_size=expected_size,
            expected_mtime_ns=expected_mtime_ns,
        )

    monkeypatch.setattr(curation_export_module, "copy_track_atomic", fail_second)
    output = tmp_path / "failed"
    with pytest.raises(OSError, match="injected"):
        export_curation(
            database,
            config,
            "export-id",
            content="both",
            copy_files=True,
            output=output,
        )

    assert not output.exists()
    assert list(tmp_path.glob(".failed.*")) == []


def test_source_changed_during_copy_never_publishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database, config = _fixture(tmp_path)
    real_copy = curation_export_module.copy_track_atomic
    changed_source = tmp_path / "source-a" / "second.flac"

    def change_after_copy(
        source: Path,
        target_dir: Path,
        name: str,
        directory_fd: int | None,
        *,
        expected_size: int,
        expected_mtime_ns: int,
    ) -> None:
        real_copy(
            source,
            target_dir,
            name,
            directory_fd,
            expected_size=expected_size,
            expected_mtime_ns=expected_mtime_ns,
        )
        if source == changed_source:
            source.write_bytes(b"changed after copy")

    monkeypatch.setattr(curation_export_module, "copy_track_atomic", change_after_copy)
    output = tmp_path / "changed-during-copy"

    with pytest.raises(ValueError, match="identity changed.*rescan"):
        export_curation(
            database,
            config,
            "export-id",
            content="both",
            copy_files=True,
            output=output,
        )

    assert not output.exists()
    assert list(tmp_path.glob(".changed-during-copy.*")) == []


@pytest.mark.parametrize("content", ["playlist", "report", "both"])
@pytest.mark.parametrize("copy_files", [False, True])
def test_cli_supports_every_content_and_copy_combination(
    tmp_path: Path, content: str, copy_files: bool
) -> None:
    database, config = _fixture(tmp_path)
    database.close()
    config_path = tmp_path / "config.toml"
    source_lines = "\n".join(
        f'''[[library.sources]]
id = "{source.id}"
path = "{source.path}"
set_eligible = true
analyze = true
'''
        for source in config.sources
    )
    config_path.write_text(
        f'''[workspace]
database = "{config.database}"
exports = "{config.exports}"

[library]
{source_lines}''',
        encoding="utf-8",
    )
    output = tmp_path / f"cli-{content}-{copy_files}"
    arguments = [
        "curation",
        "export",
        "export-id",
        "--content",
        content,
        "--output",
        str(output),
        "--config",
        str(config_path),
    ]
    if copy_files:
        arguments.append("--copy-files")

    result = CliRunner().invoke(app, arguments)

    assert result.exit_code == 0, result.output
    assert "Exported 2 tracks" in result.stdout
    assert (output / "curation.m3u8").exists() is (content in {"playlist", "both"})
    assert (output / "report.md").exists() is (content in {"report", "both"})
    assert (output / "tracks").exists() is copy_files
