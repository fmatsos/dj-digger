"""Typed publication contracts for catalog exports."""

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import dj_digger.core.application.export as export_module
from dj_digger.core.application import (
    CoreApplication,
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
        with pytest.raises(OSError, match="link failed"):
            core.export(ExportRequest(facet="tracks"))

    assert not list(tmp_path.glob(".exports-*"))


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
