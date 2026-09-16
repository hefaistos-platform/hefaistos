"""
Debug script for why derive_telemetry_requirements returned 0 entries in the
smoke test, despite ai_settings resolving as "configured".

Run via:
  docker compose exec -T backend python manage.py shell < scripts/debug_telemetry_ai_call.py
"""

from organizations.models import Organization
from identity.models import CustomUser
from ai_assistant.models import UserAISettings
from ai_assistant.schema import _get_effective_ai_settings
from ai_assistant.engine import build_available, _resolve_provider
from ai_assistant.opentide_enrichment import call_ai_provider

org = Organization.objects.first()
user = CustomUser.objects.filter(organization=org).first()
print(f"User: {user.username} (org: {org.name})")

user_ai_settings, _ = UserAISettings.objects.get_or_create(user=user)
print(f"\nUserAISettings row: id={user_ai_settings.id}")
print(f"  enable_auto_enrichment = {getattr(user_ai_settings, 'enable_auto_enrichment', 'N/A')}")

ai_settings = _get_effective_ai_settings(user_ai_settings)
print(f"\nEffective AI settings object: {ai_settings!r}")

available = build_available(ai_settings)
print(f"\nbuild_available(ai_settings) = {available!r}")

if available:
    provider = _resolve_provider(ai_settings, available)
    print(f"_resolve_provider(...) = {provider!r}")

    # Check which key getters actually return non-empty values (without
    # printing the key values themselves).
    for getter_name in [
        "get_openai_key", "get_gemini_key", "get_claude_key",
        "get_ollama_url", "get_ollama_model",
    ]:
        getter = getattr(ai_settings, getter_name, None)
        if getter:
            try:
                val = getter()
                print(f"  {getter_name}() -> {'SET (non-empty)' if val else 'EMPTY/None'}")
            except Exception as exc:
                print(f"  {getter_name}() -> raised {exc!r}")
else:
    print("\nNo provider available at all — build_available() returned falsy.")
    print("This means UserAISettings/OrgAISettings has no usable provider configured for this user,")
    print("which fully explains the 0-entries result: call_ai_provider() returns '' immediately.")

print("\n--- Attempting a minimal direct call_ai_provider() test ---")
raw = call_ai_provider(
    "",
    ai_settings,
    response_format="json",
    system_prompt="You are a test assistant. Return only strict JSON.",
    user_prompt='Return exactly this JSON: {"ping": "pong"}',
)
print(f"call_ai_provider raw response: {raw!r}")
if not raw:
    print(
        "\nEMPTY RESPONSE: either no provider available, or the provider call raised "
        "an exception that was caught and logged as a warning inside call_ai_provider(). "
        "Check backend container logs for a line like:\n"
        "  'AI provider call failed (<PROVIDER>): <error>'"
    )
else:
    print("PASS: AI provider call returned a real response — the provider itself works.")
    print("If the earlier smoke test still returned 0 entries, the issue is in JSON parsing")
    print("or in the derive_telemetry_requirements prompt/response shape, not provider connectivity.")
