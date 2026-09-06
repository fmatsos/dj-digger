# Curation exports

> Current functional documentation for the `dj-digger curation export` command.

A persisted draft or validated curation can be exported with:

```console
dj-digger curation export ID --content playlist|report|both [--copy-files] --output PATH
```

The output path must not already exist. DJ Digger prepares the complete output in a
temporary sibling directory and renames that directory into place only after every
selected artifact and optional track copy succeeds. This prevents both accidental name
collisions and partially published exports.

`--content playlist` writes a UTF-8 `curation.m3u8`, `--content report` writes
`report.md`, and `--content both` writes both. The Markdown file contains the persisted
draft report exactly, without a generated suffix. Track order is the persisted catalogue
order.

File copying is independent of the content selection. With `--copy-files`, tracks are
copied into the export's `tracks/` directory with numbered, collision-resistant names;
playlist entries, when selected, are relative to that portable directory.

Without `--copy-files`, a playlist contains absolute paths rooted in the single configured
source used by its tracks. This is deliberately a single-source format: M3U8 does not
carry a safe mapping from source identifiers to multiple consumer-side library roots.
DJ Digger therefore refuses a multi-source playlist without copying and reports that
`--copy-files` plus a portable `--output` target is required. A report-only export does
not have this restriction because it contains no filesystem references.

Before publication, every catalog identity is resolved against its matching
`WorkspaceConfig` source. DJ Digger rejects absolute or traversing catalog paths, paths
that escape through links, missing or non-regular files, and files whose recorded size or
modification time no longer matches the snapshot. Destination symbolic links and existing
paths are also refused.
