import base64
import posixpath
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests


class RepoProvider:
    GITHUB = 'GITHUB'
    GITLAB = 'GITLAB'
    GITEA = 'GITEA'
    AUTO = 'AUTO'


@dataclass
class RepoRef:
    provider: str
    scheme: str
    host: str
    namespace: str
    repo: str

    @property
    def full_name(self) -> str:
        return f'{self.namespace}/{self.repo}' if self.namespace else self.repo

    @property
    def web_base_url(self) -> str:
        return f'{self.scheme}://{self.host}'


_HTTPS_RE = re.compile(r'^https?://([^/]+)/(.+?)(?:\.git)?/?$')
_SSH_RE = re.compile(r'^git@([^:]+):(.+?)(?:\.git)?$')


def parse_repo_url(repo_url: str) -> RepoRef | None:
    if not repo_url:
        return None
    raw = repo_url.strip()
    scheme = 'https'
    host = ''
    path = ''

    m = _HTTPS_RE.match(raw)
    if m:
        host = m.group(1).lower()
        path = m.group(2).strip('/')
        scheme = 'https'
    else:
        m = _SSH_RE.match(raw)
        if not m:
            return None
        host = m.group(1).lower()
        path = m.group(2).strip('/')
        scheme = 'https'

    parts = [p for p in path.split('/') if p]
    if len(parts) < 2:
        return None

    repo = parts[-1]
    namespace = '/'.join(parts[:-1])

    if host == 'github.com':
        provider = RepoProvider.GITHUB
    elif 'gitlab' in host:
        provider = RepoProvider.GITLAB
    elif 'gitea' in host:
        provider = RepoProvider.GITEA
    else:
        # Heuristic: GitLab commonly uses nested groups, default to GitLab there.
        provider = RepoProvider.GITLAB if len(parts) > 2 else RepoProvider.GITEA

    return RepoRef(
        provider=provider,
        scheme=scheme,
        host=host,
        namespace=namespace,
        repo=repo,
    )


def infer_provider(repo_url: str | None, configured_provider: str | None = None) -> str:
    normalized = (configured_provider or RepoProvider.AUTO).upper()
    if normalized in (RepoProvider.GITHUB, RepoProvider.GITLAB, RepoProvider.GITEA):
        return normalized
    parsed = parse_repo_url(repo_url or '')
    return parsed.provider if parsed else RepoProvider.GITHUB


