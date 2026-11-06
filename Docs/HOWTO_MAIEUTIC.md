# How to use the Maieutic Engine: LSASS dump walk-through

This is a worked example you can follow click by click. It records a real test session run on a live
HEFAISTOS instance as an administrator, from an empty Maieutics tab to a generated KQL rule. Use it
alongside the [Maieutic guide](README_MAIEUTIC.md), which explains the ideas and the rules.

The example detects credential dumping from LSASS (ATT&CK T1003.001) with `rundll32.exe` and
`comsvcs.dll`. Everything in `code style` below is what was typed or picked.

## Before you start

- You need the ADMIN or ANALYST role. Only you can see your own sessions.
- For the **Create Workbench and generate rule** exit you need an AI provider: your own key, or an
  organization provider with "use organization AI" switched on in your profile. Without one you can
  still use **Create Workbench without a rule**.
- An administrator should have imported and promoted an ADE snapshot (Framework Updates). Without one
  the Evasion stage has no framework to draw questions from.

## Step 1: Start a session

1. Open **Workbench Hub** in the left menu and select the **Maieutics** tab.
2. Select **New session**.
3. **Working title:** `LSASS memory dump via comsvcs MiniDump`. This title also becomes the stage 1
   title. You can change it later while the session is in progress.
4. **TLP classification:** leave `TLP:UNCLEAR` or choose one. It is locked when the session finishes.
5. Select **Create**. The six-stage screen opens. Everything you type is saved automatically; the
   header shows "All changes saved". You can leave and resume from the Maieutics tab.

## Step 2: Hypothesis (stage 1)

Say what you want to catch and why. Nothing here is query syntax.

| Field | What was entered |
|---|---|
| Working title | already filled from step 1 |
| ATT&CK technique | typed `T1003.001` in the search box and picked "T1003.001 OS Credential Dumping: LSASS Memory". The checkbox "I have not chosen a technique" is the other valid choice |
| Goal | `Detect credential dumping from LSASS process memory on Windows servers, so that a hit means an attacker is extracting credentials, not that a backup agent ran.` |
| Ways an attacker could do this | two entries, added with **Add a way**: `rundll32.exe loading comsvcs.dll with the MiniDump export against the lsass.exe process id` and `procdump.exe -ma lsass.exe, or Task Manager 'Create dump file' on the lsass.exe process` |
| Notes on scope | `Out of scope: offline attacks on a copied ntds.dit or SAM hive, and dumping on Linux hosts.` |
| How demanding | `Standard: recommended`. Light asks only what your design clearly raises; Expert asks every evasion topic. You can change it at any time |

Select **Next**.

## Step 3: Telemetry (stage 2)

What evidence would the behaviour leave?

1. **Where would the evidence be logged?** Click the search box and type `sysmon`. The picker searches
   the Log Sources catalog first, then the Data Catalog. Choose `WinEventLog:Sysmon - EventCode=10
   (Windows)`, the process-access event. (On the test instance only Data Catalog entries matched.)
2. **Fields you would rely on.** Picking a Data Catalog entry does not fill fields in, so add them with
   **Add a field by hand**. For each one, say whether an attacker can control it:

   | Field | Name in your SIEM | Attacker can control it? |
   |---|---|---|
   | Process being accessed | `TargetImage` | No |
   | Permissions requested on the process | `GrantedAccess` | Partly |
   | Process doing the access | `SourceImage` | Yes (a binary can be renamed) |

   The choices are Yes, Partly, No, I do not know.
3. **Harmless activity that looks similar:** `The nightly backup agent reads lsass.exe memory to
   capture credential state; it runs as SYSTEM from a signed vendor path.`

Select **Next**.

## Step 4: Design (stage 3)

Describe the detection in words. Your answers here decide which evasion questions you get.

1. **What will it look for?** Add one entry per condition. Each has the text, a type ("It is...") and
   whether an attacker can change it:
   - `rundll32.exe loads comsvcs.dll and calls the MiniDump export`: type "Text in a command line",
     changeable "Yes, with some effort".
   - `The process being accessed is lsass.exe, and the permissions requested allow reading its
     memory`: type "A file or process name", changeable "No".
2. **What will it ignore?** Ignored: `Access to lsass.exe by the signed vendor backup agent`. Because:
   `It reads LSASS memory every night as part of a documented backup job.`
3. Time window, thresholds and relations were left empty because the rule fires on a single event.

Select **Next**.

## Step 5: Evasion (stage 4)

The screen says how many points are open ("10 of 10 points still open"). The questions come from your
own design and the active ADE snapshot; the AI does not choose them. The ADE4-04 question about log
fields is asked every time.

For each point:
1. Select it to open it. Read the question and, if useful, "Why we ask this" and the examples of thin
   and thorough answers.
2. If you are stuck, open the hints one at a time: **1. Where to look**, **2. How to look**, **3. A
   worked example**. Hints never contain the answer.
3. Pick a status: *My design already handles this*, *I accept this as a limitation*, *Another
   detection covers this* or *This does not apply to my design*. Optionally pick which part of your
   design it concerns.
