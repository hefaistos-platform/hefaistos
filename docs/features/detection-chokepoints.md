# Detection Chokepoints

## Purpose
Explain how staged chokepoint snapshots ground detection quality and AI outputs.

## Audience
Superusers and maintainers operating framework update workflows.

## Prerequisites
Superuser access and connectivity to configured chokepoint source.

## Steps / Workflow
1. Trigger chokepoint import into staged snapshot.
2. Review staged vs active diffs.
3. Promote staged snapshot or roll back to prior snapshot when needed.

## Validation / Expected result
Active snapshot provides stable, auditable grounding data for downstream workflows.

## Troubleshooting
If snapshot activation fails, check import job logs and snapshot status transitions.

## Related pages
- [Telemetry Tagging](telemetry-tagging.md)
- [System Update](../operations/system-update.md)
- Source detail: `Docs/README_CHOKEPOINTS.md`
