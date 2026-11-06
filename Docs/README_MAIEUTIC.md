# Maieutic in HEFAISTOS

Maieutic is HEFAISTOS's guided way to go from a detection **hypothesis** to a designed, testable
detection. You start from what you think an attacker does and how you plan to detect it, answer
questions in your own words, and finish by creating a Workbench, optionally with a generated rule.
The rule is the result of the session, never its starting point.

Step-by-step example with every value entered: [HOWTO_MAIEUTIC.md](HOWTO_MAIEUTIC.md).

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
| Capability Library entries you picked, and the focus layer | the Workbench's selected capability abstractions and detection focus layer |
| harmless look-alikes and planned exclusions | false positives |
| evasion points you accepted or left to another detection | blind spots |
| triage, response, alert trigger, severity, test scenario and expected result | the matching fields |
| enrichment, containment and notification steps | the matching step lists (only when you wrote some) |
| the evasion points you accepted as limitations | one negative test each (see below) |
| time window, threshold, count-by field, suppression | the matching tuning fields |
| related events | downstream correlation (scope text) |
| the questions and your own answers | conversation history |
| the session's TLP | TLP |

The Workbench only receives what you established in the session. Points you did not know or did not
reach, and what is still left to do in the session, are never written into it; they stay in the session
record.

Not filled in by a session: telemetry requirement tags (they come from the separate Telemetry
Tagging step and are never guessed), robustness level (the Workbench evaluates it itself under
VALUATION). Capability Library entries and the focus layer are copied only if you picked them in the design
step; nothing is chosen for you.

## Capability Library and focus layer

In the design step (stage 3) you may pick entries from the Capability Library for the technique you chose in
step 1, and one focus layer (Tool / Binary, API / Export, COM / IPC, Registry Object, Protocol, Process
Behavior or Network Behavior).

- **It is optional.** With no pick, the Workbench gets no entries and no focus layer, as before.
- **It only steers the rule generator.** The generator already reads these two fields of a Workbench; the
  entries' purpose, known evasions, observables and telemetry are added to its prompt, together with the
  focus layer. A pick does not answer, skip or change any evasion question.
- **Entries are offered only for the chosen technique**, from your organization's library and the shared
  baseline. Without a technique, the entries are not offered but you may still set a focus layer.
- **Checked again when the Workbench is created.** Entries of another organization, of another technique
  or deleted since are not attached. If you change the technique after picking, the step warns that the
  earlier picks will be ignored.
- **Robustness is not set by it.** The Workbench evaluates robustness under VALUATION, and the library's
  own robustness values are not copied into the session.

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

## Negative tests

A negative test checks the opposite of the usual test: that the rule stays **silent** on something you
accepted as a limitation. Each evasion point you answered with "accept as a limitation" gets one.
Points marked "I do not know yet", "covered by another rule" or "not applicable" do not, because there
is nothing you decided to leave uncovered.

- **In the session (stage 5)** you may write the steps for each one. Leave them empty to get a
  starting template built from the question and your own answer (no AI is involved, and the template
  is marked so you know to adapt it).
- **In the Workbench (Part 5, before Atomic Red Team)** you see the steps, the expected result ("No
  alert is raised.") and a selector for what happened: *Not run yet*, *No alert, as accepted* or
  *Alert raised unexpectedly*, plus notes.
- **Nothing is run for you.** HEFAISTOS does not execute rules against telemetry. You run the test in a
  lab, before or after finishing the session, and record what you saw.
- **Recording a result changes nothing else.** It does not alter the Workbench version, its test
  status or Blind Spots, and it is not blocked by the session being finished.
- **Alert raised unexpectedly** shows a notice under Blind Spots: the rule covers something listed
  there. Nothing is rewritten; decide whether to fix the rule or the Blind Spots entry.
- **Editing the steps clears a recorded result**, because the result belongs to the old steps.
- **If the rule text changes after a result was recorded**, the result is flagged as out of date.
- "Not run yet" is the state of the list. It is never shown as a gap or counted against the rule.

## Where your decisions went in the rule

When a rule is generated from a session, every decision is numbered (`M` must implement, `H` must
handle, `L` accepted limitation) and the AI that writes the rule reports for each one whether the
rule implements it and where. The Workbench shows this under the banner as "Where your decisions
went in the rule".

Read it as a check to review, not as proof:

- It comes from the same model that wrote the rule, so verify the entries you care about against
  the rule itself.
- "Not reported" means the model skipped that decision. It does not mean the decision was
  implemented.
- A red "Rule claims to cover an accepted limitation" means the rule contradicts something you
  chose not to cover. Edit the rule or generate again.

If the rule was automatically repaired after validation, the panel says so, because the reported
locations then refer to the earlier text. The report is stored with the generation result only. It is not written into Workbench fields.

## Sessions

- Answers save as you go; resume any time from the Maieutics tab.
- A finished session stays in your list, read-only. Its TLP is locked at that point, so choose it
  before you finish. The Workbench has its own TLP, which you can still change.
- The author, an organization admin or a superuser can delete a session. Deleting it never deletes
  the Workbench it created. Admins see only metadata (who, when, status) for other people's sessions.
- **Sharing.** On a finished session you can switch on sharing in the Maieutics tab (off by default).
  Trusted peers with a suitable key can then pull the design record and your evasion answers, within
  your TLP limit. The Workbench, its rule and its conversation history are not part of it. Copies
  you pull from a peer appear as "Imported from ...", read-only, and cannot be shared further. Details,
  key behaviour and version compatibility: [instance-sharing-tlp.md](instance-sharing-tlp.md).

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
