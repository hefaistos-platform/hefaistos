import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from ai_assistant import maieutic_lifecycle as lc
from ai_assistant import maieutic_workbench as mw
from ai_assistant.engine import _format_capability_abstractions_for_prompt
from ai_assistant.models import AIGenerationTask, UserAISettings
from ai_assistant.schema import _build_playbook_generation_context
from organizations.models import Organization
from platform_data.models import MitreAttackTechnique
from playbooks.models import CapabilityAbstraction

from .test_maieutic_workbench import SPEC


def with_design(**design):
    spec = {k: (dict(v) if isinstance(v, dict) else v) for k, v in SPEC.items()}
    spec['design'] = {**SPEC['design'], **design}
    return spec


class PureSelectionTests(SimpleTestCase):
    def test_focus_layer_is_kept_only_when_it_is_a_known_layer(self):
        self.assertEqual(mw.workbench_fields(with_design(focus_layer='API_EXPORT'))['detection_focus_layer'], 'API_EXPORT')
        self.assertEqual(mw.workbench_fields(with_design(focus_layer=' tool '))['detection_focus_layer'], 'TOOL')
        for bad in ('', 'NOPE', None, 5, ['TOOL'], {'a': 1}):
            self.assertNotIn('detection_focus_layer', mw.workbench_fields(with_design(focus_layer=bad)), bad)
        self.assertNotIn('detection_focus_layer', mw.workbench_fields(SPEC))

    def test_every_layer_the_model_offers_is_accepted(self):
        self.assertEqual(set(mw.FOCUS_LAYERS), {v for v, _ in CapabilityAbstraction.AbstractionLayer.choices})

    def test_ids_must_be_uuids_unique_and_limited(self):
        a, b = str(uuid.uuid4()), str(uuid.uuid4())
        got = mw.capability_ids_from_spec(with_design(capability_refs=[a, 'junk', None, 5, a.upper(), b, {'x': 1}, '']))
        self.assertEqual(got, [a, b])
        many = [str(uuid.uuid4()) for _ in range(mw.MAX_CAPABILITY_REFS + 5)]
        self.assertEqual(len(mw.capability_ids_from_spec(with_design(capability_refs=many))), mw.MAX_CAPABILITY_REFS)
        for bad in (None, 'abc', 7, {'a': 1}):
            self.assertEqual(mw.capability_ids_from_spec(with_design(capability_refs=bad)), [])
        self.assertEqual(mw.capability_ids_from_spec({}), [])


class AttachTests(TestCase):
    def setUp(self):
        U = get_user_model()
        self.org = Organization.objects.create(name='Org')
        self.other_org = Organization.objects.create(name='Other')
        self.author = U.objects.create_user(username='author', organization=self.org, role='ANALYST')
        self.t1 = MitreAttackTechnique.objects.create(technique_id='T1003.001', name='LSASS Memory')
        self.t2 = MitreAttackTechnique.objects.create(technique_id='T1059.001', name='PowerShell')

    def cap(self, technique=None, org='mine', layer='TOOL', name='comsvcs.dll'):
        organization = {'mine': self.org, 'other': self.other_org, 'baseline': None}[org]
        return CapabilityAbstraction.objects.create(
            technique=technique or self.t1, organization=organization, abstraction_layer=layer,
            component_artifact=name, adversary_purpose='dump memory', common_evasions='ordinal call')

    def spec(self, refs, focus='', technique=None):
        spec = with_design(capability_refs=[str(c.id) if hasattr(c, 'id') else c for c in refs], focus_layer=focus)
        if technique == 'NONE':
            spec['hypothesis'] = {**SPEC['hypothesis'], 'technique': {'state': 'NONE_CHOSEN'}}
        return spec

    def create(self, spec, mode=mw.EXIT_WITHOUT_RULE):
        d = lc.create_draft(self.author, name='s')
        d = lc.update_draft(d.id, self.author, spec_patch=spec)
        with patch('core.rabbitmq.publish_event', return_value=True):
            return mw.create_workbench_from_draft(d.id, self.author, exit_mode=mode)

    def attached(self, wb):
        return {c.component_artifact for c in wb.selected_capability_abstractions.all()}

    def test_picked_entries_and_focus_layer_land_on_the_workbench(self):
        mine, base = self.cap(name='mine'), self.cap(org='baseline', name='baseline', layer='API_EXPORT')
        wb, _ = self.create(self.spec([mine, base], focus='API_EXPORT'))
        self.assertEqual(self.attached(wb), {'mine', 'baseline'})
        wb.refresh_from_db()
        self.assertEqual(wb.detection_focus_layer, 'API_EXPORT')

    def test_nothing_is_filled_in_when_the_user_picked_nothing(self):
        self.cap()
        wb, _ = self.create(self.spec([]))
        self.assertEqual(self.attached(wb), set())
        self.assertEqual(wb.detection_focus_layer, '')

    def test_entries_of_another_organization_are_never_attached(self):
        secret = self.cap(org='other', name='theirs')
        wb, _ = self.create(self.spec([secret, self.cap(name='mine')]))
        self.assertEqual(self.attached(wb), {'mine'})

    def test_entries_for_a_different_technique_are_ignored(self):
        wb, _ = self.create(self.spec([self.cap(technique=self.t2, name='ps'), self.cap(name='lsass')]))
        self.assertEqual(self.attached(wb), {'lsass'})

    def test_no_technique_means_no_entries_but_the_focus_layer_is_kept(self):
        wb, _ = self.create(self.spec([self.cap()], focus='PROCESS_BEHAVIOR', technique='NONE'))
        self.assertEqual(self.attached(wb), set())
        self.assertEqual(wb.detection_focus_layer, 'PROCESS_BEHAVIOR')

    def test_deleted_and_invented_ids_do_not_break_creation(self):
        gone = self.cap(name='gone')
        gone_id = str(gone.id)
        gone.delete()
        wb, _ = self.create(self.spec([gone_id, str(uuid.uuid4()), 'junk', self.cap(name='kept')]))
        self.assertEqual(self.attached(wb), {'kept'})

    def test_duplicates_attach_once(self):
        c = self.cap()
        wb, _ = self.create(self.spec([c, c, str(c.id).upper()]))
        self.assertEqual(wb.selected_capability_abstractions.count(), 1)

    def test_selection_reaches_the_prompt_of_the_generation_task(self):
        UserAISettings.objects.create(user=self.author)
        c = self.cap(name='comsvcs.dll', layer='API_EXPORT')
        with self.captureOnCommitCallbacks(execute=True):
            wb, tasks = self.create(self.spec([c], focus='API_EXPORT'), mode=mw.EXIT_WITH_RULE)
        context = _build_playbook_generation_context(wb)
        self.assertEqual(context['detection_focus_layer'], 'API_EXPORT')
        text = _format_capability_abstractions_for_prompt(context)
        self.assertIn('DETECTION FOCUS LAYER: API_EXPORT', text)
        self.assertIn('COMPONENT / ARTIFACT: comsvcs.dll', text)
        self.assertIn('COMMON EVASIONS: ordinal call', text)
        self.assertEqual(AIGenerationTask.objects.filter(input_data__maieutic_workbench_id=str(wb.id)).count(), len(tasks))
        self.assertEqual(tasks[0].input_data['playbook_context']['detection_focus_layer'], 'API_EXPORT')
        self.assertEqual([x['component_artifact'] for x in tasks[0].input_data['playbook_context']['capability_abstractions']],
                         ['comsvcs.dll'])
