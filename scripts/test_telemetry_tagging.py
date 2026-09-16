"""
Smoke test for Telemetry Tagging (Milestone 1) — run via:
  docker compose exec -T backend python manage.py shell < test_telemetry_tagging.py

Exercises:
  1. Gate blocks derivation on an incomplete Workbench (no AI call made).
  2. Gate passes and derivation runs on a fully-populated Workbench.
  3. Cleans up the test object afterwards (does not leave test data behind).

Does NOT touch any real Workbench data — creates and deletes its own throwaway
PlaybookGraph scoped to the first available Organization.
"""

from organizations.models import Organization
from identity.models import CustomUser
from platform_data.models import MitreAttackTechnique
from playbooks.models import PlaybookGraph
from ai_assistant.models import UserAISettings
from ai_assistant.schema import _get_effective_ai_settings
from ai_assistant.telemetry_derivation import derive_telemetry_requirements, TelemetryGateError

print("=" * 70)
print("TELEMETRY TAGGING SMOKE TEST")
print("=" * 70)

org = Organization.objects.first()
if not org:
    print("FAIL: no Organization found in DB, cannot run test.")
else:
    print(f"Using organization: {org.name} ({org.id})")

    technique = MitreAttackTechnique.objects.filter(technique_id="T1059").first() \
        or MitreAttackTechnique.objects.first()
    print(f"Using technique: {technique}")

    # --- Create a throwaway, fully-empty test Workbench ---
    test_graph = PlaybookGraph.objects.create(
        title="[SMOKETEST] Telemetry Tagging Gate Test",
        organization=org,
    )
    print(f"\nCreated test Workbench: {test_graph.id}")

    # ------------------------------------------------------------------
    # TEST 1: Gate should BLOCK (all 5 required fields still empty)
    # ------------------------------------------------------------------
    print("\n--- TEST 1: gate should block (empty Workbench) ---")
    missing = test_graph.telemetry_tagging_missing_fields()
    print(f"Missing fields reported: {missing}")
    assert len(missing) == 5, f"Expected all 5 fields missing, got {len(missing)}: {missing}"
    assert test_graph.telemetry_tagging_gate_passed() is False
    print("PASS: gate correctly reports all 5 fields missing and gate_passed() == False")

    try:
        derive_telemetry_requirements(test_graph, user_settings=None)
        print("FAIL: derive_telemetry_requirements did NOT raise TelemetryGateError")
    except TelemetryGateError as exc:
        print(f"PASS: TelemetryGateError raised as expected, missing_fields={exc.missing_fields}")

    # ------------------------------------------------------------------
    # TEST 2: Gate should PASS after populating all 5 required fields
    # ------------------------------------------------------------------
    print("\n--- TEST 2: gate should pass (fully populated Workbench) ---")
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
    print(f"Missing fields after populating: {missing}")
    assert missing == [], f"Expected no missing fields, got: {missing}"
    assert test_graph.telemetry_tagging_gate_passed() is True
    print("PASS: gate correctly reports no missing fields and gate_passed() == True")

    # Try to resolve a real AI settings object (org may or may not have a key
    # configured — either outcome is informative here).
    user = CustomUser.objects.filter(organization=org).first()
    ai_settings = None
    if user:
        user_ai_settings, _ = UserAISettings.objects.get_or_create(user=user)
        ai_settings = _get_effective_ai_settings(user_ai_settings)
        print(f"Resolved AI settings for user {user.username}: provider configured = {bool(ai_settings)}")
    else:
        print("No CustomUser found for this organization; ai_settings will be None.")

    try:
        result = derive_telemetry_requirements(test_graph, user_settings=ai_settings)
        print(f"\nderive_telemetry_requirements() returned {len(result)} entries:")
        for entry in result:
            print(f"  - {entry}")
        if not result:
            print(
                "\nNOTE: empty result is EXPECTED if no AI provider key is configured "
                "for this user/org (call_ai_provider degrades gracefully to ''). "
                "This still proves the gate + reference-data collection path executed "
                "without raising, which is the code-path we needed to verify."
            )
        else:
            for entry in result:
                assert entry["status"] == "unverified", f"Expected status=unverified, got {entry}"
                assert entry["origin"] == "ai_derived", f"Expected origin=ai_derived, got {entry}"
            print("PASS: all derived entries correctly tagged status='unverified', origin='ai_derived'")
    except TelemetryGateError as exc:
        print(f"FAIL: gate unexpectedly blocked a fully-populated Workbench: {exc.missing_fields}")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    test_graph.delete()
    print(f"\nCleaned up test Workbench {test_graph.id}")

print("\n" + "=" * 70)
print("SMOKE TEST COMPLETE")
print("=" * 70)
