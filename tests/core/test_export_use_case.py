"""Typed publication contracts for catalog exports."""

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import dj_digger.core.application.export as export_module
from dj_digger.core.application import (
    CoreApplication,
    DependencyError,
    ExportMaintenanceWarning,
    ExportRequest,
    ExportResult,
    ExportUseCase,
    InvalidInputError,
)
from dj_digger.core.config import LibrarySourceConfig, WorkspaceConfig
from dj_digger.core.exports.tracks import PublishedFacet


def _config(tmp_path: Path) -> WorkspaceConfig:
    source = tmp_path / "library"
    source.mkdir()
    return WorkspaceConfig(
        database=tmp_path / "catalog.sqlite",
        exports=tmp_path / "exports",
        sources=(LibrarySourceConfig("source", source, True, False, True),),
    )


def test_export_returns_typed_facets_and_row_counts(tmp_path: Path) -> None:
    config = _config(tmp_path)

    with CoreApplication(config) as core:
        result = core.export(ExportRequest(facet="tracks"))

    assert isinstance(result, ExportResult)
    assert [(facet.path.name, facet.row_count) for facet in result.facets] == [("tracks.tsv", 0)]
    assert result.paths == (config.exports / "tracks.tsv",)
    assert result.generation_path.is_dir()
    assert not list(tmp_path.glob(".exports-*"))


def test_export_cleanup_runs_after_publication_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(
        export_module.os,
        "symlink",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("link failed")),
    )

    with CoreApplication(config) as core:
        with pytest.raises(DependencyError, match="POSIX directory symlink"):
            core.export(ExportRequest(facet="tracks"))

    assert not list(tmp_path.glob(".exports-*"))


def test_generation_cleanup_runs_when_promotion_fails_after_staging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(
        export_module,
        "_temporary_link",
        lambda _destination: (_ for _ in ()).throw(OSError("promotion failed")),
    )

    with CoreApplication(config) as core:
        with pytest.raises(OSError, match="promotion failed"):
            core.export(ExportRequest(facet="tracks"))

    storage = config.exports.parent / ".dj-digger-publications"
    assert not storage.exists() or not list(storage.glob("generation-*"))


def test_cleanup_failure_after_switch_returns_success_with_typed_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config = _config(tmp_path)
    monkeypatch.setattr(
        export_module,
        "_cleanup_generations",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("maintenance failed")),
    )

    with CoreApplication(config) as core:
        result = core.export(ExportRequest(facet="tracks"))

    assert result.generation_path.is_dir()
    assert isinstance(result.maintenance_warning, ExportMaintenanceWarning)
    assert result.maintenance_warning.code == "publication_cleanup_deferred"
    assert (config.exports / "tracks.tsv").is_file()


