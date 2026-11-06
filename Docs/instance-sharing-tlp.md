# Instance Sharing: maximum TLP policy

In **Configuration → Instance Sharing**, each inbound share key has a
**Required TLP Classification (Maximum)**. Administrators select it when creating
a key and can change it in the existing key table. The selector lists the exact
classifications permitted by the selected maximum. Revoked keys cannot be used.
The receiving peer uses the key issued by the origin; the origin enforces its
policy on every export request.

## Permitted classifications

| Required maximum | Permitted item classifications |
| --- | --- |
| UNCLEAR | UNCLEAR only |
| CLEAR | CLEAR, UNCLEAR |
| GREEN | CLEAR, GREEN, UNCLEAR |
| AMBER | CLEAR, GREEN, AMBER, UNCLEAR |
| AMBER+STRICT | CLEAR, GREEN, AMBER, AMBER+STRICT, UNCLEAR |
| RED | CLEAR, GREEN, AMBER, AMBER+STRICT, RED, UNCLEAR |

The order is CLEAR → GREEN → AMBER → AMBER+STRICT → RED. UNCLEAR is always
included by each of those five maximums. The dropdown also offers UNCLEAR;
selecting it permits only UNCLEAR items. It is the unofficial community
amendment proposal from [tlp-unclear.org](https://tlp-unclear.org/), displayed in
purple. Use it when the source is unavailable or unknown, its sharing model is
unclear or unknown, or no sharing model is used. Including it in this export
policy does not redefine it as public disclosure.

Existing keys migrate to RED; newly created keys also default to RED. This
retains existing eligibility until an administrator selects a lower maximum.
API creation requests that omit the field default to RED. Invalid values are
rejected; UNCLEAR is a valid policy selection. Bare or TLP-prefixed values are
accepted, case-insensitively.

## Combined eligibility

TLP applies to **Workbench, Rules, ACH, AdvOps, Capability Abstraction, and
Maieutic sessions**, including these collections in ALL exports. MVE has TLP but is not currently an
Instance Sharing scope.

Every item must still satisfy its existing organization, status, and remote
pull opt-in checks. When a key enforces Required Tags, Workbench and Rules must
also match all required tags, case-insensitively. TLP and tags combine with AND;
passing either alone is insufficient. Tags do not apply to ACH, AdvOps,
Capability Abstraction, or Maieutic sessions.

For example, a GREEN key with required tag PULL exports only enabled, deployed
Workbenches tagged PULL whose TLP is GREEN, CLEAR, or UNCLEAR. An AMBER Workbench
is excluded even if it has PULL. An untagged GREEN Workbench is also excluded.
Filtering happens before duplicate-name selection so a restricted duplicate
cannot hide an eligible item.

## Rule inheritance

Rules inherit the current classification from their owning Workbench
(`playbook`). If no owner exists, they inherit from the additional Rule Hub
association (`attached_workbench`). The owner takes precedence when both exist.
There is no independent TLP dropdown for linked rules; change the Workbench's TLP.
Rule Hub cards, rule detail headers, and the Detection Rule Editor header display
the inherited classification, including the editor opened directly from Workbench.

A stored snapshot is updated on rule saves and Workbench classification saves;
GraphQL and sharing read the effective inherited value. Existing linked rules
are backfilled during migration. Unlinked rules retain their stored value;
new standalone rules default to UNCLEAR. Unlinking retains the last inherited
snapshot. Canonical editor/publishing metadata uses the effective value in
lowercase. Existing native rule text is retained.

Instance Sharing still exports only rules owned by a deployed Workbench with
remote pull enabled. An additional Rule Hub association alone does not opt a
rule into sharing.

## Maieutic sessions (scope `MAIEUTIC`)

Finished [Maieutic](README_MAIEUTIC.md) sessions can be pulled by trusted peers.

**What leaves.** A session leaves only when all of these hold: it is `FINISHED`, its author switched
sharing on in Workbench Hub > Maieutics (default off), it was created on this instance (copies you
pulled are never passed on), and its own TLP is within the key's maximum. Sessions are de-duplicated
by title.

**What is sent.** The design record: hypothesis, telemetry choices, design, your evasion answers
(the ADE ledger), response and test notes, outcome and TLP, plus the identity of the ADE snapshot the
answers were given against (repository, ref, commit). **Not sent:** the Workbench created from the
session, its rule, its conversation history, the author, and any local identifiers.
If the author used wording help, the "AI reworded" mark travels with the field, but never the text it replaced
or any unused suggestion. Sharing a session
and sharing its Workbench are independent; a peer can have either without the other.

**What the receiver gets.** A finished, locked, read-only copy that belongs to the person who ran the
pull, shown in the Maieutics tab as "Imported from <peer>". The TLP is preserved, there is no
Workbench, and sharing is off and cannot be switched on. A later pull updates the copy instead of
duplicating it. The ADE snapshot identity is kept as history; the receiver does not need to have
imported that snapshot. Deleting the copy does not affect the source; a later pull recreates it.
Incoming data is validated: only known sections are kept, oversize or newer-format sessions are
rejected, and one bad session does not stop the others.

### Keys created before this scope existed

An `ALL` pull used to need all five original scopes. Keys that list those five explicitly (without the
`ALL` marker) **keep working for `ALL` and do not receive sessions.** They can never request
`MAIEUTIC` unless an administrator adds it. A key with the `ALL` marker grants everything, so it now
includes sessions; this is still limited to sessions whose author switched sharing on. A key listing
only `MAIEUTIC` can pull sessions and nothing else.

### Mixed versions

Pulling `ALL` from a peer that does not know sessions yet works; that collection is simply absent. An
explicit `MAIEUTIC` pull from such a peer fails with a clear message, because the peer rejects the scope.

## Capability Abstraction

Both the Capability Library and Workbench capability form include a
**TLP Classification** dropdown with all six values. New entries default to
**AMBER+STRICT**. Existing entries, including baseline entries, receive that
value during migration. TLP appears in library rows, capability cards, and details.
Changing it uses existing edit permissions and advances the capability version.

Capability export still requires Approved status, remote pull opt-in, and a
non-baseline entry owned by the origin organization. A GREEN maximum therefore
excludes a capability with the default AMBER+STRICT classification.

## Transport and diagnostics

Rule and capability payloads include `tlp_classification`; Workbench, ACH, and
AdvOps retain their existing TLP transport fields. Imports preserve source TLP.
For rules linked to a local Workbench, local inheritance takes precedence.
Older rule imports without TLP retain an existing unlinked rule's value, or use
UNCLEAR for a new unlinked rule. Older capability imports without TLP retain
existing local values, or use AMBER+STRICT for new entries. Newly imported items
still require explicit local remote pull enablement before resharing.

`/api/sharing/info` reports `required_tlp_classification` alongside existing
key settings. `/api/sharing/export` reports it in `permissions`. Pull Job History
includes the origin policy and collection diagnostics when supplied by the origin.

Exclusion counts are sequential: status → disabled remote pull → tags → TLP →
deduplication → exported. `excluded_by_tlp` counts items that passed earlier
checks but exceeded the maximum. A record failing tags and TLP is counted under
tags only. Zero received items can be explained by these origin counts.

## Deployment and API

Apply the migrations before serving the updated application:

- `organizations.0037_inbound_share_key_tlp`
- `organizations.0038_inbound_share_key_unclear_tlp`
- `playbooks.0056_capabilityabstraction_tlp_classification`
- `rules.0030_detectionrule_tlp_classification`

```sh
docker compose exec backend python manage.py migrate --noinput
```

For a non-Docker deployment, run `python manage.py migrate --noinput` in the
backend's configured environment. Rebuild/deploy the frontend and restart the
backend with the normal installation procedure. No new environment variables
are required.

GraphQL additions:

- Share keys expose `requiredTlpClassification`.
- `createHefaistosInboundShareKey` accepts optional `requiredTlpClassification`.
- `updateHefaistosInboundShareKeyTlp(id: UUID!, requiredTlpClassification: String!)`
  updates the maximum and returns `success`, `message`, and `key`; only an
  administrator in the key's organization can change it.
- Capability queries and create/update mutations expose/accept `tlpClassification`.
- Rules expose `tlpClassification` as the effective inherited classification.
