# Commit message pattern

Use English and the subject form:

`type[(scope[, scope2, ...])]: imperative summary`

- Type: `feat`, `fix`, `refactor`, `chore`, or `docs`.
- Scope is optional. Use it only when one concise DJ Digger area clarifies the
  change, such as `cli`, `catalog`, `analysis`, `exports`, `copy`, or `codex`.
  The repository commonly uses unscoped subjects such as `feat: ...` and
  `docs: ...`; do not invent a scope for consistency theatre.
- Keep the summary lowercase, imperative, and specific; wrap identifiers and
  paths in backticks when they appear in a body.
- Add `(#PRD-XXXX)` only when the user supplies a ticket reference. Omit it for
  internal tooling.

Use no body for mechanical changes. For meaningful changes, use short prose for
one cause or bullets for distinct changes. When a bounded worker brief is
useful, include:

```
Goal: <what this commit solves>
Changed files: <paths or area>
Observed proof: <QA command and result>
Residual risk: <none or precise reservation>
```

Never add `Co-Authored-By`, `Signed-off-by`, or tool-attribution trailers.
