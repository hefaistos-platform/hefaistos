# Changelog Process

## Purpose
Explain how version-scoped changelog entries are generated and maintained.

## Audience
Maintainers and release reviewers.

## Prerequisites
Version automation enabled and conventional commit usage.

## Steps / Workflow
1. On version bump, review `Versions/vX.Y.Z/changelog.md` output.
2. Confirm commit categorization and migration listing sections.
3. Backfill missing changelog files using stable-tag workflow when needed.

## Validation / Expected result
Each released version has a corresponding changelog record under `Versions/`.

## Troubleshooting
If section grouping is wrong, verify commit subject format in the bump window.

## Related pages
- [Versioning Policy](versioning-policy.md)
- [CI Version Flow](ci-version-flow.md)
- Source artifacts: `Versions/`
