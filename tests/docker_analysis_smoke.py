"""Run the complete analysis stack inside the built Docker image."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from dj_digger.analysis.extractor import AudioDecoder, CompositeAudioExtractor
from dj_digger.analysis.ffmpeg import FFmpegProbe
from dj_digger.analysis.rhythm import RhythmAnalyzer


def main() -> None:
    audio = Path(sys.argv[1])
    root = Path(sys.argv[2])
    decoder = AudioDecoder()
    probe = FFmpegProbe()
    rhythm = RhythmAnalyzer()
    # Exercise each concrete dependency before the composite call as an explicit smoke gate.
    samples = decoder.decode(audio)
    probe.probe(audio)
    rhythm.analyze(samples.astype("float64"), 48_000)
    result = CompositeAudioExtractor(decoder=decoder, probe=probe, rhythm=rhythm).extract(
        audio, relative_path="smoke/tone.wav"
    )
    for name, document in (
        ("dj-analysis.schema.json", result.payload),
        ("dj-sections.schema.json", result.sections),
    ):
        schema = json.loads((root / "schemas" / name).read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(document)
    print(json.dumps({"status": result.status, "sections": len(result.sections["sections"])}))


if __name__ == "__main__":
    main()
