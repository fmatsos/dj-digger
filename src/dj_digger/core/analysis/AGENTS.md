# Analysis Worker Instructions

This scope covers analysis worker processes, child spawning, IPC, and DSP results.

## Process model

A fresh child process is spawned for each track. The parent process is the sole
SQLite writer and manages the lifecycle of all analysis children. Child processes
terminate when analysis completes or when the parent closes the IPC channel.

Process groups are cleaned up explicitly: a child that crashes or times out must
be removed from the process table, its exit status recorded, and its incomplete
results handled deterministically.

## IPC and versioning

Communication between parent and child uses bounded, versioned JSON messages
with a protocol_version field in all frames. This parent-only SQLite, protocol_version
design allows protocol evolution and detection of incompatible analyzer versions.

Messages are exchanged over pipes or sockets with explicit size and timeout bounds.
A child that sends an oversized message or stops responding is killed and logged.

## Persistence

parent-only SQLite writes are enforced: a child process must not open or modify
the catalog. All analysis results are returned to the parent via IPC and persisted
by the parent alone.

## Computation bounds

DSP processing uses bounded float32 arithmetic. Intermediate results are
constrained to prevent memory exhaustion. Analysis workers that exceed configured
memory, CPU time, or wall-clock time limits are terminated and their status is
recorded.

## Analyzer updates

Changes to analysis behavior (DSP algorithms, feature extraction, result schemas)
must update the analyzer-identity field in the catalog so that stale results can
be invalidated.
