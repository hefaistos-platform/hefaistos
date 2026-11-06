# Maieutic components

The Maieutic guided design flow. Behaviour, stages and rules: `Docs/README_MAIEUTIC.md`.

| File | Purpose |
|---|---|
| `MaieuticSessionsTab.tsx` | Workbench Hub **Maieutics** tab: list, start, resume, read-only view, delete, share preference. |
| `../../pages/MaieuticSessionPage.tsx` | The six-stage session screen at `/maieutics/:draftId`. |
| `MaieuticFormParts.tsx` | Shared form controls for the stages. |
| `MaieuticAdeStage.tsx` | Stage 4 evasion questions with hints and the advisory answer check. |
| `MaieuticGenerationBanner.tsx` | Workbench banner showing rule generation queued by a session. |
| `MaieuticCapabilityPicker.tsx` | Stage 3 Capability Library entries and focus layer. |
| `MaieuticWordingHelp.tsx` | Optional "Help me word this" suggestion, accept, discard and restore for four text fields. |
| `MaieuticFrameworkDrift.tsx` | Note in stage 4 when the ADE framework snapshot changed during a session. |
| `MaieuticNegativeTests.tsx` | Stage 5 steps for the negative test of each accepted limitation. |
| `MaieuticTraceabilityPanel.tsx` | Workbench panel "Where your decisions went in the rule". |
| `../playbook/TestRunRecord.tsx` | Workbench Part 5 form and list for recorded test runs. |
