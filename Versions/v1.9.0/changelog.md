# v1.9.0

_2026-10-30_

## Changes
- Introduce deployment-local AI prompt governance with reviewed versions, scoped overrides, audit history, and rollback.
- Preserve AI rule generation evidence and saved rule revisions.
- Prepare correction diffs and collect structured, user-confirmed feedback for admin review.
- Track per-format and selected-variant attribution across Workbench saves, standalone drafts, and MVE rule generation.
- Add an organization-scoped feedback review queue with JSON evidence, root-cause classification, and audit history; accepting feedback leaves prompt activation in its separate approval workflow.

- Add feedback-driven prompt improvement proposals with optional AI drafting, paired baseline/candidate evaluations, immutable evidence, per-case admin assessment, and approval before activation.

- Add a visible AI feedback entry point beside editor save controls and on saved rule details, plus in-app how-to guides for authors and admins.

## Fixes
- Honor explicit version increases in release automation without applying another automatic bump.
- Keep AI Quality selected values and dropdown menus readable in light, dark, and system themes.

## Removals
- None.

## Database Migrations
- `ai_assistant.0017_ai_quality_prompt_versions`
- `ai_assistant.0018_ai_rule_feedback`
- `ai_assistant.0019_ai_improvement_proposals`
