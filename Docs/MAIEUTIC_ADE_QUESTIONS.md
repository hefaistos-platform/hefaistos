# Maieutic ADE question bank

The questions Maieutic asks about adversarial (ADE) gaps. Status: the format, validator and all
16 ADE questions exist (one per upstream subcategory). Questions for the Summiting the Pyramid
(STP) robustness block are separate and not written yet. Nothing asks these questions yet; the
planner that derives the design flags and the question flow are later phases.

Maieutic is Socratic. These questions are asked of the **user**, about their **hypothesis and
planned detection design**. The user types every answer. The AI may rephrase a question or
challenge a vague answer, and it never writes an answer. The generated rule is the final
product, so no question treats a rule as the starting point.

There is no approval step in the user's process and no approval workflow for this content: the
files are versioned in the repository and reviewed like any other code change.

## Where things are

| Path | What |
|---|---|
| `backend/ai_assistant/maieutic_content/ade_questions/*.yaml` | One file per ADE subcategory |
| `backend/ai_assistant/maieutic_questions.py` | Loader, validator, deterministic selection, placeholder rendering |
| `backend/ai_assistant/tests/test_maieutic_questions.py` | Tests that enforce the rules below |

## Shipped questions

| ADE id | Topic | Asked when the design... |
|---|---|---|
| ADE1-01 | Substring Manipulation | matches exact text the attacker can write (`matches_attacker_controlled_string`) |
| ADE1-02 | Normalization Asymmetry | compares or joins the same value across sources (`correlates_events_or_fields`) |
| ADE2-01 | Method/Binary | names a specific tool, command or API (`names_specific_tool`) |
| ADE2-02 | Versioning | assumes a version or platform, or names a specific tool |
| ADE2-03 | Locations | names folders, registry keys, URLs or regions (`names_specific_location`) |
| ADE2-04 | File Types | names file types or extensions (`names_file_types`) |
| ADE3-01 | Process Cloning | identifies behaviour by process or binary name (`matches_process_name`) |
| ADE3-02 | Aggregation Hijacking | relies on counts, thresholds or new-item logic (`uses_threshold_or_baseline`) |
| ADE3-03 | Timing and Scheduling | relies on time windows or frequency (`uses_time_window`) |
| ADE3-04 | Event Fragmentation | expects several text conditions in one event (`multi_condition_single_event`) |
| ADE3-05 | Lineage Spoofing | relies on which program started which (`relies_on_parent_process`) |
| ADE3-06 | Limit Saturation | joins, groups or sorts large volumes (`relies_on_join_or_grouping`) |
| ADE4-01 | Gate Inversion | excludes activity as harmless (`plans_exclusions`) |
| ADE4-02 | Conjunction Inversion | has a condition the attacker can set (`uses_attacker_settable_value`) |
| ADE4-03 | Incorrect Expression | combines several conditions (`combines_multiple_conditions`) |
| ADE4-04 | Field Mismapping and Semantics | **always**, because every design depends on fields being present |

In Expert mode every question is asked regardless of the design.

A new upstream subcategory has no question until someone adds a file for it. A test fails
if an upstream id in the list above has no question or has two.

## A question file

| Field | Shown to user | Purpose |
|---|---|---|
| `id`, `ade_id`, `version` | no | `id` is `ade-q-` plus the lower-case ADE id; bump `version` on any wording change |
| `question` | yes | Open-ended, about the user's plan. May contain `{placeholders}` |
| `why_we_ask` | yes | One or two sentences |
| `hints.where_to_look` | on request, step 1 | Where to find the information |
| `hints.how_to_look` | on request, step 2 | How to test or inspect it |
| `hints.worked_example` | on request, step 3 | `technique` and `text`; must use a technique other than the user's and must not reveal their answer |
| `weak_answer`, `strong_answer` | yes | What "specific enough" looks like |
| `glossary` | yes | `term` and `meaning` pairs |
| `applies_when` | no | `always`, or `design_flags_any` with a list of flags |
| `placeholders` | no | Name to plain-language fallback, used when the user has not given that wording yet |
| `checklist` | no | What a good answer covers. Used only to flag a vague answer, which is advisory and never blocks |

Design flags the planner can derive from the design answers are listed in `DESIGN_FLAGS` in
`maieutic_questions.py` and in the table above. A test fails if a flag is defined but no question
uses it. Deriving the flags from the user's answers is not built yet.

## Rules the validator enforces

A file that breaks one of these fails the test suite.

1. The question is open-ended: it may not start with is, are, do, does, can, could, would, will,
   should, has, have and similar yes/no openers, and must end with a question mark.
2. No user-facing text may say "the rule", "your rule", "the query" or "your detection rule".
   Ask about the hypothesis or the design.
3. Hints have exactly three rungs, in order: where to look, how to look, worked example.
4. The worked example names a technique.
5. Every `{placeholder}` is declared and has a fallback phrase.
6. `applies_when` uses only known flags; the checklist has at least two items.
7. The id matches the ADE id and each ADE id has one file.

## Adding or changing a question

1. Copy an existing file, name it `adeN-NN-short-name.yaml`.
2. Write the question about the user's plan. Test it by reading it aloud as a junior analyst
   who has never seen the framework.
3. Run `python manage.py test ai_assistant.tests.test_maieutic_questions`.
4. Changing wording of an existing question: bump `version`. Sessions record the version the
   user answered, so old answers stay interpretable.

## Planner, answers and the AI check

`maieutic_planner.py` turns the user's structured design (match elements, exclusions,
thresholds, correlations) into design flags and then into the list of questions, with no AI.
It is biased toward asking: a surplus question costs the user a "not applicable"; a missing one
hides a gap. Each planned question carries `design_refs` that point at the user's own design
items, and `{design_observable}` is filled with the user's own wording.

Answers are stored by `record_ade_answer` in the session ledger with the question version,
the user's text, a disposition (handled in design, accepted limitation, covered by another rule,
not applicable, or unknown), the hint rungs used and the snapshot. Only "I do not know yet" may
have empty text. If a question file is later changed, answers given to the older version show as
stale and are asked again.

`maieutic_questioner.py` runs the advisory check. The AI may flag an answer as answered, vague
or contradicting the design, and may ask one follow-up question. It cannot supply answers, and
this is enforced in code as well as in the prompt (`maieutic.evaluate_answer`): a follow-up must
be a single open-ended question and may not contain a content word absent from the question,
checklist, design and the user's own answer, otherwise it is replaced by a fixed neutral one.
The check never blocks saving, and a provider error just means "not evaluated".

## How selection works

Selection is plain code, not the AI: `questions_for_design(flags, expert_all=False)` returns the
questions whose flags match, in ADE id order, each with the reason it was asked
(`design:<flag>`, `always` or `expert_all`). The same design always gives the same questions.
