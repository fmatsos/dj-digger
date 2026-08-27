---
name: task
description: Route work by risk and model; consult CLAUDE.md routing table for model and effort assignment
---

## Purpose

Scopes tasks and prevents re-exploration. Routes bounded tranches to the
appropriate model based on the root CLAUDE.md model table.

## Inputs

- Goal (one line, what is being solved)
- Changed files (list of modified paths or affected subsystems)
- Observable acceptance criteria (command, state, or artifact proof)
- Relevant CLAUDE.md (scoped file from affected directory)
- Required skill (task, implement, qa, runtime-proof, etc.)
- Focused QA profile (docs, focused, subsystem, catalog, analysis, exports, runtime, or full)
- Do not touch (files or areas out of scope)

## Routing

Consult the root CLAUDE.md "Models and delegation" table for the current
model and effort assignment — do not restate it here. Route each tranche
accordingly before dispatch. See scoped CLAUDE.md files for
directory-specific rules.

## Outputs

See root CLAUDE.md's "Models and delegation" section for the exact
delegation payload and reporting contract — do not restate it here.

## Handoff format

Always include: Status, Branch, Diff, QA, Next, Risk. Use `.claude/scripts/handoff` for compact format.
