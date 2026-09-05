# Pull request description

Title:

`type[(scope)]: imperative summary`

Body:

```markdown
## Summary
- <distinct change, based on actual commits and diff>

## Test plan
- [ ] <re-runnable QA command or public-path check>

## Risks and notes
- <none, or a precise residual risk and follow-up>
```

Omit the risks section only when there is no meaningful reservation. Keep
identifiers and paths in backticks. Use checkboxes even for checks already run,
so reviewers can reproduce them. If the branch has no applicable ticket,
include no ticket section. Never include `Co-Authored-By`, `Signed-off-by`, or
generated-by attribution.
