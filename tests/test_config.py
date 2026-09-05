from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from dj_digger.config import DspConfig, WorkspaceConfig

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_multiple_sources_with_stable_ids() -> None:
    config = WorkspaceConfig.load(FIXTURES / "dj-digger.toml")

    assert [source.id for source in config.sources] == ["djing", "music"]
    assert config.sources[0].set_eligible is True
    assert config.sources[1].analyze is False


def test_workspace_config_uses_mastering_defaults() -> None:
    config = WorkspaceConfig.load(FIXTURES / "dj-digger.toml")

    assert config.mastering.dj_target_lufs == -9.0
    assert config.mastering.dj_target_true_peak_dbtp == -1.0
    assert config.mastering.variant_thresholds.integrated_lufs_db == 1.5
    assert config.mastering.variant_thresholds.active_loudness_db == 1.5
    assert config.mastering.variant_thresholds.plr_db == 2.0
    assert config.mastering.review_thresholds.gain_deficit_db == 1.5


def test_workspace_config_reads_explicit_curation_limits() -> None:
    config = WorkspaceConfig.load(Path("config/dj-digger.example.toml"))

    assert config.curation.base_url == "https://api.openai.com/v1"
    assert config.curation.model == "gpt-5-mini"
    assert config.curation.api_key_env == "OPENAI_API_KEY"
    assert config.curation.max_turns == 8
    assert config.curation.max_output_tracks == 20


def test_workspace_config_rejects_cleartext_curation_secret(tmp_path: Path) -> None:
    path = tmp_path / "cleartext-secret.toml"
    source = (FIXTURES / "dj-digger.toml").read_text()
    secret = "must-not-appear-in-errors"
    path.write_text(source + f'\n[curation]\napi_key = "{secret}"\n')

    with pytest.raises(ValueError) as captured:
        WorkspaceConfig.load(path)

    assert "environment variable" in str(captured.value)
    assert secret not in str(captured.value)


def test_workspace_config_reads_mastering_thresholds(tmp_path: Path) -> None:
    path = tmp_path / "mastering.toml"
    path.write_text(
        (FIXTURES / "dj-digger.toml").read_text(encoding="utf-8")
        + "\n[mastering]\ndj_target_lufs = -10\n"
        + "[mastering.variant_thresholds]\nplr_db = 3\n",
        encoding="utf-8",
    )

    config = WorkspaceConfig.load(path)

    assert config.mastering.dj_target_lufs == -10.0
    assert config.mastering.variant_thresholds.plr_db == 3.0


@pytest.mark.parametrize("value", [float("inf"), float("nan"), "-9"])
def test_mastering_targets_must_be_finite_numbers(tmp_path: Path, value: object) -> None:
    path = tmp_path / "invalid-mastering.toml"
    serialized = repr(value) if not isinstance(value, str) else f'"{value}"'
    path.write_text(
        (FIXTURES / "dj-digger.toml").read_text(encoding="utf-8")
        + f"\n[mastering]\ndj_target_lufs = {serialized}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="mastering.dj_target_lufs"):
        WorkspaceConfig.load(path)


def test_resolves_workspace_and_source_paths_from_config_directory() -> None:
    config = WorkspaceConfig.load(FIXTURES / "dj-digger.toml")

    assert config.database == (FIXTURES / "workspace" / "dj-digger.sqlite").resolve()
    assert config.exports == (FIXTURES / "workspace" / "exports").resolve()
    assert config.sources[0].path == (FIXTURES / "library" / "djing").resolve()


def test_shipped_example_uses_compose_writable_workspace_paths() -> None:
    config = WorkspaceConfig.load(Path("config/dj-digger.example.toml"))

    assert config.database == Path("/workspace/dj-digger.sqlite")
    assert config.exports == Path("/workspace/exports")


@pytest.mark.parametrize("fixture_name", ["blank-source-id.toml", "duplicate-source-id.toml"])
def test_rejects_blank_or_duplicate_source_ids(fixture_name: str) -> None:
    with pytest.raises(ValueError, match="source id"):
        WorkspaceConfig.load(FIXTURES / fixture_name)


@pytest.mark.parametrize(
    "fixture_name", ["database-inside-source.toml", "exports-inside-source.toml"]
)
def test_rejects_workspace_state_inside_a_source_root(fixture_name: str) -> None:
    with pytest.raises(ValueError, match="must not be inside source"):
        WorkspaceConfig.load(FIXTURES / fixture_name)


def test_configuration_records_are_immutable() -> None:
    config = WorkspaceConfig.load(FIXTURES / "dj-digger.toml")

    with pytest.raises(FrozenInstanceError):
        config.sources[0].enabled = False


def test_loads_versioned_dsp_configuration_for_active_analysis() -> None:
    config = WorkspaceConfig.load(Path("config/dj-digger.example.toml"))

    assert config.dsp.version == 1
    assert config.dsp.sample_rate == 48_000
    assert config.dsp.channels == 1
    assert config.dsp.fft_window_size == 4096
    assert config.dsp.semantic_min_confidence == 0.80
    assert config.dsp.bands["sub"] == (20.0, 60.0)


def test_dsp_configuration_rejects_missing_required_sections(tmp_path: Path) -> None:
    path = tmp_path / "invalid-analysis.toml"
    path.write_text("[audio]\nsample_rate = 48000\n", encoding="utf-8")

    with pytest.raises(ValueError, match="DSP configuration requires"):
        DspConfig.load(path)


def test_dsp_config_hash_changes_when_a_canonical_value_changes(tmp_path: Path) -> None:
    source = Path("config/analysis.toml").read_text(encoding="utf-8")
    changed = tmp_path / "analysis.toml"
    changed.write_text(
        source.replace("min_confidence = 0.80", "min_confidence = 0.81"), encoding="utf-8"
    )

    assert DspConfig.load(changed).config_hash != DspConfig.canonical().config_hash


def test_canonical_dsp_config_requires_packaged_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    class MissingResource:
        def joinpath(self, *_parts: str) -> "MissingResource":
            return self

        def is_file(self) -> bool:
            return False

    monkeypatch.setattr("dj_digger.config.files", lambda _package: MissingResource())

    with pytest.raises(FileNotFoundError, match="dj_digger/analysis.toml"):
        DspConfig.canonical()
