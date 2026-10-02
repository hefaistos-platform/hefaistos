# Waiting Room

## Purpose
Describe controlled intake and triage of external detection intelligence before Workbench promotion.

## Audience
Reviewers, admins, and analysts handling imported intelligence.

## Prerequisites
Configured MISP integration and role access for waiting-case workflows.

## Steps / Workflow
1. Import candidate cases into Waiting Room.
2. Normalize, filter, and deduplicate external content.
3. Review and update waiting cases.
4. Promote approved cases to Workbench.

## Validation / Expected result
Only vetted, non-duplicated cases are promoted into operational Workbench content.

## Troubleshooting
If imports are missing, verify source tags, connector scheduling, and deduplication keys.

## Related pages
- [MISP Intake Model](../integrations/misp-intake-model.md)
- [Detection Workbench](detection-workbench.md)
- Source detail: `Docs/WAITING_ROOM_WORKBENCH.md`
