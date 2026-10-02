# CI Version Flow

## Purpose
Document GitHub Actions workflows that manage automated version bumping and release tagging.

## Audience
Maintainers operating repository release automation.

## Prerequisites
Actions workflow write permissions and branch protection settings compatible with automation.

## Steps / Workflow
1. Confirm workflow permissions and release-branch protections.
2. Push commits to trigger SHARP version bump workflow.
3. Run stable tag workflow for `vX.Y.Z` release creation.

## Validation / Expected result
Automation updates `VERSION`, updates README badge, and writes version changelog artifacts.

## Troubleshooting
If workflows cannot push, re-check Actions write permissions and branch protection bot allowances.

## Related pages
- [Versioning Policy](versioning-policy.md)
- [Changelog Process](changelog-process.md)
- Source detail: `Docs/CI_VERSION_FLOW.md`
