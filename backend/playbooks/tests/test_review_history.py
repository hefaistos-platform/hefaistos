from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from graphene.test import Client

from core.schema import schema
from identity.models import CustomUser
from organizations.models import Organization
from playbooks.models import PlaybookGraph


class ReviewHistoryTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name='Review history org')
        self.author = CustomUser.objects.create_user(
            username='history-author', organization=self.org, role='ANALYST',
        )
        self.reviewer = CustomUser.objects.create_user(
            username='history-reviewer', organization=self.org, role='REVIEWER',
        )
        self.graph = PlaybookGraph.objects.create(
            title='Review history', organization=self.org, author=self.author,
        )
        self.client = Client(schema)

    def execute(self, query, user, **variables):
        result = self.client.execute(
            query, variable_values=variables,
            context_value=SimpleNamespace(user=user),
        )
        self.assertNotIn('errors', result)
        return result['data']

    @patch('playbooks.schema.publish_event')
    def test_history_survives_rejection_resubmission_and_approval(self, _publish):
        submit = '''
            mutation Submit($id: UUID!, $note: String!) {
                submitForReview(graphId: $id, note: $note) {
                    success reviewRequest { id }
                }
            }
        '''
        finalize = '''
            mutation Finalize($id: UUID!, $decision: String!, $feedback: String!) {
                finalizeReview(requestId: $id, decision: $decision, feedback: $feedback) { success }
            }
        '''
        history = '''
            query History($id: UUID!) {
                playbookGraph(id: $id) {
                    activeReview { id }
                    reviewHistory {
                        id status comments { text user { username } }
                    }
                }
            }
        '''
        for note, decision, feedback in [
            ('Initial submission', 'REJECT', 'Change the threshold'),
            ('Threshold updated', 'APPROVE', 'Looks good'),
        ]:
            request = self.execute(submit, self.author, id=str(self.graph.id), note=note)
            request_id = request['submitForReview']['reviewRequest']['id']
            self.execute(finalize, self.reviewer, id=request_id, decision=decision, feedback=feedback)

        data = self.execute(history, self.author, id=str(self.graph.id))['playbookGraph']
        self.assertIsNone(data['activeReview'])
        self.assertEqual([r['status'] for r in data['reviewHistory']], ['CHANGES_REQUESTED', 'APPROVED'])
        self.assertEqual(
            [[(c['user']['username'], c['text']) for c in r['comments']] for r in data['reviewHistory']],
            [
                [('history-author', 'Initial submission'), ('history-reviewer', 'Change the threshold')],
                [('history-author', 'Threshold updated'), ('history-reviewer', 'Looks good')],
            ],
        )

        other_graph = PlaybookGraph.objects.create(
            title='Unrelated workbench', organization=self.org, author=self.author,
        )
        self.assertEqual(
            self.execute(history, self.author, id=str(other_graph.id))['playbookGraph']['reviewHistory'], [],
        )
