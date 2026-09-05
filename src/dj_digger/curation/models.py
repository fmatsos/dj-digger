"""Strict, bounded DTOs exposed by the curation catalog."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

QualityStatus = Literal["unique", "verified_best", "best_effort", "unverified_unfingerprinted"]
AnalysisStatus = Literal["ok", "failed", "missing"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CandidateRef(_Model):
    source_id: str = Field(min_length=1)
    track_id: int = Field(gt=0)


class SearchFilters(_Model):
    query: str | None = Field(default=None, max_length=200)
    source_ids: tuple[str, ...] = Field(default=(), max_length=20)
    genres: tuple[str, ...] = Field(default=(), max_length=20)
    year_min: int | None = None
    year_max: int | None = None
    bpm_min: float | None = Field(default=None, gt=0)
    bpm_max: float | None = Field(default=None, gt=0)
    keys: tuple[str, ...] = Field(default=(), max_length=20)
    duration_min_seconds: float | None = Field(default=None, ge=0)
    duration_max_seconds: float | None = Field(default=None, gt=0)
    lossless: bool | None = None
    analysis_required: bool | None = None

    @model_validator(mode="after")
    def validate_ranges(self) -> SearchFilters:
        pairs = (
            (self.year_min, self.year_max, "year"),
            (self.bpm_min, self.bpm_max, "bpm"),
            (self.duration_min_seconds, self.duration_max_seconds, "duration"),
        )
        for lower, upper, name in pairs:
            if lower is not None and upper is not None and lower > upper:
                raise ValueError(f"{name} minimum cannot exceed maximum")
        if any(not value.strip() for value in self.source_ids + self.genres + self.keys):
            raise ValueError("filter values must not be blank")
        return self


class SourceSummary(_Model):
    source_id: str
    last_successful_scan_at: str | None = None


class FacetValue(_Model):
    value: str
    count: int = Field(ge=0)


class FacetSummary(_Model):
    values: tuple[FacetValue, ...]
    other_count: int = Field(ge=0)


class AnalysisRunSummary(_Model):
    status: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    eligible: int = Field(ge=0)
    analyzed: int = Field(ge=0)
    reused: int = Field(ge=0)
    failed: int = Field(ge=0)


class LibraryOverviewV1(_Model):
    contract_version: Literal["curation/v1"] = "curation/v1"
    catalog_version: int
    available_tracks: int = Field(ge=0)
    candidates: int = Field(ge=0)
    analysis_ok: int = Field(ge=0)
    analysis_failed: int = Field(ge=0)
    analysis_missing: int = Field(ge=0)
    fingerprinted: int = Field(ge=0)
    quality_status_counts: dict[str, int]
    latest_analysis: AnalysisRunSummary
    sources: tuple[SourceSummary, ...]
    facets: dict[str, FacetSummary]


class CandidateIdentity(_Model):
    source_id: str
    track_id: int = Field(gt=0)
    path: str = Field(min_length=1)


class CandidateSummary(_Model):
    identity: CandidateIdentity
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    genre: str | None = None
    year: str | None = None
    duration_seconds: float | None = None
    bpm: float | None = None
    key: str | None = None
    lossless: bool | None = None
    analysis_status: AnalysisStatus
    analysis_confidence: float | None = None
    quality_status: QualityStatus
    duplicate_members: int = Field(ge=1)
    matched_on_suppressed_variant: bool = False


class CandidateSearchV1(_Model):
    contract_version: Literal["curation/v1"] = "curation/v1"
    candidates: tuple[CandidateSummary, ...]
    next_cursor: str | None = None


class DiscoveryMetadata(_Model):
    filename: str
    title: str | None = None
    artist: str | None = None
    album_artist: str | None = None
    album: str | None = None
    genre: str | None = None
    year: str | None = None
    grouping: str | None = None
    comment: str | None = None
    tag_bpm: float | None = None
    tag_initial_key: str | None = None


class AudioFormat(_Model):
    duration_seconds: float | None = None
    codec: str | None = None
    container: str | None = None
    lossless: bool | None = None
    bit_depth: int | None = None
    sample_rate: int | None = None
    bitrate: int | None = None


class AnalysisWindows(_Model):
    intro: dict[str, dict[str, object | None]]
    outro: dict[str, dict[str, object | None]]


class SectionSummary(_Model):
    index: int = Field(ge=0)
    start: float
    end: float
    facts: dict[str, object | None]
    semantic_label: str | None = None
    semantic_confidence: float | None = None
    transition_suitability_in: float | None = None
    transition_suitability_out: float | None = None


class AnalysisDetails(_Model):
    status: AnalysisStatus
    confidence: float | None = None
    bpm: float | None = None
    bpm_confidence: float | None = None
    beat_stability: float | None = None
    key: str | None = None
    key_confidence: float | None = None
    energy: dict[str, float | None]
    loudness_lufs: float | None = None
    true_peak_db: float | None = None
    dynamic_range: float | None = None
    density: dict[str, float | None]
    spectral_centroid: float | None = None


class MasteringSummary(_Model):
    integrated_lufs: float | None = None
    loudness_range_lu: float | None = None
    true_peak_dbtp: float | None = None
    peak_to_loudness_ratio_db: float | None = None
    required_gain_db: float | None = None
    available_gain_db: float | None = None
    gain_deficit_db: float | None = None


class CandidateDetails(_Model):
    identity: CandidateIdentity
    discovery: DiscoveryMetadata
    format: AudioFormat
    quality_status: QualityStatus
    duplicate_members: int = Field(ge=1)
    analysis: AnalysisDetails
    windows: AnalysisWindows
    sections: tuple[SectionSummary, ...]
    mastering: MasteringSummary


class CandidateDetailsV1(_Model):
    contract_version: Literal["curation/v1"] = "curation/v1"
    candidates: tuple[CandidateDetails, ...]
