import logging
import yaml
import re
import shutil
import json
import os
import git
from github import Github
from urllib.parse import urlparse
from hefaistos_sdk.connector import BaseConnector

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


_TITLE_PATTERN = re.compile(r'^\s*(?://|#|--)?\s*title\s*:\s*(.+?)\s*$', re.IGNORECASE)


def _normalize_rule_title(value):
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    match = _TITLE_PATTERN.match(value)
    if match:
        normalized = match.group(1).strip()
        return normalized or None
    return value


def _extract_title_from_rule_content(rule_content):
    if not rule_content:
        return None
    for line in rule_content.splitlines():
        normalized = _normalize_rule_title(line)
        if normalized and normalized != line.strip():
            return normalized
    return None


def _build_safe_name(playbook, rule_content=None):
    base_name = playbook.get('analytic_id')
    if not base_name:
        base_name = _extract_title_from_rule_content(rule_content) or playbook.get('title')
    base_name = _normalize_rule_title(base_name) or "rule"
    safe_name = re.sub(r'[^a-z0-9]+', '-', base_name.lower()).strip('-')
    return safe_name or "rule"


def _get_file_extension(rule_format):
    if (rule_format or "").upper() == "KQL":
        return "kql"
    return "yml"




def push_to_git(repo_url, playbook, yaml_content, target_folder=None, rule_format=None):
    """
    Clones, branches, commits, and pushes a playbook as a YAML file.
    
    Args:
        repo_url: Git repository URL with credentials
        playbook: Playbook dict with title, id, etc.
        yaml_content: The YAML content to write
        target_folder: Optional folder path within the repo (e.g., 'rules/kql')
    """
    # 1. Sanitize title for branch and file name
    # "My Playbook [Test]" -> "my-playbook-test"
    safe_name = _build_safe_name(playbook, yaml_content)
    extension = _get_file_extension(rule_format)

    branch_name = f"hefaistos/add-{safe_name}"
    file_name = f"{safe_name}.{extension}"

    # Use a unique clone path for each job to avoid conflicts
    clone_path = f"/tmp/git_pushes/{playbook['id']}"

    repo = None
    try:
        # 2. Clone the repo
        logger.info(f"Cloning repo to {clone_path}...")
        repo = git.Repo.clone_from(repo_url, clone_path)

        # 3. Create and check out the new branch
        logger.info(f"Creating new branch: {branch_name}")
        new_branch = repo.create_head(branch_name)
        new_branch.checkout()

        # 4. Determine the file path (with optional folder)
        if target_folder:
            # Sanitize the target folder path (remove leading/trailing slashes)
            target_folder = target_folder.strip('/')
            folder_path = os.path.join(clone_path, target_folder)
            
            # Create the folder if it doesn't exist
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
                logger.info(f"Created target folder: {target_folder}")
            
            file_path = os.path.join(folder_path, file_name)
        else:
            file_path = os.path.join(clone_path, file_name)

        # 5. Write the file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(yaml_content)
        logger.info(f"Wrote rule content to {file_path}")

        # 6. Add and Commit
        repo.index.add([file_path])
        folder_info = f" in '{target_folder}'" if target_folder else ""
        commit_message = f"HEFAISTOS: Add playbook '{playbook['title']}'{folder_info}"
        repo.index.commit(commit_message)
        logger.info(f"Committed new file with message: {commit_message}")

        # 7. Push to origin
        origin = repo.remote(name='origin')
        origin.push(refspec=f"{branch_name}:{branch_name}")
        logger.info(f"Successfully pushed branch '{branch_name}' to origin.")

        return True

    except git.exc.GitCommandError as e:
        logger.error(f"Git command failed: {e}")
        if "remote: Permission" in str(e):
            logger.error("Authentication Error: Check your username and token.")
        elif "already exists" in str(e):
            logger.warning(f"Branch {branch_name} already exists. This push may have been processed before.")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during Git operations: {e}")
        return False
    finally:
        # 8. Clean up the clone directory
        if os.path.exists(clone_path):
            logger.info(f"Cleaning up clone directory: {clone_path}")
            shutil.rmtree(clone_path)


