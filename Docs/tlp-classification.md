# TLP classification

Workbench, ACH, AdvOps, MVE, Rules, and Capability Abstractions support CLEAR, GREEN, AMBER, AMBER+STRICT, RED,
and **TLP:UNCLEAR**, from the community amendment proposal at
[tlp-unclear.org](https://tlp-unclear.org/). The proposal describes using UNCLEAR
when the sender is unsure which TLP label is appropriate. The application
uses purple for UNCLEAR.

Use UNCLEAR when the source is unavailable or unknown, the source's sharing
model is unclear or unknown, or the source does not use a sharing model.
UNCLEAR does not imply permission to share publicly.

Workbench, ACH, AdvOps, MVE, and standalone rule records default to UNCLEAR.
Capability Abstractions default to AMBER+STRICT. Missing or unrecognized item
classifications normalize to UNCLEAR.
Existing Workbench classifications are retained. Existing ACH analyses,
ACH templates, AdvOps reports, and MVE drafts receive UNCLEAR when their new
classification fields are added.

## Editing and visibility

- Workbench: edit in SOAR Configuration; view the badge below Workbench Layout
  Defaults and the Hub TLP column before Actions.
- ACH: select TLP during creation or edit it in the analysis header. The owner
  can change it. View the header badge and overview TLP column before Actions.
  Selecting a template copies its TLP to the new analysis.
- AdvOps: edit TLP in the hunt form; view the form badge and overview TLP column
  before Actions. Edits use the existing organization permissions.
- MVE: edit TLP in the selected draft's overview card, independently of modeling
  completeness. View badges in the draft selector and overview card. Existing
  organization and role permissions apply; exported drafts remain locked.
- Rules: Rule Hub cards and rule detail headers show TLP inherited from the
  owning Workbench, otherwise the attached Workbench. Unlinked rules use a stored
  snapshot. Workbench changes update linked rule classifications.
- Capability Abstractions: select TLP in the Library or Workbench capability form;
  the default is AMBER+STRICT. View library columns, cards, and detail badges.
- Kanban: Workbench, ACH, AdvOps, and MVE show TLP in cards, compact list rows,
  and the details drawer.

## Preservation and exports

ACH templates, analysis copies, and Workbenches created from hypotheses retain
the source classification. Workbenches created from AdvOps or MVE also retain it.
ACH and AdvOps peer exports/imports preserve TLP; older peer updates without a
TLP field retain the existing local value.

OpenTIDE and MVE VelocityDetection YAML store TLP in lowercase. External
validators must support the TLP:UNCLEAR proposal to accept `unclear`.
Appending MVE to a Workbench requires matching classifications; a mismatch is
rejected before either record changes. Attached velocity chains and their TLP
metadata survive subsequent Workbench metadata refreshes.

MISP events carry `tlp:<level>` tags, including `tlp:unclear`. CLEAR uses all
communities distribution, GREEN uses connected communities, and AMBER,
AMBER+STRICT, RED, and UNCLEAR use organization-only distribution. Sharing
restricted events with specific recipients or clients requires a separately
configured MISP sharing group. Events are created unpublished.

## Instance Sharing

Inbound keys use a Required TLP Classification maximum, combined with existing
status, remote pull opt-in, and tag checks. GREEN permits CLEAR, GREEN, and UNCLEAR.
The maximum applies to all five sharing scopes; existing keys default to RED.
See [the full policy, inheritance, defaults, and deployment instructions](instance-sharing-tlp.md).

## Database migrations

Apply `ach.0007`, `advops.0004`, and `playbooks.0055` before running the updated
frontend and backend. Instance Sharing TLP additionally requires
`organizations.0037`, `playbooks.0056`, and `rules.0030`. For a Compose deployment:

```sh
docker compose exec backend python manage.py migrate
```
