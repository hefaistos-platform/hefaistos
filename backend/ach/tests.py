from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from ach.schema import DeleteACHAnalysis, DeleteEvidence, DeleteHypothesis


class TestSuperuserDeletePermissions(SimpleTestCase):
    def _make_info(self, is_superuser=True):
        user = SimpleNamespace(
            is_anonymous=False,
            is_superuser=is_superuser,
            id="admin-1",
        )
        return SimpleNamespace(context=SimpleNamespace(user=user))

    @patch("ach.schema.Hypothesis.objects.get")
    def test_delete_hypothesis_allows_superuser_without_owner_filter(self, mock_get):
        hypothesis = MagicMock()
        mock_get.return_value = hypothesis

        result = DeleteHypothesis().mutate(self._make_info(), hypothesis_id="hyp-1")

        self.assertTrue(result.ok)
        mock_get.assert_called_once_with(id="hyp-1")
        hypothesis.delete.assert_called_once()

    @patch("ach.schema.Evidence.objects.get")
    def test_delete_evidence_allows_superuser_without_owner_filter(self, mock_get):
        evidence = MagicMock()
        mock_get.return_value = evidence

        result = DeleteEvidence().mutate(self._make_info(), evidence_id="ev-1")

        self.assertTrue(result.ok)
        mock_get.assert_called_once_with(id="ev-1")
        evidence.delete.assert_called_once()

    @patch("ach.schema.ACHAnalysis.objects.get")
    def test_delete_analysis_allows_superuser_without_owner_filter(self, mock_get):
        analysis = MagicMock()
        mock_get.return_value = analysis

        result = DeleteACHAnalysis().mutate(self._make_info(), analysis_id="an-1")

        self.assertTrue(result.ok)
        mock_get.assert_called_once_with(id="an-1")
        analysis.delete.assert_called_once()
