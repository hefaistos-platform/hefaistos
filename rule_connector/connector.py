import logging
import os
import json
import glob
import shutil
import subprocess
import yaml
import re
from hefaistos_sdk.connector import BaseConnector
from rag_sync import QdrantTemplateStore, collect_templates_from_repo

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_GIT_SYNC_TIMEOUT_SECONDS = 600
try:
    _git_timeout_raw = int(os.environ.get('RULE_CONNECTOR_GIT_SYNC_TIMEOUT_SECONDS', DEFAULT_GIT_SYNC_TIMEOUT_SECONDS))
    GIT_SYNC_TIMEOUT_SECONDS = max(_git_timeout_raw, 30)
except (TypeError, ValueError):
    GIT_SYNC_TIMEOUT_SECONDS = DEFAULT_GIT_SYNC_TIMEOUT_SECONDS


def detect_format_from_content(content, filepath):
    """
    Detect the actual format of rule content by inspecting patterns.
    Returns: 'KQL', 'SIGMA', or 'UNKNOWN'
    
    Heuristics:
    - KQL: starts with //, contains |, where, project, let, or KQL table names
    - SIGMA: contains title:, logsource:, detection:, status: as YAML keys
    - UNKNOWN: doesn't match either pattern
    """
    if not content or not content.strip():
        logger.debug(f"[FORMAT_DETECTION] Empty content for {filepath}")
        return 'UNKNOWN'
    
    # Normalize content for analysis
    first_500_chars = content[:500].strip()
    lines = content.split('\n')[:20]  # Check first 20 lines
    
    # KQL detection patterns
    kql_indicators = [
        r'^\s*//\s+',  # Starts with // comment
        r'\|\s*(where|project|summarize|extend|join|group|sort)',  # Pipe followed by KQL operators
        r'\blet\s+\w+\s*=',  # let statement
        r'\b(DeviceProcessEvents|DeviceNetworkEvents|DeviceFileEvents|SecurityEvent|SigninLogs|AuditLogs|CommonSecurityLog|Syslog|Event|WindowsEvent|OfficeActivity|CloudAppEvents|IdentityLogonEvents|IdentityQueryEvents|IdentityDirectoryEvents)\b',  # KQL table names
    ]
    
    # SIGMA detection patterns
    sigma_indicators = [
        r'^\s*title\s*:',
        r'^\s*logsource\s*:',
        r'^\s*detection\s*:',
        r'^\s*status\s*:\s*(experimental|test|stable|deprecated)',
        r'^\s*falsepositives\s*:',
    ]
    
    kql_matches = 0
    sigma_matches = 0
    
    # Check each line for pattern matches
    for line in lines:
        for pattern in kql_indicators:
            if re.search(pattern, line, re.IGNORECASE):
                kql_matches += 1
                logger.debug(f"[FORMAT_DETECTION] KQL pattern matched in {filepath}: {pattern[:30]}...")
        
        for pattern in sigma_indicators:
            if re.search(pattern, line):
                sigma_matches += 1
                logger.debug(f"[FORMAT_DETECTION] SIGMA pattern matched in {filepath}: {pattern[:30]}...")
    
    # Decision logic
    if kql_matches > sigma_matches and kql_matches > 0:
        logger.info(f"[FORMAT_DETECTION] {filepath} detected as KQL (KQL:{kql_matches} vs SIGMA:{sigma_matches})")
        return 'KQL'
    elif sigma_matches > 0:
        logger.info(f"[FORMAT_DETECTION] {filepath} detected as SIGMA (KQL:{kql_matches} vs SIGMA:{sigma_matches})")
        return 'SIGMA'
    else:
        logger.warning(f"[FORMAT_DETECTION] {filepath} format unknown (KQL:{kql_matches} vs SIGMA:{sigma_matches})")
        return 'UNKNOWN'


