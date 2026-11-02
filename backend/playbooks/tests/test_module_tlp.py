"""Persistence, access control, and conversion coverage for module TLP fields."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase

from ach.models import ACHAnalysis, Hypothesis
from ach.schema import ApplyACHTemplate, CloneACHAnalysis, CreatePlaybookGraphFromHypothesis, SaveACHAsTemplate
from advops.models import ADVOPSReport
from advops.misp_integration import MISPClient
from core.schema import schema
from organizations.models import HefaistosRemotePeer, Organization
from organizations.sharing import _ach_payload_for_org, _advops_payload_for_org, _import_ach, _import_advops
from playbooks.models import MveDraft, MveNode, PlaybookGraph
from playbooks.schema import CreateWorkbenchFromMve, ExportMveOpenTideYaml
from playbooks.utils.mve_opentide_compiler import compile_velocity_detection
from playbooks.utils.tlp import TLP_VALUES


class ModuleTlpTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='TLP source')
        self.other_org = Organization.objects.create(name='TLP destination')
        self.user = get_user_model().objects.create_user(username='tlp_owner', organization=self.org, role='ADMIN')
        self.other = get_user_model().objects.create_user(username='tlp_other', organization=self.other_org, role='ADMIN')
        self.info = SimpleNamespace(context=SimpleNamespace(user=self.user))
        self.portal_patch = patch('playbooks.l1_portal.upsert_l1_portal_snapshot')
        self.portal_patch.start()
        self.addCleanup(self.portal_patch.stop)

    def execute(self, query, variables=None, user=None):
        result = schema.execute(query, variable_values=variables, context_value=SimpleNamespace(user=user or self.user))
        self.assertIsNone(result.errors, result.errors)
        return result.data

    def test_all_six_levels_persist_through_each_creation_api(self):
        queries = [
            ('createAchAnalysis', 'mutation($tlp:String){createAchAnalysis(title:"Analysis",tlpClassification:$tlp){analysis{id tlpClassification}}}', 'analysis', ACHAnalysis),
            ('createAdvopsReport', 'mutation($tlp:String){createAdvopsReport(input:{hypothesis:"Hunt",tlpClassification:$tlp}){report{id tlpClassification}}}', 'report', ADVOPSReport),
            ('createMveDraft', 'mutation($tlp:String){createMveDraft(name:"Chain",tlpClassification:$tlp){mveDraft{id tlpClassification}}}', 'mveDraft', MveDraft),
        ]
        for value in TLP_VALUES:
            for operation, query, field, model in queries:
                with self.subTest(value=value, operation=operation):
                    row = self.execute(query, {'tlp': f'TLP:{value.lower()}'})[operation][field]
                    self.assertEqual(row['tlpClassification'], value)
                    self.assertEqual(model.objects.get(pk=row['id']).tlp_classification, value)

    def test_missing_classifications_default_to_unclear(self):
        self.assertEqual(ACHAnalysis.objects.create(title='Unknown', owner=self.user).tlp_classification, 'UNCLEAR')
        self.assertEqual(ADVOPSReport.objects.create(hunt_id='Unknown', organization=self.org).tlp_classification, 'UNCLEAR')
        self.assertEqual(MveDraft.objects.create(name='Unknown', organization=self.org).tlp_classification, 'UNCLEAR')

    def test_ach_edit_is_owner_only_and_updates_persisted_value(self):
        analysis = ACHAnalysis.objects.create(title='Owned', owner=self.user, tlp_classification='RED')
        query = 'mutation($id:UUID!){updateAchTlpClassification(analysisId:$id,tlpClassification:"UNCLEAR"){analysis{id tlpClassification}}}'
        for user in (self.other, AnonymousUser()):
            result = schema.execute(query, variable_values={'id': str(analysis.id)}, context_value=SimpleNamespace(user=user))
            self.assertTrue(result.errors)
            analysis.refresh_from_db()
            self.assertEqual(analysis.tlp_classification, 'RED')
        self.execute(query, {'id': str(analysis.id)})
        analysis.refresh_from_db()
        self.assertEqual(analysis.tlp_classification, 'UNCLEAR')

    def test_ach_templates_clones_and_workbenches_copy_classification(self):
        source = ACHAnalysis.objects.create(title='Source', owner=self.user, tlp_classification='AMBER+STRICT')
        hypothesis = Hypothesis.objects.create(analysis=source, content='Investigate behavior')
        template = SaveACHAsTemplate().mutate(self.info, analysis_id=source.id, title='Snapshot').template
        self.assertEqual(template.tlp_classification, 'AMBER+STRICT')
        target = ACHAnalysis.objects.create(title='Target', owner=self.user)
        ApplyACHTemplate().mutate(self.info, analysis_id=target.id, template_id=template.id)
        target.refresh_from_db()
        self.assertEqual(target.tlp_classification, 'AMBER+STRICT')
        clone = CloneACHAnalysis().mutate(self.info, analysis_id=source.id).analysis
        self.assertEqual(clone.tlp_classification, 'AMBER+STRICT')
        graph = CreatePlaybookGraphFromHypothesis().mutate(self.info, hypothesis_id=hypothesis.id).playbook_graph
        self.assertEqual(graph.tlp_classification, 'AMBER+STRICT')

    def test_advops_partial_updates_preserve_tlp_and_reject_other_org(self):
        report = ADVOPSReport.objects.create(hunt_id='Partial', organization=self.org, author=self.user, tlp_classification='RED')
        query = 'mutation($id:UUID!,$input:ADVOPSReportInput!){updateAdvopsReport(id:$id,input:$input){report{id tlpClassification}}}'
        self.execute(query, {'id': str(report.id), 'input': {'status': 'RESEARCH'}})
        report.refresh_from_db()
        self.assertEqual(report.tlp_classification, 'RED')
        result = schema.execute(query, variable_values={'id': str(report.id), 'input': {'tlpClassification': 'CLEAR'}}, context_value=SimpleNamespace(user=self.other))
        self.assertTrue(result.errors)
        self.execute(query, {'id': str(report.id), 'input': {'tlpClassification': 'UNCLEAR'}})
        report.refresh_from_db()
        self.assertEqual(report.tlp_classification, 'UNCLEAR')

    def test_mve_tlp_edits_respect_org_scope_and_exported_lock(self):
        draft = MveDraft.objects.create(name='Chain', organization=self.org, author=self.user, tlp_classification='RED')
        query = 'mutation($id:UUID!,$tlp:String){updateMveDraft(draftId:$id,tlpClassification:$tlp){mveDraft{id tlpClassification}}}'
        variables = {'id': str(draft.id), 'tlp': 'UNCLEAR'}
        result = schema.execute(query, variable_values=variables, context_value=SimpleNamespace(user=self.other))
        self.assertTrue(result.errors)
        self.execute(query, variables)
        draft.refresh_from_db()
        self.assertEqual(draft.tlp_classification, 'UNCLEAR')
        draft.status = MveDraft.DraftStatus.EXPORTED
        draft.save()
        result = schema.execute(query, variable_values={'id': str(draft.id), 'tlp': 'CLEAR'}, context_value=self.info.context)
        self.assertTrue(result.errors)
        draft.refresh_from_db()
        self.assertEqual(draft.tlp_classification, 'UNCLEAR')

    def test_mve_compiler_preserves_all_six_levels(self):
        draft = MveDraft.objects.create(name='Chain', organization=self.org, author=self.user)
        MveNode.objects.create(draft=draft, step_order=1, node_type='EVENT', label='Signal')
        for value in TLP_VALUES:
            draft.tlp_classification = value
            self.assertEqual(compile_velocity_detection(draft)['metadata']['tlp'], value.lower())

    @patch('playbooks.schema._validate_mve_draft_instance', return_value=[])
    def test_mve_workbench_conversion_preserves_unclear(self, _validation):
        draft = MveDraft.objects.create(name='Chain', organization=self.org, author=self.user, tlp_classification='UNCLEAR')
        result = CreateWorkbenchFromMve.mutate(None, self.info, draft_id=draft.id, enrich_with_ai=False)
        self.assertTrue(result.success)
        self.assertEqual(result.playbook_graph.tlp_classification, 'UNCLEAR')

    @patch('playbooks.schema._validate_mve_draft_instance', return_value=[])
    def test_mve_append_rejects_mismatch_and_preserves_matching_chain(self, _validation):
        draft = MveDraft.objects.create(name='Chain', organization=self.org, author=self.user, tlp_classification='UNCLEAR')
        MveNode.objects.create(draft=draft, step_order=1, node_type='EVENT', label='Signal')
        graph = PlaybookGraph.objects.create(title='Destination', organization=self.org, author=self.user, status='DEPLOYED', tlp_classification='CLEAR')
        with self.assertRaisesRegex(Exception, 'TLP mismatch'):
            ExportMveOpenTideYaml.mutate(None, self.info, draft_id=draft.id, mode='APPEND_WORKBENCH', target_graph_id=graph.id)
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'DRAFT')
        graph.tlp_classification = 'UNCLEAR'
        graph.save()
        result = ExportMveOpenTideYaml.mutate(None, self.info, draft_id=draft.id, mode='APPEND_WORKBENCH', target_graph_id=graph.id)
        self.assertTrue(result.success)
        graph.refresh_from_db()
        self.assertEqual(graph.tlp_classification, 'UNCLEAR')
        self.assertEqual(graph.opentide_yaml['mve_velocity_detections'][0]['metadata']['tlp'], 'unclear')
        graph.save()
        graph.refresh_from_db()
        self.assertEqual(graph.opentide_yaml['mve_velocity_detections'][0]['metadata']['tlp'], 'unclear')

    def test_peer_exports_imports_and_older_updates_preserve_tlp(self):
        ACHAnalysis.objects.create(title='Share analysis', owner=self.user, status='FINISHED', allow_remote_pull=True, tlp_classification='UNCLEAR')
        ADVOPSReport.objects.create(hunt_id='Share hunt', organization=self.org, author=self.user, status='DEPLOYED', allow_remote_pull=True, tlp_classification='RED')
        ach_payload = _ach_payload_for_org(self.org)
        advops_payload = _advops_payload_for_org(self.org)
        self.assertEqual(ach_payload[0]['tlp_classification'], 'UNCLEAR')
        self.assertEqual(advops_payload[0]['tlp_classification'], 'RED')
        peer = HefaistosRemotePeer.objects.create(organization=self.other_org, name='Peer', remote_url='https://example.com', remote_instance_id=uuid.uuid4())
        summary = {key: {'created': 0, 'updated': 0, 'failed': 0} for key in ('ach', 'advops')}
        errors = []
        _import_ach(ach_payload, self.other, self.other_org, peer, summary, errors)
        _import_advops(advops_payload, self.other_org, self.other, peer, summary, errors)
        self.assertEqual(errors, [])
        imported = ADVOPSReport.objects.get(organization=self.other_org)
        self.assertEqual(imported.tlp_classification, 'RED')
        self.assertEqual(ACHAnalysis.objects.get(owner=self.other).tlp_classification, 'UNCLEAR')
        del advops_payload[0]['tlp_classification']
        _import_advops(advops_payload, self.other_org, self.other, peer, summary, errors)
        imported.refresh_from_db()
        self.assertEqual(imported.tlp_classification, 'RED')
        self.assertEqual(errors, [])

    def test_misp_serialized_events_preserve_tlp_and_restrict_unclear(self):
        client = MISPClient.__new__(MISPClient)
        client.misp = MagicMock()
        client.misp.add_event.return_value = {'Event': {'id': '1'}}
        for value in TLP_VALUES:
            client.create_event('TLP test', tlp_classification=value)
            event = client.misp.add_event.call_args.args[0]['Event']
            self.assertIn(f'tlp:{value.lower()}', [tag['name'] for tag in event['Tag']])
            if value in {'UNCLEAR', 'RED', 'AMBER', 'AMBER+STRICT'}:
                self.assertEqual(event['distribution'], 0)
            self.assertFalse(event['published'])