def test_first_and_repeated_publications_keep_at_most_one_previous(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "exports"
    storage = tmp_path / ".dj-digger-publications"
    storage.mkdir()
    (storage / "previous-stale").mkdir()
    (storage / "generation-stale").mkdir()

    def publish(value: str):
        root = tmp_path / f"stage-{value}" / "publication"
        root.mkdir(parents=True)
        path = root / "tracks.tsv"
        path.write_text(value, encoding="utf-8")
        return ExportUseCase._publish_group(destination, [PublishedFacet(path, 1)], root)

    first = publish("0")
    assert first.generation_path.is_dir()
    results = [first] + [publish(str(index)) for index in range(1, 4)]
    generations = sorted(storage.glob("generation-*"))

    assert len(generations) == 2
    assert all(result.generation_path.is_dir() for result in results[-2:])
    assert not list(storage.glob("previous-*"))


def test_regular_existing_export_is_retained_as_one_previous_generation(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "exports"
    destination.mkdir()
    (destination / "legacy.txt").write_text("legacy", encoding="utf-8")
    root = tmp_path / "stage" / "publication"
    root.mkdir(parents=True)
    path = root / "tracks.tsv"
    path.write_text("new", encoding="utf-8")

    result = ExportUseCase._publish_group(destination, [PublishedFacet(path, 1)], root)
    previous = [
        candidate
        for candidate in (tmp_path / ".dj-digger-publications").glob("generation-*")
        if candidate.resolve() != result.generation_path.resolve()
    ]

    assert destination.is_symlink()
    assert len(previous) == 1
    assert (previous[0] / "legacy.txt").read_text(encoding="utf-8") == "legacy"


def test_symlink_unavailable_leaves_existing_export_directory_intact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    destination = tmp_path / "exports"
    destination.mkdir()
    marker = destination / "legacy.txt"
    marker.write_text("legacy", encoding="utf-8")
    monkeypatch.setattr(
        export_module.os,
        "symlink",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("unsupported")),
    )
    root = tmp_path / "stage" / "publication"
    root.mkdir(parents=True)
    path = root / "tracks.tsv"
    path.write_text("new", encoding="utf-8")

    with pytest.raises(DependencyError, match="POSIX directory symlink"):
        ExportUseCase._publish_group(destination, [PublishedFacet(path, 1)], root)

    assert destination.is_dir()
    assert marker.read_text(encoding="utf-8") == "legacy"
    assert not (tmp_path / ".dj-digger-publications").exists()


def test_generation_path_pins_a_complete_immutable_group(tmp_path: Path) -> None:
    destination = tmp_path / "exports"

    def staged(name: str, value: str) -> tuple[Path, list[PublishedFacet]]:
        root = tmp_path / f"stage-{name}" / "publication"
        root.mkdir(parents=True)
        facets = []
        for filename in ("tracks.tsv", "library-artifacts.tsv"):
            path = root / filename
            path.write_text(f"{filename}:{value}\n", encoding="utf-8")
            facets.append(PublishedFacet(path, 1))
        return root, facets

    old_root, old_facets = staged("old", "old")
    old = ExportUseCase._publish_group(destination, old_facets, old_root)
    new_root, new_facets = staged("new", "new")
    ExportUseCase._publish_group(destination, new_facets, new_root)

    assert old.generation_path.is_dir()
    assert [
        (old.generation_path / filename).read_text(encoding="utf-8").strip()
        for filename in ("tracks.tsv", "library-artifacts.tsv")
    ] == ["tracks.tsv:old", "library-artifacts.tsv:old"]
    newest_root, newest_facets = staged("newest", "newest")
    ExportUseCase._publish_group(destination, newest_facets, newest_root)
    assert not old.generation_path.exists()


def test_symlinked_publication_storage_is_rejected_without_touching_target(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "exports"
    target = tmp_path / "external-storage"
    target.mkdir()
    external_generation = target / "generation-external"
    external_generation.mkdir()
    marker = external_generation / "marker.txt"
    marker.write_text("external", encoding="utf-8")
    storage = tmp_path / ".dj-digger-publications"
    storage.symlink_to(target, target_is_directory=True)
    root = tmp_path / "stage" / "publication"
    root.mkdir(parents=True)
    path = root / "tracks.tsv"
    path.write_text("new", encoding="utf-8")

    with pytest.raises(DependencyError, match="must be a real directory"):
        ExportUseCase._publish_group(destination, [PublishedFacet(path, 1)], root)

    assert marker.read_text(encoding="utf-8") == "external"
    assert external_generation.is_dir()


def test_group_switch_is_old_or_new_for_a_concurrent_reader(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    destination = tmp_path / "exports"

    def staged(name: str, value: str) -> tuple[Path, list[PublishedFacet]]:
        root = tmp_path / f"stage-{name}" / "publication"
        root.mkdir(parents=True)
        facets = []
        for filename in ("tracks.tsv", "library-artifacts.tsv"):
            path = root / filename
            path.write_text(f"{filename}:{value}\n", encoding="utf-8")
            facets.append(PublishedFacet(path, 1))
        return root, facets

    old_root, old_facets = staged("old", "old")
    ExportUseCase._publish_group(destination, old_facets, old_root)
    new_root, new_facets = staged("new", "new")

    swapping = threading.Event()
    release = threading.Event()
    real_replace = export_module.os.replace

    def replace(source: str | Path, target: str | Path) -> None:
        if Path(source).name.startswith(".exports-link-"):
            swapping.set()
            assert release.wait(5)
        real_replace(source, target)

    monkeypatch.setattr(export_module.os, "replace", replace)
    observed: list[tuple[str, str]] = []
    reading = threading.Event()

    def reader() -> None:
        while not reading.is_set():
            try:
                # Resolve the publication directory once: this is the group
                # read boundary exposed by the atomic directory switch.
                current = destination.resolve(strict=True)
                observed.append(
                    tuple(
                        (current / filename).read_text(encoding="utf-8").strip()
                        for filename in ("tracks.tsv", "library-artifacts.tsv")
                    )
                )
            except FileNotFoundError:
                continue

    thread = threading.Thread(target=reader)
    thread.start()
    publisher = threading.Thread(
        target=ExportUseCase._publish_group,
        args=(destination, new_facets, new_root),
    )
    publisher.start()
    assert swapping.wait(5)
    release.set()
    publisher.join(5)
    reading.set()
    thread.join(5)

    assert not publisher.is_alive()
    assert observed
    assert all(
        pair
        in {
            ("tracks.tsv:old", "library-artifacts.tsv:old"),
            ("tracks.tsv:new", "library-artifacts.tsv:new"),
        }
        for pair in observed
    )


def test_core_refresh_keeps_legacy_export_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _config(tmp_path)
    with CoreApplication(config) as core:
        monkeypatch.setattr(
            core,
            "_scan_for_refresh",
            lambda **_kwargs: [SimpleNamespace(source_id="source", succeeded=True)],
        )
        monkeypatch.setattr(core, "metadata", lambda: SimpleNamespace(status="succeeded"))
        monkeypatch.setattr(core, "analyze", lambda **_kwargs: SimpleNamespace(status="succeeded"))
        monkeypatch.setattr(core, "export", lambda: ["tracks.tsv"])

        result = core.refresh()

    assert result == {
        "event": "refresh",
        "status": "succeeded",
        "published": True,
        "scans": [{"source_id": "source", "succeeded": True}],
        "metadata": {"status": "succeeded"},
        "analysis": {"status": "succeeded"},
        "exports": ["tracks.tsv"],
    }


@pytest.mark.parametrize(
    ("export_request", "message"),
    [
        (ExportRequest(facet="unknown"), "unknown export facet"),
        (ExportRequest(type="tracks", fields="unknown"), "unknown field"),
    ],
)
def test_export_rejects_unknown_selection_at_core_boundary(
    tmp_path: Path, export_request: ExportRequest, message: str
) -> None:
    config = _config(tmp_path)

    with CoreApplication(config) as core:
        with pytest.raises(InvalidInputError, match=message):
            core.export(export_request)

    assert not config.exports.exists()
