# MISP Intake Model

## Purpose
Document the MISP-only ingestion path for Waiting Room case intake.

## Audience
Integrators and operators connecting external threat intelligence sources.

## Prerequisites
Configured MISP instance and threat intel connector settings.

## Steps / Workflow
1. Prepare source events in MISP with required object structure/tags.
2. Trigger manual import or scheduled auto-pull.
3. Review import outcomes and deduplication behavior in Waiting Room.

## Validation / Expected result
Eligible MISP events become normalized waiting cases and are traceable in import ledgers.

## Troubleshooting
If cases are skipped, verify tag gating, source identifiers, and connector schedule.

## Related pages
- [Waiting Room](../features/waiting-room.md)
- [Connectors Overview](connectors-overview.md)
- Source detail: `Docs/WAITING_ROOM_WORKBENCH.md`