def open_pull_request(repo_url, repo_token, branch_name, playbook_title):
    """
    Attempts to open a Pull Request on GitHub.
    """
    logger.info(f"Attempting to open Pull Request for branch: {branch_name}")
    try:
        # 1. Parse the repo URL to get "org/repo"
        path = urlparse(repo_url).path
        # Remove '.git' and leading '/'
        repo_name = path.strip('/').replace('.git', '') 

        # 2. Authenticate to GitHub API
        g = Github(repo_token)
        repo = g.get_repo(repo_name)

        # 3. Create the PR
        pr = repo.create_pull(
            title=f"HEFAISTOS: Integrate Playbook '{playbook_title}'",
            body=f"This PR was automatically generated by the HEFAISTOS platform.\n\n**Playbook:** {playbook_title}\n**Branch:** {branch_name}",
            head=branch_name,
            base="main" # or 'master'
        )

        logger.info(f"Successfully created Pull Request: {pr.html_url}")
        return True

    except Exception as e:
        logger.error(f"Failed to open Pull Request: {e}")
        # This is a non-critical failure, so we don't return False
        # The push already succeeded.
        return False




class GitPushConnector(BaseConnector):
    """
    Listens for 'playbook.git.push.requested' events,
    fetches playbook data, formats it as YAML,
    and pushes it to the specified Git repository.
    """

    def get_queue_bindings(self):
        """Defines what this connector listens to."""
        return [
            ('git_push_queue', 'playbook.git.push.requested')
        ]

    def process_message(self, routing_key, payload):
        """
        This is the core logic. It is called by BaseConnector.
        Handles two message formats:
        1. New format (push_rule): rule content directly in payload
        2. Legacy format (push_playbook): fetches playbook from API
        """
        action = payload.get('action')
        target_folder = payload.get('target_folder')  # Optional folder path
        
        # --- NEW FORMAT: Push individual rule ---
        if action == 'push_rule':
            rule_id = payload.get('rule_id')
            repository_id = payload.get('repository_id')
            rule_data = payload.get('rule', {})
            config = payload.get('config', {})
            
            if not rule_id or not repository_id:
                logger.error("Message missing 'rule_id' or 'repository_id'. Discarding.")
                return True
            
            logger.info(f"Processing Git Push request for rule_id: {rule_id} to repo_id: {repository_id}")
            
            # Build repo URL with credentials from config
            repo_url = config.get('url')
            if not repo_url:
                logger.error("Repository URL is missing in config. Discarding.")
                return True

            if config.get('username') and config.get('token'):
                logger.info("Private repository credentials found in config.")
                repo_url = repo_url.replace("https://", f"https://{config['username']}:{config['token']}@")
            
            # Build a playbook-like dict for compatibility with push_to_git
            playbook = {
                'id': rule_id,
                'title': rule_data.get('title', 'Untitled Rule'),
                'analytic_id': None,
            }
            
            yaml_content = rule_data.get('rule_content', '')
            if not yaml_content:
                logger.error(f"Rule {rule_id} has no rule_content. Discarding.")
                return True
            
            # Determine target folder based on rule format if not specified
            rule_format = rule_data.get('format', 'OTHER').upper()
            if not target_folder:
                # Auto-organize by format
                format_folders = {
                    'KQL': 'rules/kql',
                    'WAZUH': 'rules/wazuh',
                    'SPL': 'rules/splunk',
                    'OTHER': 'rules/other',
                }
                target_folder = format_folders.get(rule_format, 'rules')
                logger.info(f"Auto-selected target folder '{target_folder}' for format '{rule_format}'")
            
            push_success = push_to_git(repo_url, playbook, yaml_content, target_folder, rule_format)
            
            if not push_success:
                logger.error("Git push failed. Re-queueing message.")
                return False
            
            # Open PR for GitHub repos
            if "github.com" in config.get('url', '') and config.get('token'):
                safe_name = _build_safe_name(playbook, yaml_content)
                branch_name = f"hefaistos/add-{safe_name}"
                open_pull_request(config['url'], config['token'], branch_name, playbook['title'])
            
            logger.info(f"Successfully pushed rule {rule_id} to {config.get('url')}.")
            return True
        
        # --- LEGACY FORMAT: Push full playbook ---
        playbook_id = payload.get('playbook_id')
        repository_id = payload.get('repository_id')

        if not playbook_id or not repository_id:
            logger.error("Message missing 'playbook_id' or 'repository_id'. Discarding.")
            return True # ACK - can't process a bad message

        logger.info(f"Processing Git Push request for playbook_id: {playbook_id} to repo_id: {repository_id}")

        # --- 1. Fetch Repository Details (URL, Token) ---
        logger.info(f"Fetching details for repository: {repository_id}")
        # We use the 'get_repository_details' SDK method from Day 156
        repo_data = self.api_client.get_repository_details(repository_id)

        if not repo_data or not repo_data.get('ruleRepository'):
            logger.error(f"Could not find repo details for {repository_id}. Discarding.")
            return True # ACK - repo doesn't exist

        repo = repo_data['ruleRepository']
        repo_url = repo['url']

        # Check for auth (token is decrypted by the backend API)
        if repo.get('username') and repo.get('token'):
            logger.info("Private repository credentials found.")
            repo_url = repo_url.replace("https://", f"https://{repo['username']}:{repo['token']}@")
        else:
            logger.info("Public repository, no credentials needed.")

        # --- 2. Fetch Full Playbook Data ---
        logger.info(f"Fetching full playbook data for: {playbook_id}")
        # We use the 'get_full_playbook_details' SDK method from Day 172
        playbook_data = self.api_client.get_full_playbook_details(playbook_id)

        if not playbook_data or not playbook_data.get('playbook'):
            logger.error(f"Could not find playbook data for {playbook_id}. Retrying.")
            return False # NACK - requeue, this might be a temporary issue

        playbook = playbook_data['playbook']

        # --- 3. Format Playbook to YAML ---
        try:
            yaml_content = yaml.dump(playbook, Dumper=yaml.SafeDumper, sort_keys=False, allow_unicode=True)
            if not yaml_content:
                raise Exception("Formatter returned empty content.")
        except Exception as e:
            logger.error(f"Failed to format playbook {playbook_id} to YAML: {e}")
            return True # ACK - a formatting error is not a retryable issue

        logger.info(f"Successfully formatted playbook '{playbook['title']}'.")

        # --- 4. Push to Git (with optional target folder) ---
        push_success = push_to_git(repo_url, playbook, yaml_content, target_folder)

        if not push_success:
            logger.error("Git push failed. Re-queueing message.")
            return False # NACK - requeue and try again

        # --- 5. STRETCH GOAL: Open Pull Request ---
        if "github.com" in repo['url'] and repo.get('token'):
            # We can only do this if it's GitHub and we have a token
            # Correcting branch name to match push_to_git logic
            safe_name = _build_safe_name(playbook, yaml_content)
            branch_name = f"hefaistos/add-{safe_name}"

            open_pull_request(
                repo['url'], 
                repo['token'], 
                branch_name, 
                playbook['title']
            )
        # --- END STRETCH GOAL ---

        logger.info(f"Successfully pushed playbook {playbook_id} to {repo['url']}.")
        return True # Success (ACK)


if __name__ == '__main__':
    logger.info("--- Starting HEFAISTOS Git Push Connector (SDK v1.0) ---")
    connector = GitPushConnector(service_name="GitPushConnector")
    connector.start_consuming()
