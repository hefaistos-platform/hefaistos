from django.contrib.auth import get_user_model
from django.test import TestCase

from organizations.models import Organization
from platform_data.models import MitreAttackTechnique
from playbooks.models import PlaybookGraph, CapabilityAbstraction

from .models import OrgAISettings, UserAISettings
from .schema import (
    OrgAISettingsType,
    Query,
    _normalize_preferred_model_choice,
    _build_playbook_generation_context,
    _compose_translated_response_playbook,
    _coerce_markdown_text,
    _extract_threat_report_parts,
    _map_layer_name,
    _parse_capability_entries,
    _split_translated_response_playbook,
)


class PlaybookGenerationContextTests(TestCase):
    def test_build_generation_context_includes_selected_capability_abstractions(self):
        org = Organization.objects.create(name="AI Org")
        User = get_user_model()
        user = User.objects.create_user(username="aiuser", password="password", organization=org)
        technique = MitreAttackTechnique.objects.create(
            technique_id="T1218.005",
            stix_id="attack-pattern--ai-test",
            name="Mshta",
            description="Signed binary proxy execution via Mshta",
            url="https://example.com/t1218.005",
        )
        graph = PlaybookGraph.objects.create(
            title="AI Workbench",
            organization=org,
            author=user,
            mitre_technique=technique,
            goal="Detect malicious mshta execution",
            detection_focus_layer="PROCESS_BEHAVIOR",
        )
        capability = CapabilityAbstraction.objects.create(
            technique=technique,
            organization=org,
            created_by=user,
            updated_by=user,
            abstraction_layer=CapabilityAbstraction.AbstractionLayer.PROCESS_BEHAVIOR,
            component_artifact="mshta child process chain",
            detection_value="Better behavior anchor",
            source_kind=CapabilityAbstraction.SourceKind.CUSTOM,
        )
        graph.selected_capability_abstractions.add(capability)

        context = _build_playbook_generation_context(graph)

        self.assertEqual(context["detection_focus_layer"], "PROCESS_BEHAVIOR")
        self.assertEqual(len(context["capability_abstractions"]), 1)
        self.assertEqual(
            context["capability_abstractions"][0]["component_artifact"],
            "mshta child process chain",
        )
        # Detection-generation context intentionally excludes response_playbook,
        # so translated response text never affects AI rule generation prompts.
        self.assertNotIn("response_playbook", context)