def parse_kql_file(content, filepath):
    """
    Parse a KQL file and extract metadata from comments.
    KQL files typically have metadata in comments at the top:
    // Title: My Rule
    // Description: Detects something
    // Author: Someone
    // Tags: attack.t1059, attack.execution
    """
    lines = content.split('\n')
    metadata = {
        'title': None,
        'description': None,
        'author': None,
        'tags': [],
        'references': [],
        'level': None,
        'status': 'experimental',
    }
    
    # Try to extract metadata from comment headers
    for line in lines:
        line = line.strip()
        if not line.startswith('//'):
            continue
        
        # Remove comment prefix
        comment = line[2:].strip()
        
        # Parse key: value patterns
        if ':' in comment:
            key, _, value = comment.partition(':')
            key = key.strip().lower()
            value = value.strip()
            
            if key == 'title' and value:
                metadata['title'] = value
            elif key == 'description' and value:
                metadata['description'] = value
            elif key == 'author' and value:
                metadata['author'] = value
            elif key in ('tags', 'tag') and value:
                # Tags can be comma-separated
                metadata['tags'].extend([t.strip() for t in value.split(',') if t.strip()])
            elif key in ('reference', 'references', 'ref') and value:
                metadata['references'].append(value)
            elif key == 'level' and value:
                metadata['level'] = value
            elif key == 'status' and value:
                metadata['status'] = value
    
    # If no title found, use filename
    if not metadata['title']:
        filename = os.path.basename(filepath)
        metadata['title'] = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ').title()
    
    return metadata


def parse_kql_markdown_file(content, filepath):
    """
    Parse a Markdown file containing KQL queries in code blocks.
    Extracts the KQL query from ```kql or ``` code blocks.
    Also extracts metadata from markdown headers and content.
    """
    metadata = {
        'title': None,
        'description': None,
        'author': None,
        'tags': [],
        'references': [],
        'level': None,
        'status': 'experimental',
    }
    
    lines = content.split('\n')
    
    # Extract title from first H1 or H2 header
    for line in lines:
        line_stripped = line.strip()
        if line_stripped.startswith('# '):
            metadata['title'] = line_stripped[2:].strip()
            break
        elif line_stripped.startswith('## ') and not metadata['title']:
            metadata['title'] = line_stripped[3:].strip()
            break
    
    # Extract description - look for text after title, before code block
    in_description = False
    description_lines = []
    for line in lines:
        line_stripped = line.strip()
        if line_stripped.startswith('#'):
            if metadata['title'] and line_stripped.lstrip('#').strip() == metadata['title']:
                in_description = True
                continue
        if in_description:
            if line_stripped.startswith('```'):
                break
            if line_stripped and not line_stripped.startswith('#'):
                description_lines.append(line_stripped)
    
    if description_lines:
        metadata['description'] = ' '.join(description_lines[:3])  # First 3 lines as description
    
    # Extract KQL code blocks - match ```kql, ```kusto, or just ``` followed by KQL-like content
    code_block_pattern = r'```(?:kql|kusto|KQL|Kusto)?\s*\n(.*?)```'
    matches = re.findall(code_block_pattern, content, re.DOTALL | re.IGNORECASE)
    
    # If no language-specific blocks found, try generic code blocks
    if not matches:
        code_block_pattern = r'```\s*\n(.*?)```'
        matches = re.findall(code_block_pattern, content, re.DOTALL)
    
    # Filter to only blocks that look like KQL (contain typical KQL operators)
    kql_keywords = ['|', 'where', 'project', 'summarize', 'extend', 'join', 'let ', 'SecurityEvent', 
                    'DeviceProcessEvents', 'DeviceNetworkEvents', 'DeviceFileEvents', 'SigninLogs',
                    'AuditLogs', 'CommonSecurityLog', 'Syslog', 'Event', 'WindowsEvent']
    
    kql_queries = []
    for match in matches:
        match_stripped = match.strip()
        if any(kw in match_stripped for kw in kql_keywords):
            kql_queries.append(match_stripped)
    
    # If no title found, use filename
    if not metadata['title']:
        filename = os.path.basename(filepath)
        metadata['title'] = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ').title()
    
    # Look for author in content
    author_match = re.search(r'(?:author|by|created by)[:\s]+([^\n\r]+)', content, re.IGNORECASE)
    if author_match:
        metadata['author'] = author_match.group(1).strip()
    
    # Look for MITRE ATT&CK tags
    attack_tags = re.findall(r'T\d{4}(?:\.\d{3})?', content)
    if attack_tags:
        metadata['tags'] = [f'attack.{t.lower()}' for t in set(attack_tags)]
    
    return metadata, kql_queries


