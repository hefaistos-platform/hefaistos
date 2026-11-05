# Maieutic ADE question bank

The questions Maieutic asks about adversarial (ADE) gaps. Status: the format, validator and a
first batch of four questions exist; the remaining twelve follow the same format.

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

## Shipped questions (first batch)

| ADE id | Topic | Asked when the design... |
|---|---|---|
| ADE2-01 | Method/Binary | names a specific tool, command or API |
| ADE2-02 | Versioning | assumes a version or platform, or names a specific tool |
| ADE3-01 | Process Cloning | identifies behaviour by process or binary name |
| ADE3-04 | Event Fragmentation | expects several text conditions in one event |

In Expert mode every question is asked regardless of the design.

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

Design flags the planner can derive from the design answers: `names_specific_tool`,
`matches_process_name`, `multi_condition_single_event`, `version_or_platform_specific`.

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

## How selection works

Selection is plain code, not the AI: `questions_for_design(flags, expert_all=False)` returns the
questions whose flags match, in ADE id order, each with the reason it was asked
(`design:<flag>`, `always` or `expert_all`). The same design always gives the same questions.