class ThreatReportMappingHelperTests(TestCase):
    def test_extract_threat_report_parts_accepts_heading_style_keys(self):
        payload = {
            "PART 1: DETECTION STRATEGY": {"a": 1},
            "Part 2 - Deep Dive": {"b": 2},
            "Part 4 / SOAR Configuration": {"c": 3},
            "Part 5 Testing & Validation": {"d": 4},
        }

        part1, part2, part4, part5 = _extract_threat_report_parts(payload)

        self.assertEqual(part1, {"a": 1})
        self.assertEqual(part2, {"b": 2})
        self.assertEqual(part4, {"c": 3})
        self.assertEqual(part5, {"d": 4})

    def test_parse_capability_entries_maps_abstraction_layer_names(self):
        part1 = {
            "Capability Abstraction Library": [
                {
                    "ATT&CK Technique Code": "T1059.001",
                    "Abstraction Layer": "Tool/Binary",
                    "Component / Artifact": "powershell.exe",
                    "Adversary Purpose": "Execute encoded command payload",
                },
                {
                    "ATT&CK Technique Code": "T1053.005",
                    "Abstraction Layer": "Process behavior",
                    "Component / Artifact": "schtasks.exe parent-child chain",
                },
            ]
        }

        parsed = _parse_capability_entries(part1, fallback_technique_codes=[])

        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["abstraction_layer"], CapabilityAbstraction.AbstractionLayer.TOOL)
        self.assertEqual(parsed[1]["abstraction_layer"], CapabilityAbstraction.AbstractionLayer.PROCESS_BEHAVIOR)
        self.assertEqual(_map_layer_name("Network behavior"), CapabilityAbstraction.AbstractionLayer.NETWORK_BEHAVIOR)

    def test_parse_capability_entries_normalizes_bracketed_technique_code(self):
        part1 = {
            "Capability Abstraction Library": [
                {
                    "ATT&CK Technique Code": "[T1055.002]",
                    "Abstraction Layer": "API/EXPORT",
                    "Component / Artifact": "NtWriteVirtualMemory",
                }
            ]
        }

        parsed = _parse_capability_entries(part1, fallback_technique_codes=[])

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["technique_code"], "T1055.002")

    def test_coerce_markdown_text_formats_structured_technical_context(self):
        structured = {
            "tools_and_malware": [
                {
                    "name": "RUSTCLOAK",
                    "role": "Rust-based loader delivered as malicious UnityPlayer.dll",
                    "mapped_techniques": [
                        "MITRE ATT&CK [T1574.002]",
                        "MITRE ATT&CK [T1497.001]",
                    ],
                }
            ],
            "environment_preconditions": [
                "Windows endpoint where a user can execute a lure via MITRE ATT&CK [T1204.002].",
            ],
        }

        rendered = _coerce_markdown_text(structured)

        self.assertIn("- **Tools And Malware:**", rendered)
        self.assertIn("- **RUSTCLOAK:** Rust-based loader delivered as malicious UnityPlayer.dll", rendered)
        self.assertIn("- **Mapped Techniques:**", rendered)
        self.assertIn("- MITRE ATT&CK [T1574.002]", rendered)
        self.assertIn("- **Environment Preconditions:**", rendered)


class ResponsePlaybookTranslationTests(TestCase):
    def test_split_translated_response_playbook_extracts_original_and_translation(self):
        source = (
            "[Translation: DE]\n"
            "1. Host isolieren.\n\n"
            "---\n\n"
            "[Original]\n"
            "1. Isolate host."
        )

        parsed = _split_translated_response_playbook(source)

        self.assertEqual(parsed["language"], "DE")
        self.assertEqual(parsed["translated"], "1. Host isolieren.")
        self.assertEqual(parsed["original"], "1. Isolate host.")

    def test_compose_translated_response_playbook_formats_expected_layout(self):
        rendered = _compose_translated_response_playbook(
            original="1. Isolate host.",
            translated="1. Aislar host.",
            language_code="SP",
        )

        self.assertIn("[Translation: SP]", rendered)
        self.assertIn("[Original]", rendered)
        self.assertIn("1. Aislar host.", rendered)
        self.assertTrue(rendered.rstrip().endswith("1. Isolate host."))


class OrgAISettingsTypeResolverTests(TestCase):
    def test_resolve_has_any_provider_works_with_graphene_root_model_instance(self):
        org = Organization.objects.create(name="Resolver Org")
        settings = OrgAISettings.objects.create(
            organization=org,
            openai_api_key="sk-test",
            openai_enabled=True,
        )

        # Graphene resolves fields with the model instance as root.
        has_any_provider = OrgAISettingsType.resolve_has_any_provider(settings, info=None)

        self.assertTrue(has_any_provider)


class PreferredModelNormalizationTests(TestCase):
    def test_normalize_preferred_model_choice_maps_lowercase_openai_model(self):
        self.assertEqual(_normalize_preferred_model_choice('gpt-5.4'), 'GPT-5.4')

    def test_resolve_my_ai_settings_repairs_legacy_lowercase_preferred_model(self):
        org = Organization.objects.create(name="Legacy Model Org")
        User = get_user_model()
        user = User.objects.create_user(username="legacy-model-user", password="password", organization=org)
        UserAISettings.objects.create(
            user=user,
            preferred_model='gpt-5.4',
            use_org_ai=True,
        )

        info = type("Info", (), {"context": type("Context", (), {"user": user})()})()
        resolved = Query().resolve_my_ai_settings(info)

        self.assertEqual(resolved.preferred_model, 'GPT-5.4')
