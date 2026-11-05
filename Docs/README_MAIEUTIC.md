# Maieutic in HEFAISTOS

Maieutic is HEFAISTOS's guided way to go from a detection **hypothesis** to a designed, testable
detection. You start from what you think an attacker does and how you plan to detect it, answer
questions in your own words, and finish by creating a Workbench, optionally with a generated rule.
The rule is the result of the session, never its starting point.

Design records: [MAIEUTIC_3_SPEC.md](MAIEUTIC_3_SPEC.md) (behaviour) and
[MAIEUTIC_3_PLAN.md](MAIEUTIC_3_PLAN.md) (status). Evasion question content:
[MAIEUTIC_ADE_QUESTIONS.md](MAIEUTIC_ADE_QUESTIONS.md). Framework source: [README_ADE.md](README_ADE.md).

> **Breaking change (MAJOR release).** The earlier Maieutic Engine that opened as a pop-up inside a
> Workbench is gone. See [What was removed](#what-was-removed).

## Where to find it

Workbench Hub, **Maieutics** tab. Start a session there, resume it later, or open a finished one
read-only. There is no other entry point.

## The six stages
1. **Hypothesis**: title, ATT&CK technique (or "none yet"), goal, ways an attacker could do it.
   Also choose how demanding the evasion questions should be (Light, Standard, Expert).
2. **Telemetry**: Log Sources first, then the Data Catalog; the fields you would rely on and
   whether an attacker can control each; harmless look-alikes.
3. **Design**: in words, what the detection looks for, what it ignores, time window and
   thresholds, related events.
4. **Evasion**: questions drawn from the ADE framework, chosen from your own design. You answer
   in your own words, can open three hints one at a time, and can say "I do not know yet".
   An AI check may point out a vague answer; it never writes or fills in an answer for you.
5. **Response**: triage, response, alert trigger, severity, and how you would test it.
6. **Review**: choose output formats (KQL always; SPL, EQL, Wazuh, AQL optional) and see what you
   captured. This is a record of your thinking, not a quality score for the rule.

## Finishing a session

On the Review stage you need only the stage 1 minimum (title, technique or "none yet", goal).
Everything else may stay empty or "I do not know yet".

- **Create Workbench and generate rule** creates the Workbench, locks the session, and queues
  one normal rule generation per chosen format. It needs AI Settings in your profile; without
  them nothing is created and you are told why.
- **Create Workbench without a rule** creates the Workbench only.

Either way the session becomes a read-only record in the Maieutics tab, linked to the Workbench.
Deleting the session later never deletes the Workbench.

What goes where in the Workbench:

| Session | Workbench field |
|---|---|
| title, technique, goal + ways an attacker could do it | title, ATT&CK technique, goal |
| scope notes, planned log sources and fields, design in words and its elements | technical context |
| harmless look-alikes and planned exclusions | false positives |
| evasion points you accepted, left to another detection, or did not know; plus a count of unanswered ones | blind spots |
| triage, response, alert trigger, severity, test scenario and expected result | the matching fields |
| time window, threshold, count-by field, suppression | the matching tuning fields |
| related events | downstream correlation (scope text) |
| the questions and your own answers | conversation history |
| the session's TLP | TLP |

Not filled in by a session: telemetry requirement tags (they come from the separate Telemetry
Tagging step and are never guessed), robustness level, capability abstractions and focus layer
(those stages are not built yet).

**How the rule is generated.** The normal generator runs, with its reference retrieval, validation
check and repair attempts. Your session adds a block of design decisions to its prompt: what the
rule must implement, which evasion points you say the design already handles (it must make that
true), and the limitations you accepted (it must not claim to cover them). The finished rule is
stored in the Workbench by the server, so you can leave the page. KQL goes to the detection rule;
SPL, EQL, AQL and Wazuh go to the matching platform slots. A result is never written over text you
have entered yourself in the meantime. If a draft fails the rule checks it is not stored and the
Workbench banner says so.

This document explains what the Maieutic Engine is, how it works, and how to use it effectively inside a Workbench.

## How the AI is used

The AI may rephrase a question, point out that an answer is vague, and suggest a follow-up. It never
writes, completes or approves your answer, and the check never blocks you. A guard rejects follow-ups
that bring in content you did not write. Your answers stay exactly as you typed them.

The evasion questions come from the ADE false-negative framework (4 categories, 16 subcategories),
chosen from your own design. ADE covers *what your rule could miss*. It is a different thing from
robustness against an attacker changing their behaviour, and the two are never merged into one score.

## Sessions

- Answers save as you go; resume any time from the Maieutics tab.
- A finished session stays in your list, read-only. Its TLP is locked at that point, so choose it
  before you finish. The Workbench has its own TLP, which you can still change.
- The author, an organization admin or a superuser can delete a session. Deleting it never deletes
  the Workbench it created. Admins see only metadata (who, when, status) for other people's sessions.
- The transcript of your questions and answers is not part of anything shared from a session.

## What was removed

| Removed | Use instead |
|---|---|
| The Maieutic Engine button in the Workbench header and on the Playbooks page | Workbench Hub, Maieutics tab |
| Stage-and-apply review panel inside a Workbench | Creating the Workbench from the session |
| The five-stage modal (Hypothesis, Interrogation, Robustness, Playbook, Review) | The six stages above |
| API: `POST /api/maieutic/validate`, `/hints`, `/ai` and the `maieuticQuestion` GraphQL mutation | The `maieutic...` queries and mutations of the new flow (see the schema) |

Nothing stored is deleted. Workbenches that were filled by the old engine keep their data, and their
saved conversation is still viewable in the Workbench ("View Maieutic Conversation History"). Browser
drafts of the old engine lived only in the browser and are not carried over; start a new session if
you had one in progress.

## Troubleshooting

**"Create Workbench is disabled."** Stage 1 needs a title, a technique or the choice "none yet", and
a goal. The Review stage lists what is missing.

**"Create and generate failed with an AI provider message."** Rule generation needs AI Settings in
your profile. Nothing was created; add the settings or use "Create Workbench without a rule".

**"The rule never showed up in the Workbench."** The banner on the Workbench says whether generation
is still running, failed, or produced a draft that did not pass the rule checks (such drafts are not
stored). Generate again from the rule editor and read the validation notes. The worker process has
to be running.

**"A rule I generated replaced nothing I typed."** That is intended: results are never written over
text you entered yourself.
