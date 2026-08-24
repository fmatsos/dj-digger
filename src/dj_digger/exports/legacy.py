"""Compatibility export facets projected exclusively from the catalog."""

import csv
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from dj_digger.catalog.database import Database
from dj_digger.catalog.repositories import (
    ArtifactRepository,
    LegacyExportRepository,
    SourceRepository,
)
from dj_digger.exports.atomic import publish_atomic
from dj_digger.exports.tracks import PublishedFacet

METADATA_COLUMNS = (
    "SourceFile",
    "FileName",
    "Directory",
    "FileType",
    "FileSize",
    "Duration",
    "AudioBitrate",
    "SampleRate",
    "Title",
    "Artist",
    "AlbumArtist",
    "Album",
    "Track",
    "DiscNumber",
    "Genre",
    "Date",
    "Year",
    "Composer",
    "Comment",
    "BPM",
    "InitialKey",
    "Grouping",
)


class LegacyExporter:
    def __init__(self, database: Database) -> None:
        self._database = database

    def export(self, destination: Path) -> list[PublishedFacet]:
        roots = SourceRepository(self._database).roots()
        for source_id in roots:
            _validate_source_id(source_id)
        repository = LegacyExportRepository(self._database)
        facets: list[PublishedFacet] = []
        produced: list[str] = []
        for source_id, root in roots.items():
            tracks = repository.tracks(source_id)
            directories = repository.directories(source_id)
            facets.extend(self._source_facets(destination, source_id, root, tracks, directories))
            produced.extend(facet.path.name for facet in facets[-6:])
        artifacts = ArtifactRepository(self._database).export_rows()
        facets.extend(self._global_facets(destination, roots, artifacts, repository, produced))
        return facets

    def _source_facets(
        self,
        destination: Path,
        source: str,
        root: Path,
        tracks: list[tuple[Any, ...]],
        directories: list[str],
    ) -> list[PublishedFacet]:
        facets: list[PublishedFacet] = []
        files = destination / f"{source}-files.tsv"

        def write_files(path: Path) -> None:
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
                writer.writerow(["path", "filename", "extension", "size_bytes", "mtime"])
                for row in tracks:
                    writer.writerow(
                        [row[0], row[1], Path(str(row[0])).suffix.lower(), row[3], _time(row[4])]
                    )

        publish_atomic(files, write_files)
        facets.append(PublishedFacet(files, len(tracks)))
        metadata = destination / f"{source}-metadata.csv"

        def write_metadata(path: Path) -> None:
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(METADATA_COLUMNS)
                for row in tracks:
                    relative = str(row[0])
                    parent = str(Path(relative).parent)
                    writer.writerow(
                        [
                            relative,
                            row[1],
                            "." if parent == "." else parent,
                            Path(relative).suffix[1:].upper(),
                            row[3],
                            row[19],
                            row[20],
                            row[21],
                            *row[5:19],
                        ]
                    )

        publish_atomic(metadata, write_metadata)
        facets.append(PublishedFacet(metadata, len(tracks)))
        tree = [directory for directory in directories if len(Path(directory).parts) <= 3]
        for suffix, lines in (("directories.txt", directories), ("tree-depth-3.txt", tree)):
            target = destination / f"{source}-{suffix}"
            _publish_text(target, "".join(f"{value}\n" for value in lines))
            facets.append(PublishedFacet(target, len(lines)))
        counts: Counter[str] = Counter()
        for row in tracks:
            parts = Path(str(row[0])).parts
            if len(parts) > 1:
                counts[parts[0]] += 1
                if len(parts) > 2:
                    counts["/".join(parts[:2])] += 1
        stat_rows = [(1 if "/" not in path else 2, path, count) for path, count in counts.items()]
        stat_rows.sort(key=lambda item: (-item[2], item[1]))
        stats = destination / f"{source}-directory-stats.tsv"

        def write_stats(path: Path) -> None:
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
                writer.writerow(["level", "path", "tracks"])
                writer.writerows(stat_rows)

        publish_atomic(stats, write_stats)
        facets.append(PublishedFacet(stats, len(stat_rows)))
        extensions = Counter(Path(str(row[0])).suffix.lower() for row in tracks)
        total_bytes = sum(int(row[3]) for row in tracks)
        summary_lines = [
            f"Root: {root}",
            f"Audio files: {len(tracks)}",
            f"Total bytes: {total_bytes}",
            f"Total GiB: {total_bytes / 1024**3:.2f}",
            "",
            "Files by extension:",
        ]
        summary_lines.extend(
            f"{extension}\t{count}"
            for extension, count in sorted(extensions.items(), key=lambda item: (-item[1], item[0]))
        )
        summary = destination / f"{source}-summary.txt"
        _publish_text(summary, "\n".join(summary_lines) + "\n")
        facets.append(PublishedFacet(summary, len(tracks)))
        return facets

    def _global_facets(
        self,
        destination: Path,
        roots: dict[str, Path],
        artifacts: list[tuple[Any, ...]],
        repository: LegacyExportRepository,
        produced: list[str],
    ) -> list[PublishedFacet]:
        facets: list[PublishedFacet] = []

        def artifact_tsv(name: str, rows: list[tuple[Any, ...]]) -> PublishedFacet:
            target = destination / name

            def write(path: Path) -> None:
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
                    writer.writerow(["root", "path", "size_bytes", "mtime"])
                    writer.writerows(
                        (source, rel, size, _time(mtime, space=True))
                        for source, rel, _kind, size, mtime, *_ in rows
                    )

            publish_atomic(target, write)
            return PublishedFacet(target, len(rows))

        facets.append(artifact_tsv("dj-metadata-files.tsv", artifacts))
        facets.append(
            artifact_tsv(
                "traktor-files.tsv",
                [row for row in artifacts if row[2] in {"traktor_nml", "traktor_tsi"}],
            )
        )
        serato = sorted(
            {
                str(roots[source] / directory)
                for source in roots
                for directory in repository.directories(source)
                if Path(directory).name.lower() == "_serato_"
            }
        )
        target = destination / "serato-directories.txt"
        _publish_text(target, "".join(f"{line}\n" for line in serato))
        facets.append(PublishedFacet(target, len(serato)))
        names = sorted(
            [
                "library-artifacts.tsv",
                *produced,
                *(facet.path.name for facet in facets),
                "README.txt",
            ]
        )
        readme = destination / "README.txt"
        _publish_text(
            readme,
            "Sources: "
            + ", ".join(roots)
            + "\nFacets:\n"
            + "".join(f"- {name}\n" for name in names),
        )
        facets.append(PublishedFacet(readme, len(names)))
        return facets


def _time(value: Any, *, space: bool = False) -> str:
    timestamp = datetime.fromtimestamp(int(value) // 1_000_000_000)
    return (
        timestamp.strftime("%Y-%m-%d %H:%M:%S")
        if space
        else timestamp.isoformat(timespec="seconds")
    )


def _publish_text(destination: Path, content: str) -> None:
    def write(path: Path) -> None:
        path.write_text(content, encoding="utf-8")

    publish_atomic(destination, write)


def _validate_source_id(source_id: str) -> None:
    if source_id in {".", ".."} or "/" in source_id or "\\" in source_id:
        raise ValueError(f"source id is not a safe filename: {source_id!r}")
