# Documentation Scope Instructions

This scope covers project documentation in the `docs/` directory.

## Document categories

Documentation is organized into four distinct categories:

1. **Current architecture**: Describes the active system as implemented today,
   including module boundaries, data flow, and interface contracts.

2. **Measured acceptance**: Documents observed behavior, test results, and
   performance characteristics from real runs.

3. **Designs**: Proposed or under-consideration changes, including architecture
   alternatives and feature sketches. Designs are explicitly marked as future
   or exploratory work.

4. **Historical plans**: Records of past planning decisions, executed tasks, and
   completed work. These provide context for architectural choices.

## No rewriting history

Documentation must not rewrite historical plans to match implementation that
diverged from the plan. If implementation differs from a historical plan,
document the divergence and the reason. Preserve the plan as written, with
explicit notes on what actually occurred.

## Spec protection

The `docs/superpowers/specs/**` directory is protected. historical plans, explicit staging
— changes to this tree require explicit user authorization before staging. Specs
document the design authority for Claude Code workflows and must not be modified
without clear intent.

## Distinction and clarity

Each document clearly indicates its category (current, measured, design, or
historical). Readers must not confuse a design sketch with implemented behavior
or a historical plan with current architecture.

## Style and audience

Documentation targets agents and future maintainers. Prose is clear and
technical, avoiding both vagueness and excessive jargon.
