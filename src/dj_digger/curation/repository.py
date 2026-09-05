"""Transactional persistence for durable curation creations."""

import json
from datetime import UTC, datetime
from typing import cast

from dj_digger.catalog.database import Database
from dj_digger.curation.models import (
    CreateCurationDraft,
    CurationCreation,
    CurationKind,
    CurationStatus,
    CurationTrack,
)


class CurationRepository:
    """Create and validate normalized curation records."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def create_draft(self, draft: CreateCurationDraft) -> CurationCreation:
        """Persist a draft, report, and tracks; config is caller-sanitized and non-secret."""
        now = _now()
        with self._database.transaction():
            self._database.execute(
                """
                INSERT INTO curation_creations (
                    id, name, kind, user_prompt, report_markdown, status,
                    created_at, updated_at, validated_at, model_config_json
                ) VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, NULL, ?)
                """,
                (
                    draft.id,
                    draft.name,
                    draft.kind,
                    draft.user_prompt,
                    draft.report_markdown,
                    now,
                    now,
                    json.dumps(draft.model_config_data, sort_keys=True, separators=(",", ":")),
                ),
            )
            for track in draft.tracks:
                self._database.execute(
                    """
                    INSERT INTO curation_creation_tracks (creation_id, track_id, position)
                    VALUES (?, ?, ?)
                    """,
                    (draft.id, track.track_id, track.position),
                )
        creation = self.get(draft.id)
        if creation is None:
            raise RuntimeError("created curation could not be read")
        return creation

    def validate(self, creation_id: str) -> CurationCreation:
        """Idempotently validate a draft; validated creations never return to draft."""
        now = _now()
        with self._database.transaction():
            cursor = self._database.execute(
                """
                UPDATE curation_creations
                SET status = 'validated', updated_at = ?, validated_at = ?
                WHERE id = ? AND status = 'draft'
                """,
                (now, now, creation_id),
            )
            if cursor.rowcount == 0:
                status = self._database.scalar(
                    "SELECT status FROM curation_creations WHERE id = ?", (creation_id,)
                )
                if status is None:
                    raise ValueError(f"unknown curation creation: {creation_id}")
                if status != "validated":
                    raise RuntimeError(f"unsupported curation status: {status}")
        creation = self.get(creation_id)
        if creation is None:
            raise RuntimeError("validated curation could not be read")
        return creation

    def get(self, creation_id: str) -> CurationCreation | None:
        """Return one creation with tracks ordered by their persisted position."""
        row = self._database.execute(
            """
            SELECT id, name, kind, user_prompt, report_markdown, status,
                   created_at, updated_at, validated_at, model_config_json
            FROM curation_creations WHERE id = ?
            """,
            (creation_id,),
        ).fetchone()
        if row is None:
            return None
        tracks = tuple(
            CurationTrack(track_id=int(track_id), position=int(position))
            for track_id, position in self._database.execute(
                """
                SELECT track_id, position FROM curation_creation_tracks
                WHERE creation_id = ? ORDER BY position
                """,
                (creation_id,),
            )
        )
        return CurationCreation(
            id=str(row[0]),
            name=str(row[1]),
            kind=cast(CurationKind, str(row[2])),
            user_prompt=str(row[3]),
            report_markdown=str(row[4]),
            status=cast(CurationStatus, str(row[5])),
            created_at=str(row[6]),
            updated_at=str(row[7]),
            validated_at=None if row[8] is None else str(row[8]),
            model_config_data=json.loads(str(row[9])),
            tracks=tracks,
        )


def _now() -> str:
    return datetime.now(UTC).isoformat()