4. Write the answer in your own words and select **Save answer**. Nothing is filled in for you.
   Selecting **I do not know yet** is also a valid answer.
5. An AI check may add a note or a follow-up. It is advisory and never blocks saving. If it did not run,
   the screen says "Your answer was stored as written. It was not checked."

In the test session:
- The first point asked how an attacker could write the same text differently. Status *I accept this
  as a limitation*, answer: `The rule matches the literal comsvcs.dll and MiniDump text. An attacker can
  call the export by ordinal (#24) or rename the DLL copy, and my rule would miss it. I accept that for
  now and will add a process-access rule on lsass.exe as the second layer.`
- The second asked what other tools could produce the same result. Status *I accept this as a
  limitation*, answer: `My plan watches rundll32 only. regsvr32 and a renamed copy of rundll32 can load
  the same DLL, so those are not covered by this rule. I accept that for now and will add a
  process-access rule on lsass.exe so the target, not the tool, is what I match.`
- The other eight were marked *I do not know yet*. They still count as answered. Not knowing is not a
  blind spot, so they are kept in the session record but are not listed in the Workbench Blind Spots.

When the counter reads "0 of 10 points still open", select **Next**.

## Step 6: Response (stage 5)

| Field | What was entered |
|---|---|
| What should an analyst check first? | `Check the parent process and the user who started rundll32, then whether a dump file was written to disk.` |
| What should the response be? | `Isolate the host, collect the dump file and reset credentials of accounts that were logged on.` |
| Alert trigger | `Any single match` |
| Severity | `HIGH` (LOW, MEDIUM, HIGH, CRITICAL) |
| How would you test that it fires? | `On a lab host run rundll32.exe comsvcs.dll, MiniDump against the lsass.exe process id. Expect one alert and a dump file in the temp folder.` |

Select **Next**.

## Step 7: Review and create (stage 6)

1. **Output formats:** KQL is always produced. Tick SPL, EQL, Wazuh or AQL (a QRadar query, not a rule)
   if you need them. The test used KQL only.
2. Check **What you captured**. The test session showed: Stage 1 minimum complete, 1 telemetry source
   with 3 fields, 2 match elements and 1 exclusion, 10 of 10 evasion questions answered (2 accepted as
   limitations, 8 unknown), test scenario written. It is a record of how much of your own thinking was
   captured, not a quality score.
3. If it says something is missing, go back to that stage; the create buttons stay disabled until the
   stage 1 minimum (title, technique or "none", goal) is complete.
4. Choose how to finish:
   - **Create Workbench and generate rule:** creates the Workbench and queues rule generation.
   - **Create Workbench without a rule:** creates the Workbench only.
   - **Save and close:** keeps the session open for later.
5. Confirm the question "Create the Workbench and generate the rule? This locks the session."

## Step 8: What you get

1. You land on the new Workbench (here `DE000010`). A banner reads "Generating from your Maieutic
   design: KQL. Finished rules appear here by themselves." Leave the page open or come back; in the test
   it cleared after about 70 seconds.
2. Part 3 of the Workbench shows the generated KQL. In the test the rule:
   - read Sysmon Event ID 10, the source that was chosen;
   - matched `lsass.exe` as the target and `rundll32.exe` as the source;
   - turned the planned exclusion into an `ApprovedBackupAgentPaths` placeholder with a note to fill in
     a verified path;
   - did not add `regsvr32.exe`, because that was an accepted limitation.
3. **Blind Spots & Coverage Gaps** lists each accepted limitation and each point left to another
   detection, with the question and your own words. Points you marked "I do not know yet" are not listed.
4. "View Maieutic Conversation History" holds the questions and answers of the session.
5. Back in Workbench Hub > Maieutics the session shows **Finished, locked**. It stays as a read-only
   record of how the design was made. Edit the Workbench, not the session.

## Step 9: Review the rule before you rely on it

The generated rule goes through the normal checks, but treat it as a draft. In the test the backup-agent
path placeholder had to be filled in by a person. Run the test scenario from step 6, tune the rule, then
move the Workbench through the normal review workflow.

## Sharing a finished session (optional)

A finished session can be shared with trusted peers through Instance Sharing. In the Maieutics tab
switch on sharing for that session (it is off by default). Peers need a key with the `MAIEUTIC` scope.
See [instance-sharing-tlp.md](instance-sharing-tlp.md).

## Troubleshooting

| What you see | What to do |
|---|---|
| "To create a Workbench you still need a title (stage 1)" | Fill in the stage 1 "Working title". Sessions started with a name already have it |
| "Your answer was stored as written. It was not checked." | The AI check could not run. Your answer is saved. Check that your profile has a provider, or that "use organization AI" is on and the organization has one |
| Create buttons are disabled | The stage 1 minimum is incomplete: title, technique (or "none"), goal |
| No Data Catalog or Log Source results | Search by a shorter term, for example `sysmon` or `4688`. Ask an administrator whether the catalogs are populated |
| The banner never clears | Rule generation runs in a background worker. Ask an administrator to check that it is running |
