"""
Smoke test for Telemetry Tagging (Milestone 1) — full end-to-end run using a
user that has a real AI provider configured. Replace INSERT_USERNAME below
with a valid username that has a configured AI provider, or set it via the
TELEMETRY_TEST_USERNAME environment variable (takes precedence over the
constant below).

Run via:
  docker compose exec -T backend python manage.py shell < scripts/test_telemetry_tagging_with_ai.py

Or without editing the file:
  docker compose exec -T -e TELEMETRY_TEST_USERNAME=<username> backend \
    python manage.py shell < scripts/test_telemetry_tagging_with_ai.py
"""

import os

TEST_USERNAME = os.environ.get("TELEMETRY_TEST_USERNAME", "INSERT_USERNAME")

from organizations.models import Organization
from identity.models import CustomUser
from platform_data.models import MitreAttackTechnique
from playbooks.models import PlaybookGraph
from ai_assistant.models import UserAISettings
from ai_assistant.schema import _get_effective_ai_settings
from ai_assistant.telemetry_derivation import derive_telemetry_requirements, TelemetryGateError

print("=" * 70)
print(f"TELEMETRY TAGGING SMOKE TEST (with real AI provider, user={TEST_USERNAME})")
print("=" * 70)

user = CustomUser.objects.filter(username=TEST_USERNAME).first() if TEST_USERNAME and TEST_USERNAME != "INSERT_USERNAME" else None
if not user:
    print(
        f"FAIL: no valid username set (got '{TEST_USERNAME}'). "
        "Edit TEST_USERNAME in this script or set the TELEMETRY_TEST_USERNAME "
        "environment variable to a username that has a configured AI provider "
        "before running, e.g.:\n"
        "  docker compose exec -T -e TELEMETRY_TEST_USERNAME=<username> backend "
        "python manage.py shell < scripts/test_telemetry_tagging_with_ai.py"
    )
else:
    org = user.organization
    print(f"User: {user.username}, Organization: {org.name if org else None}")

    user_ai_settings, _ = UserAISettings.objects.get_or_create(user=user)
    ai_settings = _get_effective_ai_settings(user_ai_settings)
    print(f"Effective AI settings resolved: {ai_settings!r}")

    technique = MitreAttackTechnique.objects.filter(technique_id="T1059").first() \
        or MitreAttackTechnique.objects.first()
    print(f"Using technique: {technique}")

    test_graph = PlaybookGraph.objects.create(
        title="[SMOKETEST-AI] Telemetry Tagging Real AI Round-trip",
        organization=org,
    )
    test_graph_id = test_graph.id
    print(f"\nCreated test Workbench: {test_graph_id}")

    test_graph.mitre_technique = technique
    test_graph.goal = "Detect PowerShell-based execution used for initial access staging."
    test_graph.technical_context = (
        "Adversaries frequently invoke encoded PowerShell commands via powershell.exe "
        "or pwsh.exe spawned from Office applications to download and execute a "
        "second-stage payload. Focus on unusual parent-child process relationships "
        "and encoded command-line arguments."
    )
    test_graph.detection_rule = (
        "DeviceProcessEvents\n"
        "| where FileName in~ ('powershell.exe', 'pwsh.exe')\n"
        "| where ProcessCommandLine has '-enc' or ProcessCommandLine has '-EncodedCommand'\n"
        "| where InitiatingProcessFileName in~ ('winword.exe', 'excel.exe', 'outlook.exe')"
    )
    test_graph.threat_surface = ["OS::Windows"]
    test_graph.save()

    missing = test_graph.telemetry_tagging_missing_fields()
    print(f"Missing fields: {missing} (expect [])")
    assert missing == [], f"Gate unexpectedly blocked: {missing}"

    print("\nCalling derive_telemetry_requirements() with a REAL AI provider...")
    try:
        result = derive_telemetry_requirements(test_graph, user_settings=ai_settings)
        print(f"\nReturned {len(result)} entries:")
        for entry in result:
            print(f"  - source={entry.get('source')!r}")
            print(f"    component={entry.get('component')!r}")
            print(f"    fields={entry.get('fields')!r}")
            print(f"    rationale={entry.get('rationale')!r}")
            print(f"    origin={entry.get('origin')!r} status={entry.get('status')!r}")

        if not result:
            print("\nFAIL (or at least: unexpected) — provider is configured but 0 entries came back.")
            print("Check backend logs for 'AI provider call failed' around this timestamp.")
        else:
            all_ok = all(
                e.get("status") == "unverified" and e.get("origin") == "ai_derived"
                for e in result
            )
            print(f"\n{'PASS' if all_ok else 'FAIL'}: status/origin tagging correct on all entries: {all_ok}")
    except TelemetryGateError as exc:
        print(f"FAIL: gate unexpectedly blocked: {exc.missing_fields}")
    except Exception as exc:
        print(f"FAIL: unexpected exception during derivation: {exc!r}")

    PlaybookGraph.objects.filter(id=test_graph_id).delete()
    print(f"\nCleaned up test Workbench {test_graph_id}")

print("\n" + "=" * 70)
print("SMOKE TEST COMPLETE")
print("=" * 70)
