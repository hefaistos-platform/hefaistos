# TLP classification

Workbench supports CLEAR, GREEN, AMBER, AMBER+STRICT, RED, and **TLP:UNCLEAR**,
from the community amendment proposal at [tlp-unclear.org](https://tlp-unclear.org/).
The proposal describes using UNCLEAR when the sender is unsure which TLP label
is appropriate. HEFAISTOS displays it in purple as configured for this application.

Use UNCLEAR when the source is unavailable or unknown, the source's sharing
model is unclear or unknown, or the source does not use a sharing model.
UNCLEAR does not imply permission to share publicly.

New Workbenches and missing or unrecognized classifications default to UNCLEAR.
Existing saved classifications are retained. The SOAR selector, Workbench badge,
Hub column, AI mapping, and supported Workbench import/export paths use this value.
OpenTIDE YAML stores it as lowercase `unclear`; external validators must support
the TLP:UNCLEAR proposal to accept it.

## Planned introduction to ACH, AdvOps, and MVE

1. Add `tlp_classification` to `ACHAnalysis`, `ADVOPSReport`, and `MveDraft` using
   the shared backend choices, with UNCLEAR as the default for new and existing
   records that have no classification. Expose `tlpClassification` through list,
   detail, create, and update GraphQL operations, using existing edit permissions.
2. Reuse the shared badge and selector options in each module. Add a TLP column
   before Actions in table overviews, a badge in detail headers, and an editable
   classification in creation/settings forms. Include badges on AdvOps Kanban
   cards and in the MVE draft overview.
3. ACH: preserve classification when saving/applying templates and copy the
   analysis classification in `CreatePlaybookGraphFromHypothesis`.
4. AdvOps: update `ADVOPSForm`, report types, and mutation responses. Preserve TLP
   in peer-sharing imports/exports. For MISP, use standard TLP tags for official
   levels and a tag representing the tlp-unclear.org proposal for UNCLEAR. Do not map UNCLEAR
   to an official TLP level or derive public/community distribution from it.
   Replace the current hardcoded community distribution with explicit handling.
5. MVE: update `CreateMveDraft`, `UpdateMveDraft`, and `MveDraftType`; include
   lowercase TLP in VelocityDetection metadata and copy it in
   `CreateWorkbenchFromMve`. Preserve classification when appending to a
   Workbench. Handle conflicting classifications explicitly; UNCLEAR has no
   position in an ordered disclosure hierarchy and must not be treated as CLEAR.
6. Verify all six levels, missing/unknown values, permissions, template copying,
   Workbench conversions, import/export preservation, MISP metadata, and visible
   badge updates. Include a regression case proving UNCLEAR never maps to CLEAR.
