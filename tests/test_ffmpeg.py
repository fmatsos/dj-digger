from pathlib import Path

import pytest

from dj_digger.analysis.audio import TechnicalAudioMetadata
from dj_digger.analysis.ffmpeg import FFmpegProbe
from dj_digger.catalog.database import Database
from dj_digger.catalog.models import Track
from dj_digger.catalog.repositories import TechnicalAudioMetadataRepository


def test_ffmpeg_normalizes_facts_and_uses_read_only_argv(monkeypatch) -> None:
    calls: list[list[str]] = []

    def run(argv: list[str], **_kwargs: object) -> object:
        calls.append(argv)
        if argv[0] == "ffprobe":
            return type(
                "Result",
                (),
                {
                    "stdout": """{
                        \"streams\": [
                            {\"codec_type\": \"video\"},
                            {\"codec_type\": \"audio\", \"sample_rate\": \"48000\",
                             \"channels\": 2, \"codec_name\": \"flac\",
                             \"bit_rate\": \"1000000\", \"bits_per_raw_sample\": \"24\"}
                        ],
                        \"format\": {\"duration\": \"123.45\", \"format_name\": \"flac\"}
                    }""",
                    "stderr": "",
                },
            )()
        return type(
            "Result", (), {"stdout": "", "stderr": "I: -13.2 LUFS\nPeak: -0.4 dBFS\nLRA: 6.9 LU\n"}
        )()

    monkeypatch.setattr("dj_digger.analysis.ffmpeg.subprocess.run", run)
    path = Path("odd;name\\n.flac")

    metadata = FFmpegProbe().probe(path)

    assert metadata.duration_seconds == 123.45
    assert metadata.sample_rate == 48000
    assert metadata.channels == 2
    assert metadata.codec == "flac"
    assert metadata.container == "flac"
    assert metadata.bitrate == 1_000_000
    assert metadata.lossless is True
    assert metadata.loudness_lufs == -13.2
    assert metadata.true_peak_db == -0.4
    assert metadata.dynamic_range == 6.9
    assert calls == [
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        [
            "ffmpeg", "-v", "info", "-i", str(path), "-filter:a", "ebur128=peak=true",
            "-f", "null", "-",
        ],
    ]


def test_ffmpeg_tolerates_malformed_optional_facts_and_measurements(monkeypatch) -> None:
    def run(argv: list[str], **_kwargs: object) -> object:
        if argv[0] == "ffprobe":
            return type(
                "Result",
                (),
                {
                    "stdout": '{"streams":[{"codec_type":"audio","sample_rate":"bad",'
                    '"channels":"bad","codec_name":4}],"format":{"duration":"bad",'
                    '"format_name":false,"bit_rate":"bad"}}',
                    "stderr": "",
                },
            )()
        return type("Result", (), {"stdout": "", "stderr": "no measurements"})()

    monkeypatch.setattr("dj_digger.analysis.ffmpeg.subprocess.run", run)

    metadata = FFmpegProbe().probe(Path("track.mp3"))

    assert metadata.duration_seconds is None
    assert metadata.sample_rate is None
    assert metadata.channels is None
    assert metadata.codec is None
    assert metadata.container is None
    assert metadata.bitrate is None
    assert metadata.lossless is None
    assert metadata.loudness_lufs is None
    assert metadata.true_peak_db is None
    assert metadata.dynamic_range is None


def test_technical_audio_metadata_repository_upserts_current_probe(tmp_path: Path) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    database.execute(
        "INSERT INTO library_sources "
        "(source_id, root_path, set_eligible, analyze, enabled, created_at, updated_at) "
        "VALUES ('source', '/music', 1, 1, 1, 'now', 'now')"
    )
    database.execute(
        "INSERT INTO scan_runs (source_id, started_at, status, scanner_version) "
        "VALUES ('source', 'now', 'running', 'test')"
    )
    track = Track(
        id=1, source_id="source", relative_path="track.flac", filename="track.flac",
        extension=".flac", size_bytes=4, mtime_ns=5, presence_status="present"
    )
    database.execute(
        "INSERT INTO tracks (id, source_id, relative_path, filename, extension, size_bytes, "
        "mtime_ns, presence_status, discovered_at, last_seen_at, created_scan_id, "
        "last_seen_scan_id) VALUES (1, 'source', 'track.flac', 'track.flac', '.flac', 4, 5, "
        "'present', 'now', 'now', 1, 1)"
    )
    database.commit()

    repository = TechnicalAudioMetadataRepository(database)
    with database.transaction():
        repository.upsert(
            track, TechnicalAudioMetadata(sample_rate=48_000, lossless=True), "ffmpeg-test"
        )
        repository.upsert(
            track, TechnicalAudioMetadata(sample_rate=44_100, lossless=False), "ffmpeg-test-2"
        )

    assert database.execute(
        "SELECT sample_rate, lossless, probe_version FROM technical_audio_metadata "
        "WHERE track_id = 1"
    ).fetchone() == (44_100, 0, "ffmpeg-test-2")


def test_technical_audio_metadata_upsert_rolls_back_with_its_caller_transaction(
    tmp_path: Path,
) -> None:
    database = Database.open(tmp_path / "catalog.sqlite")
    database.migrate()
    database.execute(
        "INSERT INTO library_sources "
        "(source_id, root_path, set_eligible, analyze, enabled, created_at, updated_at) "
        "VALUES ('source', '/music', 1, 1, 1, 'now', 'now')"
    )
    database.execute(
        "INSERT INTO scan_runs (source_id, started_at, status, scanner_version) "
        "VALUES ('source', 'now', 'running', 'test')"
    )
    database.execute(
        "INSERT INTO tracks (id, source_id, relative_path, filename, extension, size_bytes, "
        "mtime_ns, presence_status, discovered_at, last_seen_at, created_scan_id, "
        "last_seen_scan_id) VALUES (1, 'source', 'track.flac', 'track.flac', '.flac', 4, 5, "
        "'present', 'now', 'now', 1, 1)"
    )
    database.commit()
    track = Track(
        id=1,
        source_id="source",
        relative_path="track.flac",
        filename="track.flac",
        extension=".flac",
        size_bytes=4,
        mtime_ns=5,
        presence_status="present",
    )

    with pytest.raises(RuntimeError, match="abort technical metadata"):
        with database.transaction():
            TechnicalAudioMetadataRepository(database).upsert(
                track,
                TechnicalAudioMetadata(sample_rate=48_000, lossless=True),
                "ffmpeg-test",
            )
            raise RuntimeError("abort technical metadata")

    assert database.scalar("SELECT COUNT(*) FROM technical_audio_metadata") == 0
