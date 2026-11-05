# Maieutic Engine 3.0: plan and future guide

> **Planned behaviour, not yet implemented** (branch `feat/maieutic-3`). At Phase 7 this
> text, updated to what was actually built, replaces `Docs/README_MAIEUTIC.md`. Field-level
> detail is in `Docs/MAIEUTIC_3_SPEC.md`.

## 1. What it is

Maieutic Engine guides you from a detection idea to a finished Workbench and a generated
rule by asking questions. It does not hand you answers. The rule is the final product, and
it is only as good as the thinking you put in.

Three promises:

1. **It asks, you answer.** On adversarial (ADE) questions the AI never writes the answer.
2. **"I don't know yet" is allowed.** It is recorded, shown, and carried into the Workbench.
3. **You always leave with a Workbench.** There is no dead end.

## 2. Where to find it

Open **Workbench Hub**. There is a **Maieutics** tab next to Workbench, ACH Matrix, ADVOPS
and Machina Velocity Engine. It lists your sessions with name, stage, last update and a
**Continue** button, plus **New session**. The Maieutic Engine is no longer opened from
inside a Workbench.

Sessions autosave after every answer. Closing the window does not lose work.

The tab has two kinds of rows:

- **In progress**: editable, with a **Continue** button.
- **Finished**: the Workbench has been created. The session is **locked and read-only
  permanently**. It stays in the tab as the record of how that Workbench was designed, shows
  its spec, ADE answers and STP decision, and links to the Workbench. It cannot be reopened for
  editing; the Workbench is the editable object.

Only you see your own sessions.

## 3. The six stages

| # | Stage | You decide |
|---|---|---|
| 1 | Hypothesis | ATT&CK technique, goal, every way an attacker could do it |
| 2 | Interrogation | Log sources and fields, benign lookalikes, which fields an attacker controls |
| 3 | Design | What to match, what to exclude and why, windows and thresholds, correlations. Output is a blueprint in words |
| 4 | Robustness | A. How hard your detection is to evade (STP). B. Adversarial questions (ADE) |
| 5 | Playbook and tests | Triage, response, SOAR, test scenario, negative tests |
| 6 | Review and create | Check, pick formats, choose how to finish |

You cannot write code in the engine. You design the detection in words, and the generator
writes the rule from your design.

## 4. Help for beginners

Every question has a help panel:

- **Why am I asked?**
- **Where to look:** concrete places such as Event Viewer channels, Sysmon event IDs,
  Defender tables, and the Log Source and Data Source catalogs.
- **How to look:** steps, such as running the technique in a lab and watching the logs.
- **What a good answer looks like:** a weak and a strong example from a *different* technique.
- **Glossary chips** for terms like parent process or kernel mode.

The **hint ladder** reveals help step by step: a rephrased nudge, then where to look, then a
worked example. It never reveals your own answer. The challenge level controls how open help
is: Light shows it expanded, Expert collapses it.

## 5. Robustness: two separate measures

| | Measures | Scale |
|---|---|---|
| **STP (Summiting the Pyramid)** | How hard the thing you detect is for an attacker to change | Level 1-5 and a telemetry column A/U/K/P/H |
| **ADE** | Whether your detection logic really covers the behaviour, and where it can miss | Per-question answers, no score |

They are never merged into one number.

**STP.** You first answer three plain questions: what does the detection look at, can an
attacker change it without breaking the attack, and where does the log come from. You commit
a level and column with a reason. The engine then shows evidence from your ADE answers, and
the AI suggests a level with reasons. You accept, rewrite, or keep yours with a written
override reason. You see "claimed" and "supported" side by side.

**ADE.** The Adversarial sub-stage asks questions drawn from the Adversarial Detection
Engineering framework. Which ones you see depends on your design and the challenge level:

- **Light:** only those triggered by your design.
- **Standard:** adds design-time questions.
- **Expert:** all.

Each answer gets a disposition: handled in design, accepted limitation, covered by another
rule, not applicable (with reason), or unknown. Which ones are asked is decided by code,
not by the AI. The AI only words the question using your design and challenges a vague answer.

