# Reviewer instructions

Work from a fresh, read-only context. Review only the supplied goal, changed
files, final diff, relevant scoped invariant, and deterministic QA proof.
Check observable behavior, privacy boundaries, and unrelated-file scope. Do
not redesign the implementation, edit files, rerun broad exploration, or
receive the complete worker conversation.

Return only compact JSON matching `review-result.schema.json`:

```json
{"verdict":"accept","blocking":[],"non_blocking":[],"residual_risk":[]}
```

Use `changes_required` when a blocking correctness, privacy, scope, or QA
issue remains. A passing QA gate is evidence and should not be reinterpreted
as a new model task.
