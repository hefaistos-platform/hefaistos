from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from identity.decorators import Roles
from organizations.models import Organization
from rules.models import RuleRepository, RuleRepositoryRAGFileStatus
from rules.schema import (
    Query,
    SyncRuleRepositoryRag,
    UpdateRuleRepositoryRagFileStatuses,
    UpdateRuleRepositoryRagSyncStatus,
)


class RuleRepositoryRAGSyncTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name='RAG Sync Org')
        self.admin = get_user_model().objects.create_user(
            username='rag_admin',
            password='pass1234',
            organization=self.organization,
            role=Roles.ADMIN,
        )
        self.repo = RuleRepository.objects.create(
            organization=self.organization,
            name='Repo One',
            git_url='https://github.com/example/repo.git',
            rag_sync_enabled=True,
            rag_sync_schedule=RuleRepository.RAGSyncSchedule.EVERY_24H,
            rag_dataset_path='rules/templates/**/*.jsonl',
            rag_branch='main',
            rag_next_scheduled_sync=timezone.now() - timedelta(minutes=5),
        )

    def _info(self, user):
        return SimpleNamespace(context=SimpleNamespace(user=user))

    @patch('rules.management.commands.run_scheduled_rag_syncs.get_publisher')
    def test_scheduler_command_queues_due_repo(self, get_publisher_mock):
        publisher = MagicMock()
        get_publisher_mock.return_value = publisher

        call_command('run_scheduled_rag_syncs')

        publisher.publish_message.assert_called_once()
        routing_key, body = publisher.publish_message.call_args[0]
        self.assertEqual(routing_key, 'rule.repo.rag.sync.requested')
        self.assertEqual(body['repository_id'], str(self.repo.id))

        self.repo.refresh_from_db()
        self.assertEqual(self.repo.rag_last_sync_status, RuleRepository.RAGSyncStatus.QUEUED)
        self.assertIsNotNone(self.repo.rag_last_sync_status_at)
        self.assertIsNotNone(self.repo.rag_last_sync_status_at)
        self.assertEqual(self.repo.rag_last_sync_error, '')
        self.assertIsNotNone(self.repo.rag_next_scheduled_sync)
        self.assertGreater(self.repo.rag_next_scheduled_sync, timezone.now() - timedelta(seconds=1))

    @patch('rules.management.commands.run_scheduled_rag_syncs.get_publisher')
    def test_scheduler_does_not_requeue_non_stale_running_repo(self, get_publisher_mock):
        publisher = MagicMock()
        get_publisher_mock.return_value = publisher

        self.repo.rag_last_sync_status = RuleRepository.RAGSyncStatus.RUNNING
        self.repo.rag_next_scheduled_sync = timezone.now() - timedelta(minutes=1)
        self.repo.save(update_fields=['rag_last_sync_status', 'rag_next_scheduled_sync'])

        call_command('run_scheduled_rag_syncs')

        publisher.publish_message.assert_not_called()
        self.repo.refresh_from_db()
        self.assertEqual(self.repo.rag_last_sync_status, RuleRepository.RAGSyncStatus.RUNNING)

    @patch('rules.management.commands.run_scheduled_rag_syncs.get_publisher')
    def test_scheduler_watchdog_marks_stale_running_and_requeues(self, get_publisher_mock):
        publisher = MagicMock()
        get_publisher_mock.return_value = publisher

        now = timezone.now()
        RuleRepository.objects.filter(pk=self.repo.pk).update(
            rag_last_sync_status=RuleRepository.RAGSyncStatus.RUNNING,
            rag_last_sync_error='',
            rag_next_scheduled_sync=now + timedelta(days=1),
            updated_at=now - timedelta(hours=3),
        )

        call_command('run_scheduled_rag_syncs')

        publisher.publish_message.assert_called_once()
        routing_key, body = publisher.publish_message.call_args[0]
        self.assertEqual(routing_key, 'rule.repo.rag.sync.requested')
        self.assertEqual(body['repository_id'], str(self.repo.id))

        self.repo.refresh_from_db()
        self.assertEqual(self.repo.rag_last_sync_status, RuleRepository.RAGSyncStatus.QUEUED)
        self.assertIsNotNone(self.repo.rag_last_sync_status_at)
        self.assertEqual(self.repo.rag_last_sync_error, '')
        self.assertIsNotNone(self.repo.rag_next_scheduled_sync)
        self.assertGreater(self.repo.rag_next_scheduled_sync, timezone.now() - timedelta(seconds=1))

    @patch('rules.management.commands.run_scheduled_rag_syncs.get_publisher')
    def test_scheduler_watchdog_can_disable_auto_requeue(self, get_publisher_mock):
        publisher = MagicMock()
        get_publisher_mock.return_value = publisher

        now = timezone.now()
        RuleRepository.objects.filter(pk=self.repo.pk).update(
            rag_last_sync_status=RuleRepository.RAGSyncStatus.RUNNING,
            rag_last_sync_error='',
            rag_next_scheduled_sync=now + timedelta(days=1),
            updated_at=now - timedelta(hours=3),
        )

        with patch.dict('os.environ', {'RAG_SYNC_WATCHDOG_REQUEUE_STALE': 'false'}):
            call_command('run_scheduled_rag_syncs')

        publisher.publish_message.assert_not_called()
        self.repo.refresh_from_db()
        self.assertEqual(self.repo.rag_last_sync_status, RuleRepository.RAGSyncStatus.FAILED)
        self.assertIsNotNone(self.repo.rag_last_sync_status_at)
        self.assertIn('Watchdog marked stale RUNNING sync as FAILED', self.repo.rag_last_sync_error)

    @patch('rules.schema.get_publisher')
    def test_sync_rule_repository_rag_mutation_queues_event(self, get_publisher_mock):
        publisher = MagicMock()
        get_publisher_mock.return_value = publisher

        result = SyncRuleRepositoryRag.mutate(None, self._info(self.admin), id=str(self.repo.id))

        self.assertTrue(result.ok)
        publisher.publish_message.assert_called_once()
        routing_key, body = publisher.publish_message.call_args[0]
        self.assertEqual(routing_key, 'rule.repo.rag.sync.requested')
        self.assertEqual(body['repository_id'], str(self.repo.id))

        self.repo.refresh_from_db()
        self.assertEqual(self.repo.rag_last_sync_status, RuleRepository.RAGSyncStatus.QUEUED)

    def test_update_rule_repository_rag_sync_status_mutation(self):
        result = UpdateRuleRepositoryRagSyncStatus.mutate(
            None,
            self._info(self.admin),
            id=str(self.repo.id),
            status='SUCCESS',
            error_message='',
            synced_templates=17,
        )

        self.assertIsNotNone(result.repository)

        self.repo.refresh_from_db()
        self.assertEqual(self.repo.rag_last_sync_status, RuleRepository.RAGSyncStatus.SUCCESS)
        self.assertIsNotNone(self.repo.rag_last_sync_status_at)
        self.assertEqual(self.repo.rag_last_sync_error, '')
        self.assertEqual(self.repo.rag_last_synced_templates, 17)
        self.assertIsNotNone(self.repo.rag_last_synced)

    def test_update_rule_repository_rag_sync_status_mutation_partial(self):
        result = UpdateRuleRepositoryRagSyncStatus.mutate(
            None,
            self._info(self.admin),
            id=str(self.repo.id),
            status='PARTIAL',
            error_message='1 file failed to ingest',
            synced_templates=9,
        )

        self.assertIsNotNone(result.repository)

        self.repo.refresh_from_db()
        self.assertEqual(self.repo.rag_last_sync_status, RuleRepository.RAGSyncStatus.PARTIAL)
        self.assertIsNotNone(self.repo.rag_last_sync_status_at)
        self.assertEqual(self.repo.rag_last_sync_error, '1 file failed to ingest')
        self.assertEqual(self.repo.rag_last_synced_templates, 9)
        self.assertIsNotNone(self.repo.rag_last_synced)

    def test_update_rule_repository_rag_file_statuses_mutation_replaces_stale_rows(self):
        RuleRepositoryRAGFileStatus.objects.create(
            repository=self.repo,
            source_path='rules/templates/stale.jsonl',
            source_branch='main',
            language='KQL',
            ingestion_status=RuleRepositoryRAGFileStatus.IngestionStatus.INGESTED,
            templates_count=1,
        )

        payload = [
            {
                'source_path': 'rules/templates/new.jsonl',
                'source_branch': 'main',
                'language': 'KQL',
                'ingestion_status': 'INGESTED',
                'templates_count': 6,
                'error_message': '',
            },
            {
                'source_path': 'rules/templates/invalid.jsonl',
                'source_branch': 'main',
                'language': 'KQL',
                'ingestion_status': 'FAILED',
                'templates_count': 0,
                'error_message': 'No valid templates found in JSONL file.',
            },
        ]

        result = UpdateRuleRepositoryRagFileStatuses.mutate(
            None,
            self._info(self.admin),
            id=str(self.repo.id),
            files=payload,
            replace_existing=True,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.count, 2)

        rows = list(
            RuleRepositoryRAGFileStatus.objects.filter(repository=self.repo).order_by('source_path')
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].source_path, 'rules/templates/invalid.jsonl')
        self.assertEqual(rows[0].ingestion_status, RuleRepositoryRAGFileStatus.IngestionStatus.FAILED)
        self.assertEqual(rows[1].source_path, 'rules/templates/new.jsonl')
        self.assertEqual(rows[1].templates_count, 6)

    def test_mark_reference_files_used_updates_usage_counters(self):
        from services.ai_generation_worker import _mark_reference_files_used

        file_status = RuleRepositoryRAGFileStatus.objects.create(
            repository=self.repo,
            source_path='rules/templates/new.jsonl',
            source_branch='main',
            language='KQL',
            ingestion_status=RuleRepositoryRAGFileStatus.IngestionStatus.INGESTED,
            templates_count=5,
            used_in_generation=False,
            usage_count=0,
        )

        _mark_reference_files_used([
            {
                'repository_id': str(self.repo.id),
                'source_path': 'rules/templates/new.jsonl',
                'source_branch': 'main',
                'language': 'KQL',
            }
        ])

        file_status.refresh_from_db()
        self.assertTrue(file_status.used_in_generation)
        self.assertEqual(file_status.usage_count, 1)
        self.assertIsNotNone(file_status.last_used_at)

    @patch('rules.schema._fetch_qdrant_repo_point_count')
    def test_rule_repository_rag_health_reports_qdrant_and_file_statuses(self, count_mock):
        count_mock.return_value = 11

        RuleRepositoryRAGFileStatus.objects.create(
            repository=self.repo,
            source_path='rules/templates/ok.jsonl',
            source_branch='main',
            language='KQL',
            ingestion_status=RuleRepositoryRAGFileStatus.IngestionStatus.INGESTED,
            templates_count=3,
        )
        RuleRepositoryRAGFileStatus.objects.create(
            repository=self.repo,
            source_path='rules/templates/bad.jsonl',
            source_branch='main',
            language='KQL',
            ingestion_status=RuleRepositoryRAGFileStatus.IngestionStatus.FAILED,
            templates_count=0,
        )

        disabled_repo = RuleRepository.objects.create(
            organization=self.organization,
            name='Repo Disabled',
            git_url='https://github.com/example/repo-disabled.git',
            rag_sync_enabled=False,
            rag_sync_schedule=RuleRepository.RAGSyncSchedule.DISABLED,
        )

        rows = Query().resolve_rule_repository_rag_health(self._info(self.admin))
        by_repo = {row.repository_name: row for row in rows}

        self.assertIn(self.repo.name, by_repo)
        self.assertIn(disabled_repo.name, by_repo)

        enabled = by_repo[self.repo.name]
        self.assertEqual(enabled.qdrant_status, 'OK')
        self.assertEqual(enabled.qdrant_point_count, 11)
        self.assertEqual(enabled.ingested_files, 1)
        self.assertEqual(enabled.failed_files, 1)

        disabled = by_repo[disabled_repo.name]
        self.assertEqual(disabled.qdrant_status, 'DISABLED')
        self.assertEqual(disabled.qdrant_point_count, 0)

        count_mock.assert_called_once_with(str(self.repo.id))
