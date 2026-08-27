---
name: native-analysis
description: Validate Python 3.12 compatibility, workers, IPC, concurrency, and resource limits
---

## Purpose

Provides evidence of real analysis worker behavior and Python limitations. Checks for OOM conditions, IPC protocol correctness, parent-process-only persistence, and honest reporting of inaccessible libraries.

## Checks

1. **Python 3.12**: Requires Python 3.12 and the `analysis` extra; code uses no deprecated patterns.
2. **OOM evidence**: Worker crash logs or observed memory usage are checked; not assumed. Bounded memory is a requirement, evidenced rather than claimed.
3. **Fresh workers**: A fresh child process is used per track.
4. **IPC**: Bounded, versioned JSON IPC between parent and worker.
5. **Parent-only persistence**: Only the parent writes to SQLite.
6. **Crash and timeout outcomes**: Worker crashes and timeouts are visible, not silently swallowed.
7. **Honest reporting**: Inaccessible libraries (network, cloud) are reported as unverified.

## Observable proof format

```
Python: python3 --version (3.12.x)
OOM: observed worker memory usage or crash log (not assumed)
IPC: bounded, versioned JSON IPC confirmed between parent and worker
Parent-SQLite: only the parent process writes to catalog.sqlite
Crash/timeout: worker crash or timeout outcome observed and reported
Inaccessible: <library> requires cloud/network — unverified
```

## Do not do

- Report network libraries as passed without testing
- Assume OOM or memory behavior without observed evidence (file descriptor
  limits such as `ulimit -n` measure descriptors, not memory, and are not OOM
  evidence)
- Write from worker processes to shared SQLite
- Report a crash or timeout outcome without observing it directly
