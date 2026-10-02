# Telemetry Tagging

## Purpose
Describe AI-assisted derivation of telemetry requirements from completed Workbench context.

## Audience
Detection engineers and reviewers ensuring telemetry transparency and quality.

## Prerequisites
Required Workbench fields populated for telemetry derivation gate.

## Steps / Workflow
1. Complete required Workbench inputs (TTP, goal, technical context, rule, threat surface).
2. Trigger telemetry derivation.
3. Review and edit derived telemetry tags.
4. Persist tags with Workbench and downstream exports.

## Validation / Expected result
Workbench contains explicit telemetry requirements aligned to detection logic.

## Troubleshooting
If derivation is blocked, verify required fields and section visibility constraints.

## Related pages
- [Detection Workbench](detection-workbench.md)
- [Detection Chokepoints](detection-chokepoints.md)
- Source detail: `Docs/TELEMETRY_TAGGING.md`