## 6. Finishing

| Button | Result |
|---|---|
| **Create Workbench and generate rule** | Creates and fills the Workbench, closes the engine, starts one generation per selected format |
| **Create Workbench without rule** | Creates and fills the Workbench from what you have, no generation |
| **Save draft and close** | Keeps the session in the Maieutics tab for later (still editable) |

Minimum to create a Workbench: a title, a technique (or an explicit "no technique"), and a
goal. Everything else may be Unknown. The Review screen shows what was captured and what is
unknown before you click.

**Formats.** KQL is always selected. SPL, EQL and Wazuh are optional. AQL is a QRadar
**query**, not a rule. Each format is generated separately from your design, not translated
from the KQL rule. The screen shows per format whether it will be validated.

If generation fails, the Workbench still exists and a banner offers a retry.

## 6b. Finished sessions and sharing

Both "Create Workbench" exits finish the session and lock it at that moment, before rule
generation completes, so the answers the generator reads cannot change underneath it.

A finished session has a **Share** toggle, off by default. When on (and the session's TLP
allows it for the peer's key), it is exported through **Configuration → Instance Sharing** under
a new scope, `MAIEUTIC`. The receiving instance gets a locked read-only copy marked as imported.
Sharing the session and sharing its Workbench are independent.

Details, including the compatibility safeguard for existing sharing keys: `MAIEUTIC_3_SPEC.md`
sections 9b and 9c.

## 7. Generation

Per format: context from your spec, RAG grounding (status recorded), generation of primary,
quick-win and robust variants, validation and repair where enabled, confidence scoring, then a
**traceability table** listing whether each decision appears in the rule. That table is a
check, not a guarantee.

## 8. What lands in the Workbench

See `Docs/MAIEUTIC_3_SPEC.md` section 8 for the field mapping. The session
transcript is saved in a collapsible section. The spec and ADE ledger are saved read-only.

## 9. When ADE changes

ADE is a framework on the **Framework Updates** page, like Chokepoints:

1. Admin imports a snapshot from GitHub (staged).
2. Admin reviews a diff: added, renamed, edited, removed.
3. Our own question text, hints and checklist (the question bank) ship as versioned files in the repository and are reviewed like code. There is no runtime approval step.
4. Admin promotes. Rollback is available.

New upstream items without a question file are listed as "needs a question" and not
asked yet. After a promotion, existing sessions only show new or changed questions as open.

## 10. Limits

- ADE measures false-negative risk in detection logic. It does not measure false positives,
  telemetry health or overall quality, and it cannot certify a rule as complete.
- STP evidence rules are a HEFAISTOS interpretation and need expert review.
- Evaluator feedback is advisory.
- EQL, Wazuh and AQL are not validated by default.
- Checking an existing rule against ADE is a separate, later feature in the rule lifecycle.

---

# Documentation and release plan

## Documents to produce with the implementation

| Document | Action |
|---|---|
| `Docs/README_MAIEUTIC.md` | Replace with the final form of this guide |
| `Docs/MAIEUTIC_CONTENT_AUTHORING.md` | New: how to write question templates, hint kits, rubrics, STP rules |
| `Docs/README_ADE.md` | New: ADE framework import, staging, diff, promote, rollback |
| `Docs/MAIEUTIC_ADE_QUESTIONS.md` | New: question format, rules, how to add or change a question |
| `Docs/capability-library.md` | Update: how entries feed Maieutic |
| `Docs/AI_QUALITY.md` | Update: new Prompt Registry keys, `rule-bundle-v2` |
| `Docs/ENVIRONMENT_VARIABLES.md` | Update if settings are added |
| `Docs/instance-sharing-tlp.md` | Update: add Maieutic sessions to the TLP scope list and to "tags do not apply"; describe the `MAIEUTIC` scope |
| `README.md` | Update links (line ~250) and add ADE guide |
| Decision record | New: what was removed from the Workbench and why |

Rule: a phase is not complete until its documentation is updated in the same change.

## Versioning: MAJOR

Decided by the project owner: this is a **MAJOR** release. Per `Docs/VERSIONING.md`, a breaking commit needs
`BREAKING CHANGE:` in the body or a `!` marker (`feat!:`). The breaking elements:

- Maieutic Engine removed from the Workbench.
- The "apply staged output to an existing Workbench" flow removed.
- Maieutic output model and generator contract change (`rule-bundle-v2`). Whether the GraphQL
  `maieuticQuestion` mutation is kept compatible must be decided in Phase 4.

Commit subjects must describe the change so the generated `Versions/vX.Y.Z/changelog.md`
is useful. The MAJOR bump should happen at the phase that actually removes behaviour (7).

## Phases

Status legend: DONE, PARTIAL, TODO.

1. DONE. Spec and docs (`MAIEUTIC_3_SPEC.md`, this file).
2. DONE. ADE on Framework Updates (`README_ADE.md`).
3. PARTIAL. Question bank: all 16 ADE questions are in `backend/ai_assistant/maieutic_content/ade_questions/` (`MAIEUTIC_ADE_QUESTIONS.md`). STP robustness questions are still TODO.
4. DONE for ADE. Backend: `MaieuticDraft` (author-only, finish lock, sharing toggle, delete rights, admin metadata view); `maieutic_planner.py` (design to design flags to questions, deterministic, no AI); `maieutic_questioner.py` (advisory answer check with a code-level guard against the AI supplying answers); ledger, hint ladder and the `maieutic.evaluate_answer` prompt. GraphQL: `maieuticAdePlan`, `revealMaieuticHint`, `answerMaieuticAdeQuestion`. STP and other stage questioners are TODO.
5. PARTIAL. Frontend (now including the two Create Workbench exits, enabled once the stage 1 minimum exists, and a generation banner on the Workbench page): the **Maieutics tab** (list, create, continue, open read-only, delete, share toggle, admin metadata view) and the **six-stage session screen** at `/maieutics/:draftId` are DONE: autosave per section, technique and Log Source / Data Catalog dropdowns, fields with attacker-control choice, design in words, the ADE question stage with hints and advisory check, response and test fields, review with output formats. TODO in this phase: Capability Library picker and focus layer in stage 3, STP robustness in stage 4, enrichment/containment/notification lists in stage 5, negative tests derived from limitations, per-field AI wording help, the save-draft exit as a separate action.
6. PARTIAL. Create Workbench and generation: DONE: `maieutic_workbench.py` (spec to Workbench mapping, constraint groups, atomic create + lock + queue, server-side write-back that never overwrites user text, status query), constraint block in the generator prompt, worker hook. TODO: `rule-bundle-v2` traceability section (spec 10), STP-derived robustness fields, capability fields.
7. DONE (MAJOR). Old engine removed: Workbench and Playbooks-page buttons, modal, review panel, store slice, mapping util, types, `/api/maieutic/*` endpoints, `maieuticQuestion` mutation, `run_maieutic_questioning` and its helpers. Kept: the Workbench conversation-history viewer (new sessions write to it too). Release bump comes from the `feat!:` commit via CI; `VERSION` is not edited by hand.
8. DONE. Instance Sharing scope `MAIEUTIC` (`organizations/sharing.py`, migration `organizations/0039`, `InstanceSharing.tsx`, `instance-sharing-tlp.md`): export of finished, opted-in, original sessions within the key's TLP maximum; validated, locked, read-only imports that update on re-pull and cannot be re-shared; the `ALL` safeguard (keys with the five original scopes keep pulling `ALL` and are not granted sessions); tolerance for peers that predate the scope. Verified with 25 dedicated tests, each safeguard mutation-checked. Not verified: a real two-instance pull over HTTPS.

## Maieutics tab: notes for Phase 5

The Hub tab state is mapped in two places in `PlaybooksHubPage.tsx` (the initial `useState` and
the `useEffect`), and both fall back to `graphs` for unknown keys. A `maieutics` key must be
added to both, or `?tab=maieutics` silently opens the Workbench tab. The MVE tab uses the same
pattern and is the model to follow.
