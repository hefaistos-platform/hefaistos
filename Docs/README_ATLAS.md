# MITRE ATLAS in HEFAISTOS

This document explains what the ATLAS integration does, why it exists, and how the pieces fit together in the current HEFAISTOS flow.

## What ATLAS is

MITRE ATLAS is MITRE's framework for adversary behaviors and campaign patterns in AI and machine-learning systems. In HEFAISTOS, ATLAS is treated as a framework dataset similar to the existing ATT&CK / ADE / Chokepoints import pipeline.

The purpose is not to build a separate browsing product for ATLAS. Instead, the app imports upstream ATLAS data once, exposes it through the platform API, and reuses it in the existing workbench and framework-update workflows.

## Why it is in HEFAISTOS

HEFAISTOS already centralizes framework data so other parts of the app can reuse it consistently:

- framework import and version tracking
- GraphQL access for downstream consumers
- UI controls for administrators to trigger imports
- workbench and analytics surfaces that can reference a framework technique without custom ad hoc logic

ATLAS fits this model because it provides a structured taxonomy that downstream tools and analysts can query without re-parsing YAML or hitting the upstream GitHub repository every time.

## Core behavior

The ATLAS integration includes four connected pieces:

1. Import and persistence of upstream ATLAS YAML data
2. Async job tracking and versioning for those imports
3. GraphQL access to imported ATLAS objects
4. Workbench linkage so an analyst can associate a workbench with a selected ATLAS technique

## Data model

The imported objects live in `backend/platform_data/models.py` and are centered on these models:

- `AtlasTactic`
- `AtlasTechnique`
- `AtlasMitigation`
- `AtlasCaseStudy`
- `AtlasRelationship`
- `AtlasImportJob`

These objects store the upstream ATLAS taxonomy, metadata, references, and the import execution state. This allows HEFAISTOS to keep a stable local copy of the framework even when upstream content changes.

## Import flow

The import pipeline is built around the same pattern as other framework loaders:

- fetch upstream repository metadata
- parse only the newest upstream ATLAS release (resolved from `dist/manifest.yaml`; `dist/ATLAS-latest.yaml` is a git symlink and cannot be fetched raw). Older releases, the deprecated `dist/ATLAS.yaml` and CI files are never imported, so retired objects cannot appear as current. The stored version stays the commit SHA so the update check keeps working
- import relationships from the upstream `relationships:` section (entries have no `id` and use hyphenated keys such as `relationship-type`, `step-id`, `leads-to`)
- normalize the data into HEFAISTOS models
- record a statusful import job
- expose the updated counts through GraphQL

Key implementation points:

- `backend/platform_data/atlas_sync.py` resolves upstream repo metadata / revision data
- `backend/platform_data/management/commands/import_atlas_framework.py` performs the parse + import
- `backend/platform_data/tasks.py` runs the async execution path and status updates

The UI triggers this through the framework update page, which shows source repo, revision status, counts, and prior import jobs.

## GraphQL access

The GraphQL layer in `backend/platform_data/schema.py` exposes the imported ATLAS objects to the rest of the app:

- `atlasCoverageSummary`
- `atlasTactic`, `atlasTactics`
- `atlasTechnique`, `atlasTechniques`
- `atlasMitigation`, `atlasMitigations`
- `atlasCaseStudy`, `atlasCaseStudies`
- `atlasRelationship`, `atlasRelationships`
- `atlasImportJob`, `atlasImportJobs`
- `latestAvailableAtlasRevision`
- `runAtlasImport`

This gives downstream features a stable API contract instead of direct data access to raw import logic.

## Workbench integration

The workbench model in `backend/playbooks/models.py` now supports a selected ATLAS technique through `atlas_technique`, and the GraphQL workbench type exposes it as `atlasTechnique`.

This is intentionally lightweight and integrated into the existing workbench flow rather than implemented as a separate ATLAS-specific page. The user experience is: pick a technique in the existing workbench strategy area, and the selected ATLAS frame is then persisted to the workbench.

This design matches the repo’s direction: avoid building a standalone ATLAS browser unless product requirements demand it. Instead, use ATLAS as a framework relationship for import, analytics, and coverage surfaces already used in the app.

## Frontend experience

The relevant frontend pieces are:

- `frontend/src/components/framework/AtlasFrameworkSection.tsx` for the framework update/import UI
- `frontend/src/pages/FrameworkUpdatesPage.tsx` for registration in the framework updates page
- `frontend/src/components/playbook/DetectionStrategy.tsx` for ATLAS technique search / selection in the workbench strategy flow
- `frontend/src/pages/PlaybookWorkbench.tsx` to wire the selected ATLAS technique into the workbench mutation flow

This ensures the feature is discoverable in the existing admin and workbench experience without creating a new dedicated page.

## Why this is the right scope

The ATLAS feature is valuable as a framework import and integration layer, but it is not a full threat-modeling workflow by itself. The workbench still primarily reflects ATT&CK-based detection strategy patterns; ATLAS is added as an additional framework dimension and integration point.

This keeps the implementation aligned with the rest of HEFAISTOS:

- maintainable framework import pattern
- governed GraphQL access
- reuse in the same surfaces analysts already use
- no unnecessary standalone UI unless a clear product requirement pushes for it

## Files to review

- `backend/platform_data/models.py`
- `backend/platform_data/schema.py`
- `backend/platform_data/atlas_sync.py`
- `backend/platform_data/management/commands/import_atlas_framework.py`
- `backend/platform_data/tasks.py`
- `backend/playbooks/models.py`
- `backend/playbooks/schema.py`
- `frontend/src/components/framework/AtlasFrameworkSection.tsx`
- `frontend/src/components/playbook/DetectionStrategy.tsx`
- `frontend/src/pages/PlaybookWorkbench.tsx`

## Operational note

The ATLAS import is intended to be safe and observable: it runs as an async job, preserves job logs, and exposes revision/status information so operators can validate upstream drift before promoting updated content into active use.
