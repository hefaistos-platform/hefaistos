"""
Helpers for fetching MITRE ATLAS content from GitHub.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
import yaml

DEFAULT_ATLAS_REPO = "https://github.com/mitre-atlas/atlas-data"
DEFAULT_ATLAS_REF = "main"

_GITHUB_API_BASE = "https://api.github.com"
_REQUEST_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "hefaistos-platform-data-sync",
}


def parse_github_repo(source_repo: str) -> tuple[str, str]:
    """Parse a GitHub repository URL and return ``(owner, repo)``."""
    repo_url = (source_repo or "").strip().rstrip("/")
    if not repo_url:
        raise ValueError("source_repo cannot be empty")

    parsed = urlparse(repo_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("source_repo must be an HTTP(S) URL")
    if parsed.netloc.lower() != "github.com":
        raise ValueError("Only github.com repositories are supported")

    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise ValueError("source_repo must include owner and repository name")

    owner = parts[0].strip()
    repo = parts[1].strip()
    if repo.endswith(".git"):
        repo = repo[:-4]

    if not owner or not repo:
        raise ValueError("source_repo must include valid owner/repository")

    return owner, repo


def _github_json(url: str, timeout: int = 20) -> dict:
    response = requests.get(url, headers=_REQUEST_HEADERS, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected JSON payload from GitHub for {url}")
    return data


def fetch_latest_ref_sha(source_repo: str = DEFAULT_ATLAS_REPO, ref: str = DEFAULT_ATLAS_REF) -> str | None:
    """Resolve the latest commit SHA for the given ref."""
    owner, repo = parse_github_repo(source_repo)
    payload = _github_json(f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{ref}", timeout=15)
    sha = str(payload.get("sha") or "").strip()
    return sha or None


_MANIFEST_PATH = "dist/manifest.yaml"
_RELEASE_PATH_RE = re.compile(r"^dist/v\d+/ATLAS-\d{4}\.\d{2}\.ya?ml$")


def latest_path_from_manifest(manifest_text: str) -> tuple[str, str] | None:
    """Return ``(repo_path, release)`` of the newest release listed in ``dist/manifest.yaml``.

    The upstream manifest lists releases newest first; the entry's ``versions[].path`` is
    relative to ``dist/``. ``dist/ATLAS-latest.yaml`` itself is a git symlink, so raw
    downloads of it only return the target path text, not YAML content.
    """
    try:
        data = yaml.safe_load(manifest_text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, list):
        return None
    for entry in data:
        if not isinstance(entry, dict):
            continue
        release = str(entry.get("release") or "").strip()
        for version in entry.get("versions") or []:
            rel_path = str((version or {}).get("path") or "").strip().lstrip("/")
            if rel_path.lower().endswith((".yaml", ".yml")):
                return f"dist/{rel_path}", release
    return None


def list_remote_atlas_paths(
    source_repo: str = DEFAULT_ATLAS_REPO,
    ref: str = DEFAULT_ATLAS_REF,
) -> list[str]:
    """Return the single YAML file holding the current ATLAS release.

    Only the newest release is imported. The upstream repo also holds CI workflows, the
    deprecated ``dist/ATLAS.yaml`` and dozens of historical releases; importing those would
    resurrect retired tactics/techniques as if they were current.
    """
    try:
        manifest = fetch_remote_atlas_text(source_repo, ref, _MANIFEST_PATH)
    except requests.RequestException:
        manifest = ""
    latest = latest_path_from_manifest(manifest) if manifest else None
    if latest:
        return [latest[0]]

    # Fallback: newest dist/vN/ATLAS-YYYY.MM.yaml in the git tree.
    owner, repo = parse_github_repo(source_repo)
    payload = _github_json(
        f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{ref}?recursive=1",
        timeout=20,
    )
    rows = payload.get("tree") or []
    candidates = [
        str(row.get("path") or "")
        for row in rows
        if isinstance(row, dict) and str(row.get("type") or "").lower() == "blob"
    ]
    candidates = sorted(path for path in candidates if _RELEASE_PATH_RE.match(path))
    return candidates[-1:]


def build_remote_raw_url(source_repo: str, ref: str, path: str) -> str:
    owner, repo = parse_github_repo(source_repo)
    norm_ref = (ref or "").strip() or DEFAULT_ATLAS_REF
    norm_path = (path or "").strip().lstrip("/")
    if not norm_path:
        raise ValueError("path cannot be empty")
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{norm_ref}/{norm_path}"


def fetch_remote_atlas_text(source_repo: str, ref: str, path: str) -> str:
    raw_url = build_remote_raw_url(source_repo, ref, path)
    response = requests.get(raw_url, headers=_REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def normalize_git_ref(value: str | None, default: str = DEFAULT_ATLAS_REF) -> str:
    text = (value or "").strip()
    if not text:
        return default
    return re.sub(r"^refs/", "", text)
