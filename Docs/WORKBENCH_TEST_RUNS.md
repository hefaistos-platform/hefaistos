# Recording a test run in a Workbench

Part 5 of a Workbench, **Expected Telemetry & Validation**, has a place to record what happened when you
ran the positive test: was the test executed, and did the rule fire.

## What it is, and what it is not

- **It is your own report.** HEFAISTOS does not run the test or the rule against telemetry. You run it in
  a lab and write down what you saw.
- **Each record is added, never edited.** A record keeps who wrote it, when, whether the rule fired, your
  notes and which version of the rule text it was made for. A wrong record is corrected by adding a newer one.
  The latest 20 are kept, newest first.
- **It changes nothing else.** The Workbench version, its `updated_at` and its test status are untouched.
  The test status field belongs to the CI/CD pipeline; a record here never overwrites it.

## How to record one

1. Run the test on a test host, using the simulation steps above.
2. Tick **Test executed**. **Rule fired** only becomes available after that, because a rule cannot fire in a
   test that was not run. A run that did not happen is not recorded.
3. Add notes if useful (artifacts observed, rule or alert ID, correlation IDs) and press **Record test run**.

"Executed, rule did not fire" is a valid and useful result.

## Reading the list

Each entry shows **Rule fired** or **Rule did not fire**, the person and the time. An entry marked
**The rule changed after this run** was recorded for an earlier rule text: test again before relying on it.
A change that only touches whitespace does not count as a change.

A Workbench that has not been saved yet shows "Save the Workbench first".

## Sharing and files

Workbench export files carry the records (outcome, notes and time) **without the username**, and importing a
file restores them. Updating a Workbench from an older file that has no records keeps the ones you already have.
Negative tests of an accepted limitation are a separate panel; see [README_MAIEUTIC.md](README_MAIEUTIC.md).
