from pathlib import Path
from types import SimpleNamespace

from dj_digger.core.application.refresh import RefreshRequest, RefreshUseCase
from dj_digger.core.application.scan import ScanRunResult, ScanSourceResult
from dj_digger.core.config import LibrarySourceConfig, WorkspaceConfig


def _config(tmp_path: Path) -> WorkspaceConfig:
    source = tmp_path / "library"
    source.mkdir()
    return WorkspaceConfig(
        database=tmp_path / "catalog.sqlite",
        exports=tmp_path / "exports",
        sources=(LibrarySourceConfig("required", source, True, True),),
    )


def test_refresh_stops_before_publication_after_required_scan_failure(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[str] = []

    class Scan:
        def __init__(self, *_args):
            pass

        def execute(self, _request):
            calls.append("scan")
            return ScanRunResult((ScanSourceResult("required", False, None, "missing"),))

    class Unexpected:
        def __init__(self, *_args):
            calls.append("unexpected")

        def execute(self, *_args, **_kwargs):
            raise AssertionError("refresh published after required scan failure")

    monkeypatch.setattr("dj_digger.core.application.refresh.ScanUseCase", Scan)
    monkeypatch.setattr("dj_digger.core.application.refresh.MetadataUseCase", Unexpected)
    monkeypatch.setattr("dj_digger.core.application.refresh.AnalyzeUseCase", Unexpected)
    monkeypatch.setattr("dj_digger.core.application.refresh.ExportUseCase", Unexpected)

    result = RefreshUseCase(object(), _config(tmp_path), object(), object()).execute()

    assert result.status == "failed"
    assert result.published is False
    assert calls == ["scan"]


def test_refresh_keeps_partial_non_required_scan_outcome_and_publishes(
    monkeypatch, tmp_path: Path
) -> None:
    config = WorkspaceConfig(
        database=tmp_path / "catalog.sqlite",
        exports=tmp_path / "exports",
        sources=(
            LibrarySourceConfig("required", tmp_path / "required", True, True),
            LibrarySourceConfig("optional", tmp_path / "optional", False, True),
        ),
    )

    class Scan:
        def __init__(self, *_args):
            pass

        def execute(self, _request):
            return ScanRunResult(
                (
                    ScanSourceResult("required", True, 1),
                    ScanSourceResult("optional", False, 2, "unavailable"),
                )
            )

    class Metadata:
        def __init__(self, *_args):
            pass

        def execute(self, _request):
            return SimpleNamespace(status="succeeded")

    class Analyze:
        def __init__(self, *_args):
            pass

        def execute(self, _request, **_kwargs):
            return SimpleNamespace(status="succeeded")

    class Export:
        def __init__(self, *_args):
            pass

        def execute(self, _request):
            return ["tracks.tsv"]

    monkeypatch.setattr("dj_digger.core.application.refresh.ScanUseCase", Scan)
    monkeypatch.setattr("dj_digger.core.application.refresh.MetadataUseCase", Metadata)
    monkeypatch.setattr("dj_digger.core.application.refresh.AnalyzeUseCase", Analyze)
    monkeypatch.setattr("dj_digger.core.application.refresh.ExportUseCase", Export)

    result = RefreshUseCase(object(), config, object(), object()).execute(RefreshRequest())

    assert result.status == "partial"
    assert result.published is True
    assert result.as_dict()["exports"] == ["tracks.tsv"]
