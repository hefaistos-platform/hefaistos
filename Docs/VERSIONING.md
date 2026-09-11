# HEFAISTOS PRO Versioning Policy

Effective date: July 9, 2026

## Standard

HEFAISTOS PRO uses hybrid semantic versioning:

- `MAJOR.MINOR.PATCH-sharp.BUILD` for SHARP artifacts.
- `MAJOR.MINOR.PATCH` for stable releases.

`VERSION` in repository root is the single source of truth for the base semantic version (`MAJOR.MINOR.PATCH`).

## Bump rules

Every push to `main` (or legacy `sharp`) produces a version bump using commit messages in that push range:

- `MAJOR` if any commit indicates breaking change:
  - `BREAKING CHANGE:` in commit body, or
  - conventional commit with `!` marker, for example `feat!: ...` or `refactor(core)!: ...`.
- `MINOR` if any commit subject matches `feat(...)?: ...`.
- `PATCH` for all remaining commit types (`fix`, `chore`, `docs`, `refactor`, `test`, `ci`, merge commits, and others).

## Release rules

- SHARP automation updates `VERSION` and commits it back to the release branch (`main`; legacy fallback `sharp`).
- SHARP automation writes a per-version changelog to `Versions/vX.Y.Z/changelog.md`.
- Stable releases are created by a manual workflow that:
  - validates the selected commit is on the release branch (`main`; legacy fallback `sharp`),
  - reads `VERSION` from that commit,
  - creates annotated git tag `vMAJOR.MINOR.PATCH`.

## Examples

- `1.4.2` + patch push on `main` => `1.4.3-sharp.128`
- `1.4.3` + feature push on `main` => `1.5.0-sharp.129`
- `1.5.0` + breaking push on `main` => `2.0.0-sharp.130`
- stable promotion => tag `v2.0.0`
