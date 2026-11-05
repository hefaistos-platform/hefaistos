# Maieutic components

The Maieutic guided design flow. Behaviour, stages and rules: `Docs/README_MAIEUTIC.md`.

| File | Purpose |
|---|---|
| `MaieuticSessionsTab.tsx` | Workbench Hub **Maieutics** tab: list, start, resume, read-only view, delete, share preference. |
| `../../pages/MaieuticSessionPage.tsx` | The six-stage session screen at `/maieutics/:draftId`. |
| `MaieuticFormParts.tsx` | Shared form controls for the stages. |
| `MaieuticAdeStage.tsx` | Stage 4 evasion questions with hints and the advisory answer check. |
| `MaieuticGenerationBanner.tsx` | Workbench banner showing rule generation queued by a session. |

The earlier in-Workbench Maieutic Engine modal, its store slice and its mapping utility were
removed in the MAJOR release that introduced this flow.
