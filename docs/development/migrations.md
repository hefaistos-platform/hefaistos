# Migrations

## Purpose
Describe database migration lifecycle for HEFAISTOS backend changes.

## Audience
Backend contributors and release maintainers.

## Prerequisites
Backend service access and migration tooling available.

## Steps / Workflow
1. Create new migration after model updates.
2. Apply migrations in local and deployment environments.
3. Check migration status before release/update.

## Validation / Expected result
Schema changes apply cleanly and migration history remains consistent.

## Troubleshooting
If migration conflicts appear, inspect dependency graph and sequence before applying fixes.

## Related pages
- [Testing](testing.md)
- [System Update](../operations/system-update.md)
- [Changelog Process](../release/changelog-process.md)
