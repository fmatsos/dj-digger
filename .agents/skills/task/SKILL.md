---
name: task
description: Route work by risk and model; consult AGENTS.md routing table for Sol/Luna and effort assignment
---

## Purpose

Scopes direct-Codex tasks and prevents re-exploration. Under Docker Agent, the
bounded brief is authoritative and this skill is a fallback for direct use.
Routes tranches to Luna or Sol based on the root AGENTS.md model table.

## Inputs

- Goal (one line, what is being solved)
- Changed files (list of modified paths or affected subsystems)
- Observable acceptance criteria (command, state, or artifact proof)
- Relevant AGENTS.md (scoped file from affected directory)
- Required skill (task, implement, qa, runtime-proof, etc.)
- Focused QA profile (docs, focused, subsystem, catalog, analysis, exports, runtime, or full)
- Do not touch (files or areas out of scope)

## Routing

Consult the root AGENTS.md "Models and delegation" table for the current Sol/Luna
model and effort assignment — do not restate it here. Route each tranche accordingly
before dispatch. See scoped AGENTS.md files for directory-specific rules.

## Outputs

See root AGENTS.md's "Models and delegation" section for the exact delegation
payload and reporting contract — do not restate it here.

## Handoff format

Always include: Status, Branch, Diff, QA, Next, Risk. Use `.agents/scripts/handoff` for compact format. A Docker Agent worker returns this handoff to the lead.
