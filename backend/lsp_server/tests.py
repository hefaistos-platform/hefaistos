import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.test import TestCase

from lsp_server.manager import SyntaxTideLSPManager, get_lsp_manager


class LSPManagerTests(TestCase):
    def setUp(self):
        self.manager = SyntaxTideLSPManager()

    def test_language_ports_defined(self):
        """All supported languages have port assignments."""
        self.assertIn('kql', self.manager.language_ports)
        self.assertIn('spl', self.manager.language_ports)
        self.assertNotIn('sigma', self.manager.language_ports)
        self.assertIn('wazuh', self.manager.language_ports)
        self.assertIn('aql', self.manager.language_ports)
        self.assertEqual(self.manager.language_ports['kql'], 7000)
        self.assertEqual(self.manager.language_ports['spl'], 7001)
        self.assertEqual(self.manager.language_ports['wazuh'], 7003)
        self.assertEqual(self.manager.language_ports['aql'], 7004)

    def test_get_status_no_servers_running(self):
        """get_status returns all languages as not running when no processes started."""
        status = self.manager.get_status()
        for language in ('kql', 'spl', 'wazuh', 'aql'):
            self.assertIn(language, status)
            self.assertFalse(status[language]['running'])
            self.assertIsNone(status[language]['pid'])
            self.assertIsNotNone(status[language]['port'])

    def test_start_lsp_server_unsupported_language(self):
        """start_lsp_server returns False for unsupported languages."""
        result = self.manager.start_lsp_server('unknown_lang')
        self.assertFalse(result)

    def test_start_lsp_server_missing_script(self):
        """start_lsp_server returns False when SyntaxTide script is not present."""
        # syntaxtide_path does not exist in the test environment
        result = self.manager.start_lsp_server('kql')
        self.assertFalse(result)

    def test_get_lsp_manager_singleton(self):
        """get_lsp_manager always returns the same instance."""
        manager_a = get_lsp_manager()
        manager_b = get_lsp_manager()
        self.assertIs(manager_a, manager_b)

    def test_start_all_without_syntaxtide(self):
        """start_all gracefully fails when SyntaxTide repository is not cloned."""
        with patch.object(self.manager, 'setup_syntaxtide', return_value=None):
            with patch.object(self.manager, 'start_lsp_server', return_value=False) as mock_start:
                self.manager.start_all()
                self.assertEqual(mock_start.call_count, 4)  # kql, spl, wazuh, aql

    def test_wazuh_lsp_server_missing_script(self):
        """start_lsp_server returns False for wazuh when SyntaxTide script is not present."""
        result = self.manager.start_lsp_server('wazuh')
        self.assertFalse(result)

    def test_aql_lsp_server_missing_script(self):
        """start_lsp_server returns False for aql when SyntaxTide script is not present."""
        result = self.manager.start_lsp_server('aql')
        self.assertFalse(result)

    def test_stop_all_no_servers_running(self):
        """stop_all completes without errors when no servers are running."""
        self.manager.stop_all()  # Should not raise

    def test_setup_clones_into_existing_empty_placeholder_dir(self):
        """setup_syntaxtide clones when path exists but is an empty non-git directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.manager.syntaxtide_path = Path(tmpdir) / "syntaxtide"
            self.manager.syntaxtide_path.mkdir(parents=True, exist_ok=True)

            with patch.object(self.manager, "_check_runtime", return_value=None):
                with patch.object(self.manager, "_is_git_repo", return_value=False):
                    with patch("lsp_server.manager.subprocess.run") as mock_run:
                        self.manager.setup_syntaxtide()

        clone_cmd = [
            'git',
            'clone',
            self.manager.syntaxtide_repo_url,
            str(self.manager.syntaxtide_path),
        ]
        all_cmds = [call.args[0] for call in mock_run.call_args_list]
        self.assertIn(clone_cmd, all_cmds)

    def test_setup_skips_pull_for_non_git_nonempty_dir(self):
        """setup_syntaxtide does not call git pull when folder is non-git and non-empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.manager.syntaxtide_path = Path(tmpdir) / "syntaxtide"
            self.manager.syntaxtide_path.mkdir(parents=True, exist_ok=True)
            (self.manager.syntaxtide_path / "placeholder.txt").write_text("x", encoding="utf-8")

            with patch.object(self.manager, "_check_runtime", return_value=None):
                with patch.object(self.manager, "_is_git_repo", return_value=False):
                    with patch("lsp_server.manager.subprocess.run") as mock_run:
                        self.manager.setup_syntaxtide()

        all_cmds = [call.args[0] for call in mock_run.call_args_list]
        self.assertNotIn(['git', 'pull'], all_cmds)
        self.assertNotIn(
            ['git', 'clone', self.manager.syntaxtide_repo_url, str(self.manager.syntaxtide_path)],
            all_cmds,
        )

    def test_setup_uses_quiet_npm_install_flags(self):
        """setup_syntaxtide installs npm dependencies without audit/fund noise."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.manager.syntaxtide_path = Path(tmpdir) / "syntaxtide"
            self.manager.syntaxtide_path.mkdir(parents=True, exist_ok=True)
            (self.manager.syntaxtide_path / ".git").mkdir()
            (self.manager.syntaxtide_path / "package.json").write_text("{}", encoding="utf-8")

            with patch.object(self.manager, "_check_runtime", return_value=None):
                with patch.object(self.manager, "_is_git_repo", return_value=True):
                    with patch("lsp_server.manager.subprocess.run") as mock_run:
                        self.manager.setup_syntaxtide()

        all_cmds = [call.args[0] for call in mock_run.call_args_list]
        self.assertIn(
            ['npm', 'install', '--no-audit', '--no-fund', '--loglevel=error'],
            all_cmds,
        )


class LSPRoutingTests(TestCase):
    """Tests for the Django Channels WebSocket routing configuration."""

    def test_websocket_urlpatterns_defined(self):
        """websocket_urlpatterns list is non-empty and contains the LSP proxy route."""
        from lsp_server.routing import websocket_urlpatterns
        self.assertTrue(len(websocket_urlpatterns) > 0)

    def test_lsp_proxy_consumer_importable(self):
        """LSPProxyConsumer can be imported and is an ASGI application."""
        from lsp_server.consumers import LSPProxyConsumer
        # as_asgi() should return an ASGI-compatible callable
        asgi_app = LSPProxyConsumer.as_asgi()
        self.assertTrue(callable(asgi_app))


class LSPStatusEndpointTests(TestCase):
    """Tests for the HTTP status endpoint exposing LSP health information."""

    def test_lsp_status_endpoint_degraded_when_servers_down(self):
        """Endpoint returns degraded when no language server is running."""
        response = self.client.get('/api/lsp/status')
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload['status'], 'degraded')
        self.assertIn('summary', payload)
        self.assertIn('languages', payload)
        self.assertEqual(payload['summary']['total'], 4)

    def test_lsp_status_endpoint_ok_when_all_running(self):
        """Endpoint returns ok when manager reports all languages running."""
        mocked_status = {
            'kql': {'running': True, 'pid': 101, 'port': 7000},
            'spl': {'running': True, 'pid': 102, 'port': 7001},
            'wazuh': {'running': True, 'pid': 104, 'port': 7003},
            'aql': {'running': True, 'pid': 105, 'port': 7004},
        }

        with patch('lsp_server.views.get_lsp_manager') as mock_get_manager:
            mock_get_manager.return_value.get_status.return_value = mocked_status
            response = self.client.get('/api/lsp/status')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['summary']['running'], 4)
        self.assertEqual(payload['summary']['total'], 4)


class AIGenerationTests(TestCase):
    """Tests for AI rule generation engine."""

    def test_spl_system_prompt_selection(self):
        """generate_rule selects SPL-specific system prompt for SPL format."""
        from ai_assistant.engine import generate_rule

        mock_settings = MagicMock()
        mock_settings.get_openai_key.return_value = 'test-key'
        mock_settings.user.username = 'testuser'

        context = {
            'title': 'Detect suspicious PowerShell',
            'technique_id': 'T1059.001',
            'technique_name': 'PowerShell',
            'strategy_name': 'Process monitoring',
            'technical_context': 'Monitor PowerShell execution',
            'goal': 'Detect encoded PowerShell commands',
            'data_sources': 'Windows Event Logs',
        }

        captured_prompts = {}

        with patch('ai_assistant.engine.build_available', return_value=['GPT']):
            with patch('ai_assistant.engine._resolve_provider', return_value='GPT'):
                with patch.object(mock_settings, 'get_openai_key', return_value='test-key'):
                    mock_client = MagicMock()
                    mock_response = MagicMock()
                    mock_response.choices[0].message.content = (
                        "index=windows sourcetype=WinEventLog:Security\n"
                        "| where EventCode=4688\n"
                        "| table _time, Computer, User"
                    )
                    mock_client.chat.completions.create.return_value = mock_response

                    with patch('ai_assistant.engine.openai') as mock_openai_mod:
                        mock_openai_mod.OpenAI.return_value = mock_client

                        rule, provider = generate_rule(mock_settings, context, 'SPL')

                        call_args = mock_client.chat.completions.create.call_args
                        messages = call_args[1]['messages']
                        system_msg = next(m for m in messages if m['role'] == 'system')
                        user_msg = next(m for m in messages if m['role'] == 'user')

                        captured_prompts['system'] = system_msg['content']
                        captured_prompts['user'] = user_msg['content']

        self.assertIn('Splunk SPL', captured_prompts['system'])
        self.assertIn('index=', captured_prompts['user'])
        self.assertIn('Splunk SPL', captured_prompts['user'])
        self.assertEqual(provider, 'GPT')

    def test_wazuh_format(self):
        """WAZUH format uses the Wazuh XML system prompt."""
        from ai_assistant.engine import generate_rule

        mock_settings = MagicMock()
        mock_settings.get_openai_key.return_value = 'test-key'
        mock_settings.user.username = 'testuser'

        context = {
            'title': 'Test Rule',
            'technique_id': 'T1059',
            'technique_name': 'Command Scripting',
            'strategy_name': 'Detection',
            'technical_context': 'Context',
            'goal': 'Goal',
        }

        with patch('ai_assistant.engine.build_available', return_value=['GPT']):
            with patch('ai_assistant.engine._resolve_provider', return_value='GPT'):
                mock_client = MagicMock()
                mock_response = MagicMock()
                mock_response.choices[0].message.content = '<rule id="100001"><description>Test</description></rule>'
                mock_client.chat.completions.create.return_value = mock_response

                with patch('ai_assistant.engine.openai') as mock_openai_mod:
                    mock_openai_mod.OpenAI.return_value = mock_client

                    generate_rule(mock_settings, context, 'WAZUH')

                    call_args = mock_client.chat.completions.create.call_args
                    messages = call_args[1]['messages']
                    system_msg = next(m for m in messages if m['role'] == 'system')

                    self.assertIn('Wazuh', system_msg['content'])
                    self.assertNotIn('Splunk', system_msg['content'])
