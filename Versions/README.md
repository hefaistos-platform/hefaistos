# Versions

This directory stores generated version changelog documents for the platform.

A GitHub Actions workflow (`.github/workflows/sharp-version.yml`) generates a changelog for every automatic version bump on `main`.
An additional workflow (`.github/workflows/version-changelog.yml`) backfills missing changelogs when a new `v*` tag is pushed.

Each version is stored in its own folder using the format `Versions/vX.Y.Z/changelog.md` (for example: `Versions/v1.2.3/changelog.md`) and contains:

- Changes
- Fixes
- Removals
- Database Migrations
