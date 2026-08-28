# Export fields

This is the complete field list accepted by `dj-digger export --fields`. Fields are grouped by the required `--type`. The order below is the schema order used by a full export; a custom selection preserves the order supplied on the command line.

## `tracks`

| Field | Description |
| --- | --- |
| `source_id` | Stable identifier of the configured library source. |
| `track_id` | Stable numeric identifier of the track in the catalog. |
| `path` | Path relative to the configured source root. |
| `absolute_path` | Resolved absolute path to the local file. |
| `filename` | File name including its extension. |
| `extension` | Lowercase file extension including the leading dot. |
| `size_bytes` | File size in bytes. |
| `mtime` | Last file modification time recorded by the catalog. |
| `set_eligible` | Whether the source permits this track to be used in generated sets. |
| `title` | Track title read from embedded metadata. |
| `artist` | Primary track artist read from embedded metadata. |
| `album_artist` | Album-level artist read from embedded metadata. |
| `album` | Album or release title read from embedded metadata. |
| `track_number` | Track number within the release. |
| `disc_number` | Disc number within a multi-disc release. |
| `genre` | Genre value read from embedded metadata. |
| `date` | Release date value as stored in embedded metadata. |
| `year` | Four-digit release year derived from metadata when available. |
| `composer` | Composer value read from embedded metadata. |
| `comment` | Free-form comment read from embedded metadata. |
| `tag_bpm` | BPM value stored in the file tags. |
| `tag_initial_key` | Initial musical key stored in the file tags. |
| `grouping` | Grouping value stored in embedded metadata. |
| `duration_seconds` | Audio duration in seconds. |
| `sample_rate` | Audio sample rate in hertz. |
| `channels` | Number of audio channels. |
| `codec` | Detected audio codec. |
| `container` | Detected media container. |
| `bitrate` | Audio bitrate in bits per second. |
| `lossless` | Whether the detected audio encoding is lossless. |
| `duplicate_group_id` | Stable fingerprint group identifier when the track has duplicates. |
| `duplicate_best_quality` | Whether this file is the selected best-quality copy in its source. |

## `artifacts`

| Field | Description |
| --- | --- |
| `source_id` | Stable identifier of the configured library source. |
| `path` | Path relative to the configured source root. |
| `absolute_path` | Resolved absolute path to the local file. |
| `artifact_type` | Detected kind of non-track library artifact. |
| `size_bytes` | File size in bytes. |
| `mtime` | Last file modification time recorded by the catalog. |
| `present` | Whether the artifact is currently present in the source. |
| `first_seen_at` | Timestamp when the artifact was first observed. |
| `last_seen_at` | Timestamp when the artifact was most recently observed. |
| `missing_since` | Timestamp when the artifact was first found missing, or empty if present. |

## `analysis`

