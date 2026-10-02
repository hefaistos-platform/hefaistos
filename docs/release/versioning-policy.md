# Versioning Policy

## Purpose
Define HEFAISTOS version semantics and bump/release rules.

## Audience
Maintainers and release managers.

## Prerequisites
Understanding of conventional commit conventions and release branch policy.

## Steps / Workflow
1. Track base semantic version in root `VERSION` file.
2. Apply bump rules from commit messages (major/minor/patch).
3. Distinguish SHARP artifact versioning from stable release tags.

## Validation / Expected result
Version outputs are deterministic and aligned with repository automation.

## Troubleshooting
If bump level is unexpected, inspect commit messages for breaking markers and conventional prefixes.

## Related pages
- [CI Version Flow](ci-version-flow.md)
- [Changelog Process](changelog-process.md)
- Source detail: `Docs/VERSIONING.md`