class RepoClient:
    def __init__(
        self,
        repo_url: str,
        token: str,
        provider: str = RepoProvider.AUTO,
        api_base_url: str | None = None,
        verify_ssl: bool = True,
    ):
        if not token:
            raise ValueError('Repository token is required')
        self.token = token
        parsed = parse_repo_url(repo_url)
        if not parsed:
            raise ValueError(f'Cannot parse repository URL: {repo_url}')
        self.ref = parsed
        self.provider = infer_provider(repo_url, provider)
        self.api_base_url = (api_base_url or '').rstrip('/') or self._default_api_base()
        self.verify_ssl = bool(verify_ssl)

    def _get(self, url: str, **kwargs):
        kwargs.setdefault('verify', self.verify_ssl)
        return requests.get(url, **kwargs)

    def _post(self, url: str, **kwargs):
        kwargs.setdefault('verify', self.verify_ssl)
        return requests.post(url, **kwargs)

    def _patch(self, url: str, **kwargs):
        kwargs.setdefault('verify', self.verify_ssl)
        return requests.patch(url, **kwargs)

    def _put(self, url: str, **kwargs):
        kwargs.setdefault('verify', self.verify_ssl)
        return requests.put(url, **kwargs)

    def _default_api_base(self) -> str:
        if self.provider == RepoProvider.GITHUB:
            return 'https://api.github.com'
        if self.provider == RepoProvider.GITLAB:
            return f'{self.ref.web_base_url}/api/v4'
        if self.provider == RepoProvider.GITEA:
            return f'{self.ref.web_base_url}/api/v1'
        raise ValueError(f'Unsupported provider: {self.provider}')

    @property
    def owner(self) -> str:
        if '/' in self.ref.namespace:
            return self.ref.namespace.split('/', 1)[0]
        return self.ref.namespace

    @property
    def repo(self) -> str:
        return self.ref.repo

    @property
    def full_name(self) -> str:
        return self.ref.full_name

    def _headers(self) -> dict[str, str]:
        if self.provider == RepoProvider.GITHUB:
            return {
                'Authorization': f'token {self.token}',
                'Accept': 'application/vnd.github+json',
                'X-GitHub-Api-Version': '2022-11-28',
            }
        if self.provider == RepoProvider.GITLAB:
            return {
                'PRIVATE-TOKEN': self.token,
                'Accept': 'application/json',
            }
        if self.provider == RepoProvider.GITEA:
            return {
                'Authorization': f'token {self.token}',
                'Accept': 'application/json',
            }
        raise ValueError(f'Unsupported provider: {self.provider}')

    def _project_path(self) -> str:
        return quote(self.full_name, safe='')

    def resolve_commit_sha(self, branch: str, commit_sha: str | None = None) -> str:
        if commit_sha:
            return commit_sha

        headers = self._headers()
        if self.provider == RepoProvider.GITHUB:
            url = f'{self.api_base_url}/repos/{self.full_name}/git/ref/heads/{branch}'
            resp = self._get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                raise ValueError(f'Cannot resolve HEAD of branch {branch}: {resp.text}')
            sha = resp.json().get('object', {}).get('sha')
        elif self.provider == RepoProvider.GITLAB:
            url = f'{self.api_base_url}/projects/{self._project_path()}/repository/branches/{quote(branch, safe="")}'
            resp = self._get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                raise ValueError(f'Cannot resolve HEAD of branch {branch}: {resp.text}')
            sha = resp.json().get('commit', {}).get('id')
        else:
            url = f'{self.api_base_url}/repos/{self.full_name}/branches/{quote(branch, safe="")}'
            resp = self._get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                raise ValueError(f'Cannot resolve HEAD of branch {branch}: {resp.text}')
            sha = resp.json().get('commit', {}).get('id')

        if not sha:
            raise ValueError(f'Cannot resolve commit SHA for branch {branch}')
        return sha

    def fetch_tree(self, sha: str) -> list[dict[str, Any]]:
        headers = self._headers()
        if self.provider == RepoProvider.GITHUB:
            url = f'{self.api_base_url}/repos/{self.full_name}/git/trees/{sha}?recursive=1'
            resp = self._get(url, headers=headers, timeout=60)
            if resp.status_code != 200:
                raise ValueError(f'Cannot fetch git tree for SHA {sha}: {resp.text}')
            return resp.json().get('tree', [])

        if self.provider == RepoProvider.GITLAB:
            page = 1
            items: list[dict[str, Any]] = []
            while True:
                url = f'{self.api_base_url}/projects/{self._project_path()}/repository/tree'
                resp = self._get(
                    url,
                    headers=headers,
                    params={'ref': sha, 'recursive': True, 'per_page': 100, 'page': page},
                    timeout=60,
                )
                if resp.status_code != 200:
                    raise ValueError(f'Cannot fetch git tree for SHA {sha}: {resp.text}')
                batch = resp.json() if isinstance(resp.json(), list) else []
                for item in batch:
                    items.append({
                        'path': item.get('path'),
                        'type': 'tree' if item.get('type') == 'tree' else 'blob',
                        'sha': item.get('id') or item.get('sha'),
                    })
                if len(batch) < 100:
                    break
                page += 1
            return items

        url = f'{self.api_base_url}/repos/{self.full_name}/git/trees/{sha}'
        resp = self._get(url, headers=headers, params={'recursive': 1}, timeout=60)
        if resp.status_code != 200:
            raise ValueError(f'Cannot fetch git tree for SHA {sha}: {resp.text}')
        return resp.json().get('tree', [])

    def get_file_content(self, path: str, ref: str) -> str | None:
        headers = self._headers()
        if self.provider == RepoProvider.GITHUB:
            url = f'{self.api_base_url}/repos/{self.full_name}/contents/{path}'
            resp = self._get(url, headers=headers, params={'ref': ref}, timeout=30)
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                raise ValueError(f'Cannot fetch {path} at {ref}: {resp.text}')
            content = resp.json().get('content', '')
            return base64.b64decode(content).decode('utf-8')

        if self.provider == RepoProvider.GITLAB:
            enc_path = quote(path, safe='')
            url = f'{self.api_base_url}/projects/{self._project_path()}/repository/files/{enc_path}'
            resp = self._get(url, headers=headers, params={'ref': ref}, timeout=30)
            if resp.status_code == 404:
                return None
            if resp.status_code != 200:
                raise ValueError(f'Cannot fetch {path} at {ref}: {resp.text}')
            content = resp.json().get('content', '')
            return base64.b64decode(content).decode('utf-8')

        url = f'{self.api_base_url}/repos/{self.full_name}/contents/{path}'
        resp = self._get(url, headers=headers, params={'ref': ref}, timeout=30)
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise ValueError(f'Cannot fetch {path} at {ref}: {resp.text}')
        content = resp.json().get('content', '')
        return base64.b64decode(content).decode('utf-8')

    def commit_files(self, branch: str, files: dict[str, str], commit_message: str) -> str:
        if self.provider == RepoProvider.GITHUB:
            return self._commit_files_github(branch, files, commit_message)
        if self.provider == RepoProvider.GITLAB:
            return self._commit_files_gitlab(branch, files, commit_message)
        if self.provider == RepoProvider.GITEA:
            return self._commit_files_gitea(branch, files, commit_message)
        raise ValueError(f'Unsupported provider: {self.provider}')

    def _commit_files_github(self, branch: str, files: dict[str, str], commit_message: str) -> str:
        headers = self._headers()
        read_ref_url = f'{self.api_base_url}/repos/{self.full_name}/git/ref/heads/{branch}'
        update_ref_url = f'{self.api_base_url}/repos/{self.full_name}/git/refs/heads/{branch}'

        ref_resp = self._get(read_ref_url, headers=headers, timeout=30)
        if ref_resp.status_code != 200:
            raise ValueError(f'Unable to access branch {branch}: {ref_resp.text}')
        base_commit_sha = ref_resp.json().get('object', {}).get('sha')
        if not base_commit_sha:
            raise ValueError(f'Unable to resolve HEAD SHA for branch {branch}')

        commit_url = f'{self.api_base_url}/repos/{self.full_name}/git/commits/{base_commit_sha}'
        commit_resp = self._get(commit_url, headers=headers, timeout=30)
        if commit_resp.status_code != 200:
            raise ValueError(f'Unable to read base commit: {commit_resp.text}')
        base_tree_sha = commit_resp.json().get('tree', {}).get('sha')
        if not base_tree_sha:
            raise ValueError('Unable to resolve base tree SHA for repository branch')

        tree_entries = []
        for path, content in files.items():
            blob_resp = self._post(
                f'{self.api_base_url}/repos/{self.full_name}/git/blobs',
                headers=headers,
                json={'content': content, 'encoding': 'utf-8'},
                timeout=30,
            )
            if blob_resp.status_code not in (200, 201):
                raise ValueError(f'Unable to create blob for {path}: {blob_resp.text}')
            tree_entries.append({
                'path': path,
                'mode': '100644',
                'type': 'blob',
                'sha': blob_resp.json().get('sha'),
            })

        tree_resp = self._post(
            f'{self.api_base_url}/repos/{self.full_name}/git/trees',
            headers=headers,
            json={'base_tree': base_tree_sha, 'tree': tree_entries},
            timeout=30,
        )
        if tree_resp.status_code not in (200, 201):
            raise ValueError(f'Unable to create git tree: {tree_resp.text}')

        new_tree_sha = tree_resp.json().get('sha')
        new_commit_resp = self._post(
            f'{self.api_base_url}/repos/{self.full_name}/git/commits',
            headers=headers,
            json={'message': commit_message, 'tree': new_tree_sha, 'parents': [base_commit_sha]},
            timeout=30,
        )
        if new_commit_resp.status_code not in (200, 201):
            raise ValueError(f'Unable to create commit: {new_commit_resp.text}')
        new_commit_sha = new_commit_resp.json().get('sha')

        update_ref_resp = self._patch(
            update_ref_url,
            headers=headers,
            json={'sha': new_commit_sha, 'force': False},
            timeout=30,
        )
        if update_ref_resp.status_code != 200:
            raise ValueError(f'Unable to update branch ref: {update_ref_resp.text}')
        return new_commit_sha

    def _commit_files_gitlab(self, branch: str, files: dict[str, str], commit_message: str) -> str:
        headers = self._headers()
        actions = []
        for path, content in files.items():
            exists = self.get_file_content(path, branch) is not None
            actions.append({
                'action': 'update' if exists else 'create',
                'file_path': path,
                'content': content,
                'encoding': 'text',
            })

        url = f'{self.api_base_url}/projects/{self._project_path()}/repository/commits'
        resp = self._post(
            url,
            headers=headers,
            json={'branch': branch, 'commit_message': commit_message, 'actions': actions},
            timeout=60,
        )
        if resp.status_code not in (200, 201):
            raise ValueError(f'Unable to create commit: {resp.text}')
        sha = resp.json().get('id')
        if not sha:
            raise ValueError('Unable to resolve commit SHA from GitLab response')
        return sha

    def _commit_files_gitea(self, branch: str, files: dict[str, str], commit_message: str) -> str:
        headers = self._headers()
        last_sha = ''
        for path, content in files.items():
            existing_sha = None
            get_url = f'{self.api_base_url}/repos/{self.full_name}/contents/{path}'
            get_resp = self._get(get_url, headers=headers, params={'ref': branch}, timeout=30)
            if get_resp.status_code == 200:
                existing_sha = get_resp.json().get('sha')
            elif get_resp.status_code != 404:
                raise ValueError(f'Unable to inspect file {path}: {get_resp.text}')

            payload = {
                'message': commit_message,
                'content': base64.b64encode(content.encode('utf-8')).decode('ascii'),
                'branch': branch,
            }
            if existing_sha:
                payload['sha'] = existing_sha

            put_resp = self._put(get_url, headers=headers, json=payload, timeout=30)
            if put_resp.status_code not in (200, 201):
                raise ValueError(f'Unable to upsert file {path}: {put_resp.text}')

            last_sha = (
                put_resp.json().get('commit', {}).get('sha')
                or put_resp.json().get('content', {}).get('sha')
                or last_sha
            )

        if not last_sha:
            last_sha = self.resolve_commit_sha(branch)
        return last_sha

    def file_web_url(self, branch: str, path: str | None = None) -> str:
        if self.provider == RepoProvider.GITHUB:
            if path:
                return f'{self.ref.web_base_url}/{self.full_name}/blob/{branch}/{path}'
            return f'{self.ref.web_base_url}/{self.full_name}/tree/{branch}'
        if self.provider == RepoProvider.GITLAB:
            if path:
                return f'{self.ref.web_base_url}/{self.full_name}/-/blob/{branch}/{path}'
            return f'{self.ref.web_base_url}/{self.full_name}/-/tree/{branch}'
        if path:
            return f'{self.ref.web_base_url}/{self.full_name}/src/branch/{branch}/{path}'
        return f'{self.ref.web_base_url}/{self.full_name}/src/branch/{branch}'


def join_repo_path(*parts: str) -> str:
    clean_parts = [part.strip('/') for part in parts if part and str(part).strip('/')]
    return posixpath.join(*clean_parts) if clean_parts else ''
