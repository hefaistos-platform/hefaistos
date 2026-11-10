from datetime import date

from django.test import TestCase

from platform_data.models import (
    AtlasCaseStudy,
    AtlasMitigation,
    AtlasRelationship,
    AtlasTactic,
    AtlasTechnique,
    PlatformDataVersion,
)


class AtlasModelTests(TestCase):
    def test_can_create_atlas_core_objects(self):
        tactic = AtlasTactic.objects.create(
            atlas_id="AML.TA0001",
            name="AI Attack Adaptation",
            description="Adversary adapts capabilities for target conditions.",
            created_date=date(2021, 5, 13),
            modified_date=date(2026, 8, 31),
        )
        technique = AtlasTechnique.objects.create(
            atlas_id="AML.T0000",
            name="Search Open Technical Databases",
            description="Adversary gathers technical documentation.",
            maturity="Realized",
            platforms=["Enterprise"],
            created_date=date(2021, 5, 13),
            modified_date=date(2026, 9, 15),
        )
        mitigation = AtlasMitigation.objects.create(
            atlas_id="AML.M0004",
            name="Limit AI Service Query Volume and Rate",
            categories=["Technical - Cyber"],
            lifecycle_phases=["Deployment", "Monitoring and Maintenance"],
        )
        case_study = AtlasCaseStudy.objects.create(
            atlas_id="AML.CS0000",
            name="Evasion of Deep Learning Detector",
            case_study_type="Exercise",
            actor="Example Team",
            target="Example Target",
            start_date=date(2020, 1, 1),
            end_date=date(2020, 1, 1),
            start_date_granularity="Year",
            end_date_granularity="Year",
        )
        relationship = AtlasRelationship.objects.create(
            source_atlas_id=case_study.atlas_id,
            target_atlas_id=technique.atlas_id,
            relationship_type="employs",
            tactic_atlas_id=tactic.atlas_id,
            step_id="S01",
            leads_to=["S02"],
        )

        self.assertEqual(str(tactic), "AML.TA0001: AI Attack Adaptation")
        self.assertEqual(str(technique), "AML.T0000: Search Open Technical Databases")
        self.assertEqual(str(mitigation), "AML.M0004: Limit AI Service Query Volume and Rate")
        self.assertEqual(str(case_study), "AML.CS0000: Evasion of Deep Learning Detector")
        self.assertEqual(
            str(relationship),
            "AML.CS0000 employs AML.T0000",
        )

    def test_platform_data_version_accepts_atlas_framework(self):
        row = PlatformDataVersion.objects.create(framework='atlas', version='2026.10')
        self.assertEqual(row.framework, 'atlas')
        self.assertEqual(str(row), "MITRE ATLAS v2026.10")
