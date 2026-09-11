"""
Helpers for fetching detection-chokepoints content from GitHub.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import requests

DEFAULT_CHOKEPOINTS_REPO = "https://github.com/iimp0ster/detection-chokepoints"
DEFAULT_CHOKEPOINTS_REF = "main"

_GITHUB_API_BASE = "https://api.github.com"
_REQUEST_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "hefaistos-platform-data-sync",
}


def parse_github_repo(source_repo: str) -> tuple[str, str]:
    """
    Parse a GitHub repository URL and return ``(owner, repo)``.
    """
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


def fetch_latest_ref_sha(source_repo: str = DEFAULT_CHOKEPOINTS_REPO, ref: str = DEFAULT_CHOKEPOINTS_REF) -> str | None:
    """
    Resolve the latest commit SHA for the given ref.
    """
    owner, repo = parse_github_repo(source_repo)
    payload = _github_json(f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{ref}", timeout=15)
    sha = str(payload.get("sha") or "").strip()
    return sha or None


def list_remote_chokepoint_paths(
    source_repo: str = DEFAULT_CHOKEPOINTS_REPO,
    ref: str = DEFAULT_CHOKEPOINTS_REF,
) -> list[str]:
    """
    Return all chokepoint YAML files found under ``chokepoints/`` for a ref.
    """
    owner, repo = parse_github_repo(source_repo)
    payload = _github_json(
        f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{ref}?recursive=1",
        timeout=20,
    )
    rows = payload.get("tree") or []
    if not isinstance(rows, list):
        return []

    result: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("type") or "").lower() != "blob":
            continue
        path = str(row.get("path") or "").strip()
        lower = path.lower()
        if not path.startswith("chokepoints/"):
            continue
        if not (lower.endswith(".yml") or lower.endswith(".yaml")):
            continue
        result.append(path)

    result.sort()
    return result


def build_remote_raw_url(
    source_repo: str,
    ref: str,
    path: str,
) -> str:
    owner, repo = parse_github_repo(source_repo)
    norm_ref = (ref or "").strip() or DEFAULT_CHOKEPOINTS_REF
    norm_path = (path or "").strip().lstrip("/")
    if not norm_path:
        raise ValueError("path cannot be empty")
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{norm_ref}/{norm_path}"


def fetch_remote_chokepoint_text(
    source_repo: str,
    ref: str,
    path: str,
) -> str:
    raw_url = build_remote_raw_url(source_repo, ref, path)
    response = requests.get(raw_url, headers=_REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


def normalize_git_ref(value: str | None, default: str = DEFAULT_CHOKEPOINTS_REF) -> str:
    text = (value or "").strip()
    if not text:
        return default
    # Keep short refs and commit SHAs. Remove accidental leading "refs/".
    return re.sub(r"^refs/", "", text)
