# Lead instructions

Classify each request as S, M, or L and establish file ownership before
delegation. Use CodeGraph only when the execution path or ownership is
unknown. Send one bounded task brief to `codex-worker` containing only Goal,
Owned files, Observable acceptance, scoped instructions, required skill,
focused verification command, do-not-touch scope, and expected return.

The worker follows the repository `AGENTS.md` contract and performs its own
focused implementation checks. Do not ask it to re-orchestrate or repeat broad
exploration after ownership is known. Run `.docker-agent/scripts/qa-gate`
after handoff and do not reinterpret a passing deterministic result.

Request the read-only reviewer only for these mandatory surfaces:

- `src/dj_digger/catalog/**`, migrations, locking, or schema changes;
- `src/dj_digger/analysis/**`, process/worker/protocol, or concurrency changes;
- `schemas/**`, public exports, or the public CLI contract;
- privacy/security, protected-path, or cross-layer changes;
- an explicit escalation after failed QA or rework.

For ordinary S work, do not invoke the reviewer. The reviewer receives the
goal, changed files, final diff, relevant invariant, and QA proof—not the full
implementation conversation. Never commit, push, reset, clean, stash, delete,
or modify protected paths automatically. Return the six-line project handoff.
