# System Update

## Purpose
Describe superuser-only in-app update workflow and safety model.

## Audience
Superusers and operators performing platform updates.

## Prerequisites
Superuser access and operational compose environment.

## Steps / Workflow
1. Check local vs repository version state.
2. Start default or force update mode.
3. Monitor asynchronous job status and logs.
4. Confirm readiness checks pass after update.

## Validation / Expected result
Update job finishes successfully and platform services return to healthy running state.

## Troubleshooting
If update checks fail due to git ownership, apply safe.directory guidance or explicit repository version override.

## Related pages
- [Service Matrix](service-matrix.md)
- [Versioning Policy](../release/versioning-policy.md)
- Source detail: `Docs/SYSTEM_IN_APP_UPDATE.md`