| Field | Description |
| --- | --- |
| `source_id` | Stable identifier of the configured library source. |
| `track_id` | Stable numeric identifier of the track in the catalog. |
| `path` | Path relative to the configured source root. |
| `size_bytes` | File size in bytes. |
| `mtime` | Last file modification time recorded by the catalog. |
| `analysis_schema_version` | Version of the published audio-analysis schema. |
| `analyzer_version` | Version identifier of the analyzer that produced the result. |
| `config_hash` | SHA-256 identity of the DSP configuration used for analysis. |
| `analysis_status` | Public status of the latest analysis attempt. |
| `analysis_confidence` | Overall confidence score for the analysis result. |
| `duration_seconds` | Audio duration in seconds. |
| `sample_rate` | Audio sample rate in hertz. |
| `channels` | Number of audio channels. |
| `codec` | Detected audio codec. |
| `container` | Detected media container. |
| `lossless` | Whether the detected audio encoding is lossless. |
| `bpm` | Estimated tempo in beats per minute. |
| `bpm_confidence` | Confidence score for the BPM estimate. |
| `beat_stability` | Stability of the detected beat grid. |
| `key` | Estimated musical key. |
| `key_confidence` | Confidence score for the musical-key estimate. |
| `loudness_lufs` | Integrated loudness in LUFS. |
| `true_peak_db` | Estimated true-peak level in decibels. |
| `dynamic_range` | Measured audio dynamic range. |
| `sub_energy` | Relative energy in the sub-bass frequency band. |
| `low_energy` | Relative energy in the low-frequency band. |
| `low_mid_energy` | Relative energy in the low-mid frequency band. |
| `kick_strength` | Estimated prominence of kick-drum transients. |
| `kick_density` | Estimated density of kick-drum events. |
| `bass_density` | Estimated density of bass activity. |
| `onset_density` | Estimated density of detected note or transient onsets. |
| `spectral_centroid` | Spectral centroid, indicating the audio brightness. |
| `intro_8_available` | Whether a 8-bar opening analysis window is available. |
| `intro_8_bpm` | Estimated tempo in beats per minute in the 8-bar opening window. |
| `intro_8_beat_stability` | Stability of the detected beat grid in the 8-bar opening window. |
| `intro_8_sub_energy` | Relative sub-bass energy in the 8-bar opening window. |
| `intro_8_low_energy` | Relative low-frequency energy in the 8-bar opening window. |
| `intro_8_low_mid_energy` | Relative low-mid energy in the 8-bar opening window. |
| `intro_8_kick_strength` | Estimated kick-drum prominence in the 8-bar opening window. |
| `intro_8_kick_density` | Estimated density of kick-drum events in the 8-bar opening window. |
| `intro_8_bass_density` | Estimated density of bass activity in the 8-bar opening window. |
| `intro_8_loudness_lufs` | Integrated loudness in LUFS in the 8-bar opening window. |
| `intro_8_onset_density` | Estimated onset density in the 8-bar opening window. |
| `intro_8_spectral_centroid` | Spectral centroid or brightness in the 8-bar opening window. |
| `intro_16_available` | Whether a 16-bar opening analysis window is available. |
| `intro_16_bpm` | Estimated tempo in beats per minute in the 16-bar opening window. |
| `intro_16_beat_stability` | Stability of the detected beat grid in the 16-bar opening window. |
| `intro_16_sub_energy` | Relative sub-bass energy in the 16-bar opening window. |
| `intro_16_low_energy` | Relative low-frequency energy in the 16-bar opening window. |
| `intro_16_low_mid_energy` | Relative low-mid energy in the 16-bar opening window. |
| `intro_16_kick_strength` | Estimated kick-drum prominence in the 16-bar opening window. |
| `intro_16_kick_density` | Estimated density of kick-drum events in the 16-bar opening window. |
| `intro_16_bass_density` | Estimated density of bass activity in the 16-bar opening window. |
| `intro_16_loudness_lufs` | Integrated loudness in LUFS in the 16-bar opening window. |
| `intro_16_onset_density` | Estimated onset density in the 16-bar opening window. |
| `intro_16_spectral_centroid` | Spectral centroid or brightness in the 16-bar opening window. |
| `intro_32_available` | Whether a 32-bar opening analysis window is available. |
| `intro_32_bpm` | Estimated tempo in beats per minute in the 32-bar opening window. |
| `intro_32_beat_stability` | Stability of the detected beat grid in the 32-bar opening window. |
| `intro_32_sub_energy` | Relative sub-bass energy in the 32-bar opening window. |
| `intro_32_low_energy` | Relative low-frequency energy in the 32-bar opening window. |
| `intro_32_low_mid_energy` | Relative low-mid energy in the 32-bar opening window. |
| `intro_32_kick_strength` | Estimated kick-drum prominence in the 32-bar opening window. |
| `intro_32_kick_density` | Estimated density of kick-drum events in the 32-bar opening window. |
| `intro_32_bass_density` | Estimated density of bass activity in the 32-bar opening window. |
| `intro_32_loudness_lufs` | Integrated loudness in LUFS in the 32-bar opening window. |
| `intro_32_onset_density` | Estimated onset density in the 32-bar opening window. |
| `intro_32_spectral_centroid` | Spectral centroid or brightness in the 32-bar opening window. |
| `intro_64_available` | Whether a 64-bar opening analysis window is available. |
| `intro_64_bpm` | Estimated tempo in beats per minute in the 64-bar opening window. |
| `intro_64_beat_stability` | Stability of the detected beat grid in the 64-bar opening window. |
| `intro_64_sub_energy` | Relative sub-bass energy in the 64-bar opening window. |
| `intro_64_low_energy` | Relative low-frequency energy in the 64-bar opening window. |
| `intro_64_low_mid_energy` | Relative low-mid energy in the 64-bar opening window. |
| `intro_64_kick_strength` | Estimated kick-drum prominence in the 64-bar opening window. |
| `intro_64_kick_density` | Estimated density of kick-drum events in the 64-bar opening window. |
| `intro_64_bass_density` | Estimated density of bass activity in the 64-bar opening window. |
| `intro_64_loudness_lufs` | Integrated loudness in LUFS in the 64-bar opening window. |
| `intro_64_onset_density` | Estimated onset density in the 64-bar opening window. |
| `intro_64_spectral_centroid` | Spectral centroid or brightness in the 64-bar opening window. |
| `outro_8_available` | Whether a 8-bar closing analysis window is available. |
| `outro_8_bpm` | Estimated tempo in beats per minute in the 8-bar closing window. |
| `outro_8_beat_stability` | Stability of the detected beat grid in the 8-bar closing window. |
| `outro_8_sub_energy` | Relative sub-bass energy in the 8-bar closing window. |
| `outro_8_low_energy` | Relative low-frequency energy in the 8-bar closing window. |
| `outro_8_low_mid_energy` | Relative low-mid energy in the 8-bar closing window. |
| `outro_8_kick_strength` | Estimated kick-drum prominence in the 8-bar closing window. |
| `outro_8_kick_density` | Estimated density of kick-drum events in the 8-bar closing window. |
| `outro_8_bass_density` | Estimated density of bass activity in the 8-bar closing window. |
| `outro_8_loudness_lufs` | Integrated loudness in LUFS in the 8-bar closing window. |
| `outro_8_onset_density` | Estimated onset density in the 8-bar closing window. |
| `outro_8_spectral_centroid` | Spectral centroid or brightness in the 8-bar closing window. |
| `outro_16_available` | Whether a 16-bar closing analysis window is available. |
| `outro_16_bpm` | Estimated tempo in beats per minute in the 16-bar closing window. |
| `outro_16_beat_stability` | Stability of the detected beat grid in the 16-bar closing window. |
| `outro_16_sub_energy` | Relative sub-bass energy in the 16-bar closing window. |
| `outro_16_low_energy` | Relative low-frequency energy in the 16-bar closing window. |
| `outro_16_low_mid_energy` | Relative low-mid energy in the 16-bar closing window. |
| `outro_16_kick_strength` | Estimated kick-drum prominence in the 16-bar closing window. |
| `outro_16_kick_density` | Estimated density of kick-drum events in the 16-bar closing window. |
| `outro_16_bass_density` | Estimated density of bass activity in the 16-bar closing window. |
| `outro_16_loudness_lufs` | Integrated loudness in LUFS in the 16-bar closing window. |
| `outro_16_onset_density` | Estimated onset density in the 16-bar closing window. |
| `outro_16_spectral_centroid` | Spectral centroid or brightness in the 16-bar closing window. |
| `outro_32_available` | Whether a 32-bar closing analysis window is available. |
| `outro_32_bpm` | Estimated tempo in beats per minute in the 32-bar closing window. |
| `outro_32_beat_stability` | Stability of the detected beat grid in the 32-bar closing window. |
| `outro_32_sub_energy` | Relative sub-bass energy in the 32-bar closing window. |
| `outro_32_low_energy` | Relative low-frequency energy in the 32-bar closing window. |
| `outro_32_low_mid_energy` | Relative low-mid energy in the 32-bar closing window. |
| `outro_32_kick_strength` | Estimated kick-drum prominence in the 32-bar closing window. |
| `outro_32_kick_density` | Estimated density of kick-drum events in the 32-bar closing window. |
| `outro_32_bass_density` | Estimated density of bass activity in the 32-bar closing window. |
| `outro_32_loudness_lufs` | Integrated loudness in LUFS in the 32-bar closing window. |
| `outro_32_onset_density` | Estimated onset density in the 32-bar closing window. |
| `outro_32_spectral_centroid` | Spectral centroid or brightness in the 32-bar closing window. |
| `outro_64_available` | Whether a 64-bar closing analysis window is available. |
| `outro_64_bpm` | Estimated tempo in beats per minute in the 64-bar closing window. |
| `outro_64_beat_stability` | Stability of the detected beat grid in the 64-bar closing window. |
| `outro_64_sub_energy` | Relative sub-bass energy in the 64-bar closing window. |
| `outro_64_low_energy` | Relative low-frequency energy in the 64-bar closing window. |
| `outro_64_low_mid_energy` | Relative low-mid energy in the 64-bar closing window. |
| `outro_64_kick_strength` | Estimated kick-drum prominence in the 64-bar closing window. |
| `outro_64_kick_density` | Estimated density of kick-drum events in the 64-bar closing window. |
| `outro_64_bass_density` | Estimated density of bass activity in the 64-bar closing window. |
| `outro_64_loudness_lufs` | Integrated loudness in LUFS in the 64-bar closing window. |
| `outro_64_onset_density` | Estimated onset density in the 64-bar closing window. |
| `outro_64_spectral_centroid` | Spectral centroid or brightness in the 64-bar closing window. |

## `sections`

| Field | Description |
| --- | --- |
| `source_id` | Stable identifier of the configured library source. |
| `track_id` | Stable numeric identifier of the track in the catalog. |
| `path` | Path relative to the configured source root. |
| `analysis_schema_version` | Version of the published audio-analysis schema. |
| `sections` | Ordered structural sections detected for the track. |

## `run`

| Field | Description |
| --- | --- |
| `analysis_schema_version` | Version of the published audio-analysis schema. |
| `catalog_schema_version` | Catalog schema version used for the export. |
| `started_at` | Timestamp when the analysis run started. |
| `finished_at` | Timestamp when the analysis run finished. |
| `status` | Overall status of the analysis run. |
| `eligible` | Number of tracks eligible for the analysis run. |
| `analyzed` | Number of tracks analyzed during the run. |
| `reused` | Number of existing analysis results reused during the run. |
| `failed` | Number of tracks whose analysis failed during the run. |
| `config_hash` | SHA-256 identity of the DSP configuration used for analysis. |
| `analyzer_version` | Version identifier of the analyzer that produced the result. |
| `failures` | Ordered details of per-track analysis failures. |
