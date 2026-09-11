from datetime import timedelta
from types import SimpleNamespace

from django.test import SimpleTestCase
from django.utils import timezone

from organizations.ai_tasks import compute_next_run_at, get_ai_task_definitions
from organizations.models import OrganizationAITaskConfig


class TestAiTaskDefinitions(SimpleTestCase):
    def test_contains_expected_mvp_task_count(self):
        definitions = get_ai_task_definitions()
        self.assertGreaterEqual(len(definitions), 12)
        keys = {item.key for item in definitions}
        self.assertIn('push_rules_workbenches_to_git', keys)
        self.assertIn('sync_deployed_l1_portal', keys)
        self.assertIn('program_review_digest', keys)

        l1_sync = next(item for item in definitions if item.key == 'sync_deployed_l1_portal')
        self.assertTrue(l1_sync.default_enabled)


class TestComputeNextRunAt(SimpleTestCase):
    def test_daily_rolls_to_next_day_when_time_passed(self):
        reference = timezone.now().replace(hour=15, minute=30, second=0, microsecond=0)
        config = SimpleNamespace(
            schedule=OrganizationAITaskConfig.Schedule.DAILY,
            run_hour=8,
            run_minute=0,
            day_of_week=0,
            day_of_month=1,
        )

        next_run = compute_next_run_at(config, reference=reference)
        self.assertGreater(next_run, reference)
        self.assertEqual(next_run.hour, 8)
        self.assertEqual(next_run.minute, 0)

    def test_weekly_targets_requested_weekday(self):
        # Tuesday reference, ask for Friday.
        reference = timezone.now().replace(hour=10, minute=0, second=0, microsecond=0)
        while reference.weekday() != 1:  # Tuesday
            reference = reference + timedelta(days=1)

        config = SimpleNamespace(
            schedule=OrganizationAITaskConfig.Schedule.WEEKLY,
            day_of_week=4,  # Friday
            run_hour=9,
            run_minute=15,
            day_of_month=1,
        )

        next_run = compute_next_run_at(config, reference=reference)
        self.assertGreater(next_run, reference)
        self.assertEqual(next_run.weekday(), 4)
        self.assertEqual(next_run.hour, 9)
        self.assertEqual(next_run.minute, 15)

    def test_monthly_respects_day_of_month(self):
        reference = timezone.now().replace(day=20, hour=14, minute=0, second=0, microsecond=0)
        config = SimpleNamespace(
            schedule=OrganizationAITaskConfig.Schedule.MONTHLY,
            day_of_month=5,
            run_hour=7,
            run_minute=0,
            day_of_week=0,
        )

        next_run = compute_next_run_at(config, reference=reference)
        self.assertGreater(next_run, reference)
        self.assertEqual(next_run.day, 5)
        self.assertEqual(next_run.hour, 7)
        self.assertEqual(next_run.minute, 0)
