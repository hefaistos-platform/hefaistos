# Capability Library

## Overview

The **Capability Library** is a dedicated workspace for managing **Capability Abstraction** items in HEFAISTOS.

It is designed to provide a larger, more effective management experience than Workbench detail while preserving existing Workbench behavior.

## Why this page exists

Before this addition, capability abstraction work was primarily handled via existing flows (including Add Capability Abstraction and Workbench contexts). The Capability Library introduces a focused place to:

- discover capability abstraction items quickly,
- create and edit them with the same core inputs,
- review status and ownership more efficiently,
- prepare for broader lifecycle/governance workflows.

## Scope and compatibility

### What stays the same

- The **core Capability Abstraction input model** remains aligned with the existing **Add Capability Abstraction** form.
- Existing **Workbench detail behavior remains unchanged**.
- Existing payload contracts are preserved (no intentional breaking API changes).

### What is new

- A dedicated **Capability Library** page/route.
- Navigation entry to access this page.
- A catalog-style management surface for Capability Abstraction items.

## Capability Library: expected content

Depending on role and permissions, users can work with:

- Search for capability abstraction items.
- List/table view of capabilities (for example: name, ID, owner, status, last update).
- Create flow using existing Capability Abstraction inputs.
- Edit flow using the same schema/validation patterns.
- Status/lifecycle visibility using existing state/status fields.
- Optional "used by"/impact hints where currently available.

## Relationship to Workbench

Workbench remains the execution/use context.

Capability Library is the authoring/management context.

If available in your UI build, Workbench may expose a non-invasive **Open in Capability Library** action for advanced capability maintenance.

## User workflow (recommended)

1. Open **Capability Library** from main navigation.
2. Search/filter to find a capability abstraction item.
3. Open item details for update.
4. Edit using the existing Capability Abstraction inputs.
5. Save and validate.
6. Continue using the capability in Workbench as before.

## Notes for maintainers

- Keep Capability Library and Add Capability Abstraction aligned on schema/validation.
- Prefer additive changes to avoid regressions in existing Workbench flows.
- If lifecycle/versioning is expanded in future, avoid introducing incompatible contracts.

## Future enhancements (non-blocking)

- richer dependency/impact mapping,
- explicit draft/publish/deprecate lifecycle controls,
- bulk operations and saved views,
- stronger governance/audit surfaces.
