# Documentation Scope Instructions

This scope covers project documentation in the `docs/` directory.

## Document categories

Tracked documentation is limited to current technical architecture, functional
usage, and development operations. Historical plans, specifications, migrations,
and acceptance records live in the ignored `.specifications/` archive.

## No rewriting history

Documentation must not rewrite historical plans to match implementation that
diverged from the plan. If implementation differs from a historical plan,
document the divergence and the reason. Preserve the plan as written, with
explicit notes on what actually occurred.

## Specification archive

The `.specifications/**` directory is ignored by Git and contains historical plans,
specifications, migrations, and acceptance records. It is not part of the published
technical or functional documentation surface.
— changes to this tree require explicit user authorization before staging. Specs
document the design authority for Codex workflows and must not be modified
without clear intent.

## Distinction and clarity

Each document clearly indicates its category (current, measured, design, or
historical). Readers must not confuse a design sketch with implemented behavior
or a historical plan with current architecture.

## Style and audience

Documentation targets agents and future maintainers. Prose is clear and
technical, avoiding both vagueness and excessive jargon.
