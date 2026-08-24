"""Select catalog tracks that require audio analysis."""

from dj_digger.analysis.config import AnalysisIdentity
from dj_digger.catalog.models import Track
from dj_digger.catalog.repositories import TrackRepository


class AnalysisEligibility:
    """Catalog-backed eligibility query for a specific analysis identity."""

    def __init__(self, tracks: TrackRepository) -> None:
        self._tracks = tracks

    def pending(
        self,
        identity: AnalysisIdentity,
        source_id: str | None = None,
        path_prefix: str | None = None,
    ) -> list[Track]:
        """Return present, analyzable tracks without an exactly reusable result."""
        return self._tracks.pending_analysis(
            schema_version=identity.schema_version,
            analyzer_version=identity.analyzer_version,
            config_hash=identity.config_hash,
            source_id=source_id,
            path_prefix=path_prefix,
        )