class RuleConnector(BaseConnector):
    """
    Listens for 'rule.repo.pull.requested' events and
    syncs/parses the specified Git repository.
    """

    def get_queue_bindings(self):
        """Defines what this connector listens to."""
        return [
            ('rule_sync_queue', 'rule.repo.pull.requested'),
            ('rule_rag_sync_queue', 'rule.repo.rag.sync.requested'),
        ]

    def _redact_git_arg(self, arg):
        """Redact credentials embedded in HTTPS repository URLs before logging."""
        if not isinstance(arg, str):
            return arg
        if arg.startswith('https://') and '@' in arg:
            prefix, _, remainder = arg.partition('https://')
            auth_and_host = remainder.split('@', 1)
            if len(auth_and_host) == 2:
                return f"{prefix}https://***@{auth_and_host[1]}"
        return arg

    def _run_git_command(self, args, cwd=None, allow_failure=False):
        """Run git command with timeout to avoid indefinite connector hangs."""
        command = ['git', *args]
        redacted_command = [self._redact_git_arg(arg) for arg in command]

        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
                timeout=GIT_SYNC_TIMEOUT_SECONDS,
            )
            return (completed.stdout or '').strip()
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"Git command timed out after {GIT_SYNC_TIMEOUT_SECONDS}s: {' '.join(redacted_command)}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or '').strip()
            if allow_failure:
                logger.debug(
                    "Ignoring git command failure (%s): %s",
                    ' '.join(redacted_command),
                    stderr or 'no stderr output',
                )
                return ''
            raise RuntimeError(
                f"Git command failed ({' '.join(redacted_command)}): {stderr or 'no stderr output'}"
            ) from exc

    def _sync_repo_checkout(self, clone_path, repo, repo_url, branch=None):
        """Clone or pull a repository checkout (optionally pinned to branch)."""
        branch_name = (branch or '').strip()
        has_checkout = os.path.isdir(clone_path) and bool(os.listdir(clone_path))
        has_git_dir = os.path.isdir(os.path.join(clone_path, '.git'))

        if has_checkout and not has_git_dir:
            logger.warning(
                "Checkout path %s is not a git repository. Recreating clean checkout.",
                clone_path,
            )
            shutil.rmtree(clone_path, ignore_errors=True)
            has_checkout = False

        if has_checkout and has_git_dir:
            logger.info("Repo exists, pulling changes from %s...", repo.get('url'))
            self._run_git_command(['remote', 'set-url', 'origin', repo_url], cwd=clone_path, allow_failure=True)

            fetch_args = ['fetch', '--depth', '1', 'origin']
            if branch_name:
                fetch_args.append(branch_name)
            self._run_git_command(fetch_args, cwd=clone_path)

            checkout_branch = branch_name or 'hefaistos-sync'
            self._run_git_command(['checkout', '-B', checkout_branch, 'FETCH_HEAD'], cwd=clone_path)
            self._run_git_command(['reset', '--hard', 'HEAD'], cwd=clone_path)
            self._run_git_command(['clean', '-fd'], cwd=clone_path)
            return

        if os.path.isdir(clone_path):
            shutil.rmtree(clone_path, ignore_errors=True)

        os.makedirs(os.path.dirname(clone_path), exist_ok=True)

        clone_args = ['clone', '--depth', '1']
        if branch_name:
            clone_args.extend(['--single-branch', '--branch', branch_name])
        clone_args.extend([repo_url, clone_path])

        logger.info("Cloning repo (shallow) from %s%s...", repo.get('url'), f" [branch={branch_name}]" if branch_name else "")
        self._run_git_command(clone_args)

    def process_message(self, routing_key, payload):
        """Process pull/sync events for rule repositories."""
        if routing_key == 'rule.repo.rag.sync.requested':
            return self.process_rag_sync(payload)

        repo_id = payload.get('repository_id')
        if not repo_id:
            logger.error("Message missing 'repository_id'. Discarding.")
            return True  # ACK - can't process

        logger.info(f"Processing pull request for repository_id: {repo_id}")

        # 1) Get repository details (includes decrypted token for service accounts)
        repo_data = self.api_client.get_repository_details(repo_id)
        if not repo_data or not repo_data.get('ruleRepository'):
            logger.error(f"Could not find repo details for {repo_id}. Discarding.")
            return True  # ACK - nothing to do

        repo = repo_data['ruleRepository']
        repo_url = repo.get('url')
        repo_name = repo.get('name')

        if not repo_url:
            logger.error(f"Repository {repo_id} has no URL. Discarding.")
            return True

        # Handle private repos: inject basic auth into URL
        username = repo.get('username')
        token = repo.get('token')
        if username and token and repo_url.startswith('https://'):
            repo_url = repo_url.replace("https://", f"https://{username}:{token}@", 1)

        clone_path = f"/tmp/rule_repos/{repo_id}"

        # 2) Clone or pull
        # Use shallow clone (depth=1) to speed up large repos like Azure-Sentinel
        try:
            self._sync_repo_checkout(clone_path, repo, repo_url)
        except TimeoutError as e:
            logger.error(f"Timed out while clone/pull repo {repo_id}: {e}")
            return True  # ACK - timeout already logged, avoid queue starvation
        except Exception as e:
            logger.error(f"Failed to clone/pull repo {repo_id}: {e}")
            return False  # NACK - try again later

        # 3) Parse rule files (SIGMA *.yml, KQL *.kql, and KQL in *.md)
        logger.info(f"Parsing rule files in {clone_path}...")
        
        # Find SIGMA files
        sigma_files = glob.glob(f"{clone_path}/**/*.yml", recursive=True)
        # Find KQL files
        kql_files = glob.glob(f"{clone_path}/**/*.kql", recursive=True)
        # Find Markdown files (may contain KQL queries)
        md_files = glob.glob(f"{clone_path}/**/*.md", recursive=True)
        
        logger.info(f"Found {len(sigma_files)} SIGMA (.yml), {len(kql_files)} KQL (.kql), {len(md_files)} Markdown (.md) files")
        
        success_count = 0
        skipped_count = 0
        error_count = 0

        # Process SIGMA and KQL YAML files
        for fpath in sigma_files:
            try:
                with open(fpath, 'r', encoding='utf-8') as fh:
                    raw_yaml = fh.read()
                
                # FIRST: Detect format from content (not just file extension)
                detected_format = detect_format_from_content(raw_yaml, fpath)
                logger.info(f"[PROCESSING] {fpath} - Detected format: {detected_format}")
                
                # If content is KQL but file is .yml, handle as KQL
                if detected_format == 'KQL':
                    logger.info(f"[PROCESSING] Treating {fpath} as KQL (despite .yml extension)")
                    try:
                        metadata = parse_kql_file(raw_yaml, fpath)
                        rule_data = {
                            "repoId": str(repo_id),
                            "title": metadata['title'],
                            "status": metadata['status'],
                            "description": metadata['description'],
                            "author": metadata['author'],
                            "references": metadata['references'] if metadata['references'] else None,
                            "logsource": None,
                            "detection": None,
                            "falsePositives": None,
                            "level": metadata['level'],
                            "tags": metadata['tags'] if metadata['tags'] else None,
                            "rawContent": raw_yaml,
                            "format": "KQL",
                        }
                        resp = self.api_client.upsert_rule(rule_data)
                        if resp and resp.get('upsertRule') and resp['upsertRule'].get('rule'):
                            success_count += 1
                            logger.info(f"[SUCCESS] Upserted KQL rule from .yml file: {metadata['title']}")
                        else:
                            error_count += 1
                            logger.warning(f"[ERROR] Upsert failed for KQL rule {metadata['title']}: {resp}")
                    except Exception as e:
                        error_count += 1
                        logger.warning(f"[ERROR] Failed to parse .yml file as KQL {fpath}: {e}")
                    continue
                
                # Otherwise, try parsing as YAML/SIGMA
                try:
                    rule_doc = yaml.safe_load(raw_yaml)
                except yaml.YAMLError as yaml_err:
                    error_count += 1
                    logger.warning(f"[ERROR] Failed to parse YAML {fpath}: {yaml_err}")
                    continue

                if not isinstance(rule_doc, dict):
                    logger.debug(f"[SKIP] {fpath} - Not a YAML dict after parsing")
                    skipped_count += 1
                    continue

                # Detect if this is a KQL/Sentinel rule or a Sigma rule
                # KQL YAML typically has 'query' field with KQL content, or 'queryFrequency', 'triggerOperator' etc.
                is_kql_yaml = (
                    rule_doc.get('query') and 
                    (rule_doc.get('queryFrequency') or 
                     rule_doc.get('triggerOperator') or
                     rule_doc.get('kind') == 'Scheduled' or
                     rule_doc.get('tactics') or
                     '|' in str(rule_doc.get('query', ''))  # KQL pipe operator
                    )
                )

                if is_kql_yaml:
                    # Process as KQL/Sentinel Analytics Rule
                    title = rule_doc.get('name') or rule_doc.get('displayName') or rule_doc.get('title')
                    if not title:
                        skipped_count += 1
                        continue

                    # Extract tactics/techniques as tags
                    tags = []
                    tactics = rule_doc.get('tactics') or rule_doc.get('relevantTechniques') or []
                    if isinstance(tactics, list):
                        for t in tactics:
                            if isinstance(t, str):
                                tags.append(f'attack.{t.lower().replace(" ", "_")}')
                    
                    techniques = rule_doc.get('techniques') or rule_doc.get('relevantTechniques') or []
                    if isinstance(techniques, list):
                        for t in techniques:
                            if isinstance(t, str) and t.startswith('T'):
                                tags.append(f'attack.{t.lower()}')

                    # Map severity to level
                    severity = rule_doc.get('severity', '').lower()
                    level_map = {'high': 'high', 'medium': 'medium', 'low': 'low', 'informational': 'informational'}
                    level = level_map.get(severity, 'medium')

                    rule_data = {
                        "repoId": str(repo_id),
                        "title": title,
                        "status": rule_doc.get('status', 'experimental'),
                        "description": rule_doc.get('description'),
                        "author": rule_doc.get('author') or rule_doc.get('createdBy'),
                        "references": None,
                        "logsource": None,
                        "detection": None,
                        "falsePositives": None,
                        "level": level,
                        "tags": tags if tags else None,
                        "rawContent": rule_doc.get('query', raw_yaml),  # Store the actual KQL query
                        "format": "KQL",
                    }

                    resp = self.api_client.upsert_rule(rule_data)
                    if resp and resp.get('upsertRule') and resp['upsertRule'].get('rule'):
                        success_count += 1
                    else:
                        error_count += 1
                        logger.warning(f"Upsert failed for KQL YAML rule {title}: {resp}")
                    continue

                # Otherwise, process as Sigma rule
                title = rule_doc.get('title')
                logsource = rule_doc.get('logsource')
                detection = rule_doc.get('detection')
                if not title or logsource is None or detection is None:
                    # Basic validity filter - not a Sigma rule
                    skipped_count += 1
                    continue

                rule_data = {
                    "repoId": str(repo_id),
                    "title": title,
                    "status": rule_doc.get('status', 'experimental'),
                    "description": rule_doc.get('description'),
                    "author": rule_doc.get('author'),
                    "references": rule_doc.get('references'),
                    "logsource": json.dumps(logsource),
                    "detection": json.dumps(detection),
                    "falsePositives": rule_doc.get('falsepositives'),
                    "level": rule_doc.get('level'),
                    "tags": rule_doc.get('tags'),
                    "rawContent": raw_yaml,
                    "format": "SIGMA",
                }

                resp = self.api_client.upsert_rule(rule_data)
                if resp and resp.get('upsertRule') and resp['upsertRule'].get('rule'):
                    success_count += 1
                else:
                    error_count += 1
                    logger.warning(f"Upsert failed for SIGMA rule {title}: {resp}")
            except Exception as e:
                error_count += 1
                logger.warning(f"Failed to parse or upsert YAML file {fpath}: {e}")

        # Process KQL files
        for fpath in kql_files:
            try:
                with open(fpath, 'r', encoding='utf-8') as fh:
                    raw_content = fh.read()

                # Skip empty files
                if not raw_content.strip():
                    skipped_count += 1
                    continue

                # Parse KQL metadata from comments
                metadata = parse_kql_file(raw_content, fpath)
                
                rule_data = {
                    "repoId": str(repo_id),
                    "title": metadata['title'],
                    "status": metadata['status'],
                    "description": metadata['description'],
                    "author": metadata['author'],
                    "references": metadata['references'] if metadata['references'] else None,
                    "logsource": None,  # KQL doesn't have logsource structure
                    "detection": None,  # KQL query is in rawContent
                    "falsePositives": None,
                    "level": metadata['level'],
                    "tags": metadata['tags'] if metadata['tags'] else None,
                    "rawContent": raw_content,
                    "format": "KQL",
                }

                resp = self.api_client.upsert_rule(rule_data)
                if resp and resp.get('upsertRule') and resp['upsertRule'].get('rule'):
                    success_count += 1
                else:
                    error_count += 1
                    logger.warning(f"Upsert failed for KQL rule {metadata['title']}: {resp}")
            except Exception as e:
                error_count += 1
                logger.warning(f"Failed to parse or upsert KQL file {fpath}: {e}")

        # Process Markdown files (KQL queries in code blocks)
        for fpath in md_files:
            try:
                # Skip common non-rule markdown files
                filename = os.path.basename(fpath).lower()
                if filename in ['readme.md', 'license.md', 'changelog.md', 'contributing.md', 'code_of_conduct.md']:
                    skipped_count += 1
                    continue

                with open(fpath, 'r', encoding='utf-8') as fh:
                    raw_content = fh.read()

                # Skip empty files or very short files
                if not raw_content.strip() or len(raw_content) < 50:
                    skipped_count += 1
                    continue

                # Parse markdown for KQL queries
                metadata, kql_queries = parse_kql_markdown_file(raw_content, fpath)
                
                if not kql_queries:
                    skipped_count += 1
                    continue

                # If multiple queries in one file, combine them or create one rule per query
                # For simplicity, we'll combine all queries into one rule per file
                combined_query = '\n\n// --- Query Separator ---\n\n'.join(kql_queries)
                
                rule_data = {
                    "repoId": str(repo_id),
                    "title": metadata['title'],
                    "status": metadata['status'],
                    "description": metadata['description'],
                    "author": metadata['author'],
                    "references": metadata['references'] if metadata['references'] else None,
                    "logsource": None,
                    "detection": None,
                    "falsePositives": None,
                    "level": metadata['level'],
                    "tags": metadata['tags'] if metadata['tags'] else None,
                    "rawContent": combined_query,
                    "format": "KQL",
                }

                resp = self.api_client.upsert_rule(rule_data)
                if resp and resp.get('upsertRule') and resp['upsertRule'].get('rule'):
                    success_count += 1
                    logger.debug(f"Upserted KQL rule from markdown: {metadata['title']}")
                else:
                    error_count += 1
                    logger.warning(f"Upsert failed for KQL (markdown) rule {metadata['title']}: {resp}")
            except Exception as e:
                error_count += 1
                logger.warning(f"Failed to parse or upsert markdown file {fpath}: {e}")

        logger.info(f"Finished processing repo {repo_name}: {success_count} upserted, {skipped_count} skipped, {error_count} errors")
        try:
            self.api_client.update_repo_last_sync(repo_id)
        except Exception as e:
            logger.warning(f"Failed to update last_sync for repo {repo_id}: {e}")
        return True

    def process_rag_sync(self, payload):
        """Process repository RAG sync request (JSONL/KQL/EQL/SPL/WAZUH -> Qdrant templates)."""
        repo_id = payload.get('repository_id')
        if not repo_id:
            logger.error("RAG sync message missing 'repository_id'. Discarding.")
            return True

        logger.info("Processing RAG sync for repository_id=%s", repo_id)

        repo_data = self.api_client.get_repository_details(repo_id)
        if not repo_data or not repo_data.get('ruleRepository'):
            logger.error("Could not find repo details for RAG sync %s. Discarding.", repo_id)
            return True

        repo = repo_data['ruleRepository']
        repo_url = repo.get('url')
        repo_name = repo.get('name') or f"repo-{repo_id}"
        rag_enabled = bool(repo.get('ragSyncEnabled'))
        rag_dataset_path = (repo.get('ragDatasetPath') or '').strip()
        rag_branch = (repo.get('ragBranch') or 'main').strip() or 'main'
        organization_id = payload.get('organization_id')

        if payload.get('scheduled') and not rag_enabled:
            logger.info("Skipping scheduled RAG sync for repo %s because ragSyncEnabled=false.", repo_id)
            return True

        if not repo_url:
            logger.error("Repository %s has no URL for RAG sync. Discarding.", repo_id)
            try:
                self.api_client.update_repo_rag_sync_status(
                    repo_id,
                    status='FAILED',
                    error_message='Repository URL is not configured.',
                )
            except Exception:
                pass
            return True

        username = repo.get('username')
        token = repo.get('token')
        if username and token and repo_url.startswith('https://'):
            repo_url = repo_url.replace("https://", f"https://{username}:{token}@", 1)

        try:
            self.api_client.update_repo_rag_sync_status(repo_id, status='RUNNING', error_message='')
        except Exception as exc:
            logger.warning("Failed to mark RAG sync RUNNING for repo %s: %s", repo_id, exc)

        clone_path = f"/tmp/rule_repos_rag/{repo_id}"

        try:
            self._sync_repo_checkout(clone_path, repo, repo_url, branch=rag_branch)
            templates, file_statuses = collect_templates_from_repo(
                repo_root=clone_path,
                repo_id=str(repo_id),
                repo_name=repo_name,
                organization_id=str(organization_id) if organization_id else None,
                source_branch=rag_branch,
                dataset_path=rag_dataset_path,
            )

            try:
                self.api_client.update_repo_rag_file_statuses(
                    repo_id,
                    file_statuses,
                    replace_existing=True,
                )
            except Exception as exc:
                logger.warning("Failed to update RAG file statuses for repo %s: %s", repo_id, exc)

            store = QdrantTemplateStore()

            ingested_files = sum(
                1
                for file_status in file_statuses
                if str(file_status.get('ingestion_status') or '').upper() == 'INGESTED'
            )
            failed_files = max(len(file_statuses) - ingested_files, 0)

            summary = {
                'total': len(templates),
                'upserted': 0,
                'deleted': 0,
                'skipped': len(templates),
            }

            if ingested_files > 0:
                summary = store.sync_repository_templates(str(repo_id), templates)
            else:
                logger.warning(
                    "Skipping Qdrant upsert/delete for repo %s because no dataset files were ingested.",
                    repo_id,
                )

            logger.info(
                "RAG sync summary for repo %s: total=%s upserted=%s deleted=%s skipped=%s files=%s",
                repo_id,
                summary.get('total'),
                summary.get('upserted'),
                summary.get('deleted'),
                summary.get('skipped'),
                len(file_statuses),
            )

            final_status = 'SUCCESS'
            final_error = ''

            if len(file_statuses) == 0:
                final_status = 'FAILED'
                pattern_hint = (rag_dataset_path or '**/*.jsonl, **/*.kql, **/*.eql, **/*.spl (including data-wazuh JSONL)').strip()
                final_error = (
                    f"No dataset files matched pattern(s): {pattern_hint} "
                    f"on branch '{rag_branch}'."
                )
            elif ingested_files == 0 or int(summary.get('total', 0)) == 0:
                final_status = 'FAILED'
                failure_messages = []
                for file_status in file_statuses:
                    message = str(file_status.get('error_message') or '').strip()
                    if message and message not in failure_messages:
                        failure_messages.append(message)
                    if len(failure_messages) >= 3:
                        break

                final_error = (
                    f"No templates ingested ({failed_files}/{len(file_statuses)} files failed)."
                )
                if failure_messages:
                    final_error = f"{final_error} Details: {' | '.join(failure_messages)}"
            elif failed_files > 0:
                final_status = 'PARTIAL'
                failure_messages = []
                for file_status in file_statuses:
                    if str(file_status.get('ingestion_status') or '').upper() != 'FAILED':
                        continue
                    message = str(file_status.get('error_message') or '').strip()
                    if message and message not in failure_messages:
                        failure_messages.append(message)
                    if len(failure_messages) >= 3:
                        break

                final_error = (
                    f"Partial template ingestion ({ingested_files}/{len(file_statuses)} files ingested; "
                    f"{failed_files} failed)."
                )
                if failure_messages:
                    final_error = f"{final_error} Details: {' | '.join(failure_messages)}"

            try:
                self.api_client.update_repo_rag_sync_status(
                    repo_id,
                    status=final_status,
                    error_message=final_error,
                    synced_templates=int(summary.get('total', 0)),
                )
            except Exception as exc:
                logger.warning("Failed to mark RAG sync completion status for repo %s: %s", repo_id, exc)
            return True
        except Exception as exc:
            logger.exception("RAG sync failed for repository %s: %s", repo_id, exc)
            try:
                self.api_client.update_repo_rag_sync_status(
                    repo_id,
                    status='FAILED',
                    error_message=str(exc),
                )
            except Exception:
                pass
            if isinstance(exc, TimeoutError):
                return True
            return False


if __name__ == '__main__':
    logger.info("--- Starting HEFAISTOS Rule Connector (SDK v1.0) ---")
    connector = RuleConnector(service_name="RuleConnector")
    connector.start_consuming()
