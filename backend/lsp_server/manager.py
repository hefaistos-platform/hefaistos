"""
SyntaxTide LSP Server Manager

Manages lifecycle of Language Server Protocol servers for detection rule editing.
"""

import subprocess
import os
import signal
import logging
import shutil
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class SyntaxTideLSPManager:
    """
    Manage SyntaxTide LSP server processes

    Responsibilities:
    - Clone/update SyntaxTide repository
    - Start LSP servers for KQL, SPL, Sigma
    - Provide WebSocket endpoints for Monaco Editor
    - Handle server lifecycle (restart on crash)
    """

    REQUIRED_BINARIES = ("git", "node", "npm")

    def __init__(self, syntaxtide_repo_url='https://github.com/OpenTideHQ/SyntaxTide.git'):
        self.syntaxtide_repo_url = syntaxtide_repo_url
        self.syntaxtide_path = Path('/app/syntaxtide')
        self.bridge_script = Path('/app/lsp_server/syntaxtide_tcp_bridge.js')
        self.processes: Dict[str, subprocess.Popen] = {}
        self.base_port = 7000

        # Language to port mapping
        self.language_ports = {
            'kql': 7000,
            'spl': 7001,
            'wazuh': 7003,
            'aql': 7004,
        }

    def _check_runtime(self) -> Optional[str]:
        """Return the name of the first missing required binary, or None if all are present."""
        for binary in self.REQUIRED_BINARIES:
            if shutil.which(binary) is None:
                return binary
        return None

    def _is_git_repo(self, path: Path) -> bool:
        """Return True when path points to a valid git working tree."""
        if not (path / '.git').exists():
            return False

        result = subprocess.run(
            ['git', 'rev-parse', '--is-inside-work-tree'],
            cwd=path,
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and result.stdout.strip() == 'true'

    def setup_syntaxtide(self):
        """Clone or update SyntaxTide repository and install dependencies."""
        missing = self._check_runtime()
        if missing:
            raise RuntimeError(
                f"SyntaxTide LSP disabled: `{missing}` is not installed in this runtime. "
                "Install Node.js 20+ (which provides npm) or set ENABLE_LSP_SERVERS=false."
            )

        should_clone = False
        if self.syntaxtide_path.exists():
            if self._is_git_repo(self.syntaxtide_path):
                logger.info("SyntaxTide already exists at %s, pulling latest", self.syntaxtide_path)
                try:
                    subprocess.run(
                        ['git', 'pull'],
                        cwd=self.syntaxtide_path,
                        check=True,
                        capture_output=True,
                    )
                except subprocess.CalledProcessError as e:
                    logger.warning("Failed to pull SyntaxTide updates: %s", e)
            else:
                # Repository copy includes an empty /app/syntaxtide placeholder directory.
                # Clone into it on first run instead of trying `git pull` on a non-repo.
                if any(self.syntaxtide_path.iterdir()):
                    logger.warning(
                        "SyntaxTide path %s exists but is not a git repository; "
                        "skipping update and using existing files.",
                        self.syntaxtide_path,
                    )
                else:
                    should_clone = True
        else:
            should_clone = True

        if should_clone:
            logger.info("Cloning SyntaxTide to %s", self.syntaxtide_path)
            self.syntaxtide_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ['git', 'clone', self.syntaxtide_repo_url, str(self.syntaxtide_path)],
                check=True,
            )

        # Install Node dependencies if needed
        package_json = self.syntaxtide_path / 'package.json'
        if package_json.exists():
            logger.info("Installing SyntaxTide dependencies")
            subprocess.run(
                ['npm', 'install', '--no-audit', '--no-fund', '--loglevel=error'],
                cwd=self.syntaxtide_path,
                check=True,
            )

    def _resolve_server_script(self) -> Optional[Path]:
        """Find the SyntaxTide server entrypoint across old/new repo layouts."""
        candidates = (
            self.syntaxtide_path / 'server' / 'main.js',  # legacy layout
            self.syntaxtide_path / 'out' / 'server.js',   # current layout
        )
        for candidate in candidates:
            if candidate.exists():
                return candidate

        # Fallback for source-only checkouts where compiled output is missing
        ts_source = self.syntaxtide_path / 'src' / 'server.ts'
        if ts_source.exists():
            logger.info("SyntaxTide server output not found, attempting TypeScript compile")
            try:
                subprocess.run(['npm', 'run', 'compile'], cwd=self.syntaxtide_path, check=True)
            except subprocess.CalledProcessError as exc:
                logger.error("SyntaxTide compile failed: %s", exc)
                return None

            compiled = self.syntaxtide_path / 'out' / 'server.js'
            if compiled.exists():
                return compiled

        return None

    def start_lsp_server(self, language: str) -> bool:
        """
        Start LSP server for specific language.

        Args:
            language: One of 'kql', 'spl', 'wazuh', 'aql'

        Returns:
            bool: True if server started successfully
        """
        if language not in self.language_ports:
            logger.error("Unsupported language: %s", language)
            return False

        if language in self.processes:
            logger.info("LSP server for %s already running", language)
            return True

        port = self.language_ports[language]

        # SyntaxTide server entrypoint
        server_script = self._resolve_server_script()

        if server_script is None:
            logger.error(
                "SyntaxTide server script not found in expected locations under %s",
                self.syntaxtide_path,
            )
            return False

        if not self.bridge_script.exists():
            logger.error("SyntaxTide TCP bridge script not found: %s", self.bridge_script)
            return False

        logger.info("Starting LSP server for %s on port %d using %s", language, port, server_script)

        try:
            process = subprocess.Popen(
                [
                    'node',
                    str(self.bridge_script),
                    '--server',
                    str(server_script),
                    '--language',
                    language,
                    '--port',
                    str(port),
                ],
                cwd=self.syntaxtide_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,  # Creates a new session (thread-safe process group isolation)
            )

            self.processes[language] = process
            logger.info("LSP server for %s started (PID: %d)", language, process.pid)
            return True

        except Exception as e:
            logger.error("Failed to start LSP server for %s: %s", language, e)
            return False

    def stop_lsp_server(self, language: str):
        """
        Stop LSP server for specific language.

        Args:
            language: One of 'kql', 'spl', 'wazuh', 'aql'
        """
        process = self.processes.get(language)
        if not process:
            logger.warning("No LSP server running for %s", language)
            return

        logger.info("Stopping LSP server for %s (PID: %d)", language, process.pid)

        try:
            # Send SIGTERM to process group
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=5)
            logger.info("LSP server for %s stopped gracefully", language)
        except subprocess.TimeoutExpired:
            logger.warning("LSP server for %s did not stop, sending SIGKILL", language)
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception as e:
            logger.error("Error stopping LSP server for %s: %s", language, e)
        finally:
            self.processes.pop(language, None)

    def start_all(self):
        """Start LSP servers for all supported languages."""
        logger.info("Starting all SyntaxTide LSP servers")

        try:
            self.setup_syntaxtide()
        except Exception as e:
            logger.error("Failed to setup SyntaxTide: %s", e)
            logger.warning("LSP servers will not be available. Continuing without LSP support.")
            return

        for language in self.language_ports:
            try:
                self.start_lsp_server(language)
            except Exception as e:
                logger.error("Failed to start %s LSP server: %s", language, e)

    def stop_all(self):
        """Stop all running LSP servers."""
        logger.info("Stopping all SyntaxTide LSP servers")

        for language in list(self.processes.keys()):
            self.stop_lsp_server(language)

    def restart_lsp_server(self, language: str):
        """
        Restart LSP server for specific language.

        Args:
            language: One of 'kql', 'spl', 'wazuh', 'aql'
        """
        logger.info("Restarting LSP server for %s", language)
        self.stop_lsp_server(language)
        self.start_lsp_server(language)

    def get_status(self) -> Dict[str, Dict]:
        """
        Get status of all LSP servers.

        Returns:
            dict: Language -> status info
        """
        status = {}

        for language, port in self.language_ports.items():
            process = self.processes.get(language)
            if process:
                is_running = process.poll() is None
                status[language] = {
                    'running': is_running,
                    'pid': process.pid if is_running else None,
                    'port': port,
                }
            else:
                status[language] = {
                    'running': False,
                    'pid': None,
                    'port': port,
                }

        return status


# Global instance
_lsp_manager: Optional[SyntaxTideLSPManager] = None


def get_lsp_manager() -> SyntaxTideLSPManager:
    """
    Get or create global LSP manager instance.

    Returns:
        SyntaxTideLSPManager: Global LSP manager
    """
    global _lsp_manager
    if _lsp_manager is None:
        _lsp_manager = SyntaxTideLSPManager()
    return _lsp_manager
