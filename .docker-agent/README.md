# Docker Agent workflow

This is an optional orchestration layer for DJ Digger. The `lead` scopes a
request, delegates one bounded brief to the `codex-worker`, runs the
deterministic `.docker-agent/scripts/qa-gate`, and requests a fresh read-only
review only for elevated-risk changes. Direct Codex use remains supported and
is the fallback when Docker Agent is unavailable.

The configuration uses Docker Agent schema version 15. Native agents use
ChatGPT-backed model aliases: Luna low for orchestration and Sol medium for
elevated-risk review. The `codex-worker` uses the Codex harness pinned to
GPT-5.6 Luna. The repository guard, `protect-local`, and staged checks remain
authoritative alongside the Docker Agent configuration.

Run the read-only `session-guard` before a session; it verifies the DJ Digger
worktree and required deterministic scripts. Filesystem denies and
`protect-local` remain independent safeguards. Destructive commands are denied
by policy and Git delivery operations require explicit approval.

Benchmark artifacts belong under `.agent-benchmarks/` and are privacy-safe,
deterministic summaries. They must not contain prompts, responses, commands,
absolute paths, private library facts, or unhashed session IDs.

The lead and worker use a bounded task brief. Once ownership is established,
the worker reads only the relevant scoped `AGENTS.md` and does not repeat
repository-wide exploration. QA remains observable and the project handoff is:

```text
Status : COMPLETE | PARTIAL | BLOCKED
Branch : <branch>
Diff   : <changed files>
QA     : <profiles and commands>
Next   : <follow-up or none>
Risk   : <none or precise reservation>
```
