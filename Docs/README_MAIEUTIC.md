# Maieutic Engine in HEFAISTOS

This document explains what the Maieutic Engine is, how it works, and how to use it effectively inside a Workbench.

## What Maieutic Engine Is

Maieutic Engine is HEFAISTOS's guided detection-engineering assistant.

It does not try to replace analysts. Instead, it helps analysts refine detection ideas through structured Socratic questioning across a staged workflow:

1. Hypothesis
2. Interrogation
3. Robustness
4. Playbook
5. Review

The goal is to move from rough intent to a usable, testable, and operationally grounded detection package.

## Why It Exists

Detection ideas often stall in one of these ways:

1. The idea is too broad ("detect bad PowerShell") and not testable.
2. Missing telemetry details create false positives later.
3. Playbook steps are incomplete for triage and response.
4. Knowledge is captured in chat but not merged into Workbench fields.

Maieutic Engine addresses these gaps by making users answer concrete, stage-specific questions and then staging the output for controlled import into the Workbench.

## How It Works

### 1) UI Workflow

Maieutic opens as a modal from Playbook Workbench and guides users through the five stages.

- Required fields control stage progression.
- AI readiness score is shown as advisory coaching, not a hard blocker.
- Users can continue when required fields are complete, even if AI recommends more refinement.

### 2) Context-Aware Start

When Workbench context exists, Maieutic starts with it:

- Selected ATT&CK technique (for example `T1218.005`)
- Technique name
- Detection focus layer
- Existing Workbench goal/context
- Selected capability abstractions

This context is used to:

1. Pre-seed Hypothesis fields (when still empty)
2. Shape kickoff prompts
3. Ground backend AI questioning from the first turn

If no Workbench context is available, Maieutic starts from blank fields and asks baseline setup questions.

### 3) AI Interaction Model

Each turn returns structured JSON from backend AI providers through GraphQL (`maieuticQuestion`), including:

1. Teaching note
2. One Socratic question
3. Answer template
4. Completion check
5. Field suggestions
6. Autofill candidates

The assistant is tuned by challenge level:

1. Light: guided coaching mode for less-experienced users
2. Standard: balanced depth for day-to-day work
3. Expert: advanced challenge mode for experienced detection engineers

### 4) Knowledge Grounding

Backend grounding combines:

1. Current user message
2. Form context
3. Workbench context (including ATT&CK technique)
4. Active Detection Chokepoints snapshot (if available)

This reduces generic answers and improves ATT&CK-aware questioning.

### Relationship to Qdrant RAG Template Grounding

Maieutic and rule-template RAG are complementary but different systems:

1. Maieutic focuses on analytical quality (hypothesis clarity, evidence, robustness, playbook readiness).
2. Qdrant RAG template grounding focuses on query-quality generation (syntax/schema/query idioms for KQL/EQL/SPL).

Current implementation note:

- Maieutic questioning itself does not directly call template retrieval from Qdrant.
- Qdrant template grounding is used in the AI rule generation/improvement/reuse flows in Workbench.

### 5) Repeat-Question Guard

If the generated Socratic question is too similar to the previous AI question, backend logic replaces it with a gap-focused question tied to the current missing item/stage.

This prevents loop behavior where users see near-identical prompts repeatedly.

## Stage Rules

### Hypothesis

Required:

1. Detection Intent
2. Technical Capability

Purpose:
- Define the behavior and scope to detect, not just tool names.

### Interrogation

Required:

1. At least one Q&A log entry

Purpose:
- Capture field-level evidence and technical uncertainty.

### Robustness

Required:

1. Data Quality
2. False Positive Rate
3. Coverage & Blind Spots
4. Overall Justification

Purpose:
- Stress-test resilience and identify operational limits.

### Playbook

Required:

1. Manual steps or SOAR playbook content

Purpose:
- Turn detection into usable response actions.

### Review

Required:

1. Prior stages must satisfy required fields

Purpose:
- Confirm readiness before staging data for import.

Note:
- AI may still recommend additional improvements during Review, but these are advisory.

## How to Use Maieutic Engine

1. Open an existing Workbench.
2. (Recommended) Set ATT&CK technique and strategy context first.
3. Launch Maieutic Engine from the Workbench toolbar.
4. Complete fields in each stage and use AI suggestions/autofill where helpful.
5. Move through stages using `Next` once required fields are complete.
6. In Review, choose import toggles (Hypothesis, Q&A, Robustness, Playbook, Rule, Synthesis).
7. Submit to stage Maieutic output.
8. Apply staged output to Workbench from the review banner/panel.

## Output Mapping to Workbench

When applied, Maieutic output maps as follows:

1. Hypothesis -> `goal` (append)
2. Q&A log -> `technicalContext` (append)
3. Robustness -> `blindSpots` and `falsePositives` (append)
4. Playbook design -> `responsePlaybook` (append)
5. Detection rule -> `detectionRule` (overwrite with `format + rule`)
6. Review synthesis -> `triageGuidance`, `testScenario`, `testExpectedOutput`, plus optional SOAR/testing extras

## Design Principles

1. Analyst-first: AI assists, analyst decides.
2. Structured progress: stage requirements keep output usable.
3. Context grounding: prefer ATT&CK + chokepoint-aware prompts.
4. Safe imports: stage before apply; avoid silent destructive writes.
5. Practical coaching: actionable next-best step rather than vague feedback.

## Troubleshooting

### "I am stuck and questions repeat"

- Confirm required fields for the current stage are filled.
- Ask AI: `What am I still missing?`
- Use challenge level `Light` if prompts are too strict.
- Ensure Workbench technique/context is set before opening Maieutic.

### "No useful context is used"

- Verify the Workbench has selected ATT&CK technique and saved strategy context.
- Re-open Maieutic so kickoff prompt includes updated Workbench context.

### "Output imported but fields look partial"

- Check import toggles in Review.
- Re-run Review synthesis and apply again if missing triage/testing sections.
