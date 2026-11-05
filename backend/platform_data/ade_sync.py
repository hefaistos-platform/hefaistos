"""
Fetching and parsing helpers for the Adversarial Detection Engineering (ADE) framework.

Upstream: https://github.com/Adversarial-Detection-Engineering/Adversarial-Detection-Engineering-Framework

Upstream content comes in three shapes, and this module normalizes all of them into
plain dicts so the import command stays small and the parsers are unit-testable offline:

* Taxonomy Markdown (``docs/taxonomy/ade*.md``): category and subcategory definitions.
  There is no machine-readable list upstream, so subcategories are read from
  ``### ADEn-nn: Title`` headings inside the ``## Subcategories`` section.
* Bug Likelihood Test (``docs/guides/bug-likelihood-test.md``): ``- [ ]`` checklist items.
* YAML records: ``dle/<year>/DLE-*.yaml`` (rule-specific bypasses) and
  ``in-the-wild/ITW-*.yaml`` (threat-actor bypasses).

Parsers never raise on odd layouts. They return what they found and let the caller
decide, because the upstream layout can change without notice.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import requests

from .chokepoints_sync import (  # reuse the same GitHub helpers and URL validation
    _github_json,
    build_remote_raw_url,
    normalize_git_ref,
    parse_github_repo,
)

try:
    import yaml
except Exception:  # pragma: no cover - dependency availability is validated at runtime
    yaml = None

DEFAULT_ADE_REPO = "https://github.com/Adversarial-Detection-Engineering/Adversarial-Detection-Engineering-Framework"
DEFAULT_ADE_REF = "main"

_GITHUB_API_BASE = "https://api.github.com"
_REQUEST_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "hefaistos-platform-data-sync",
}

KIND_CATEGORY = "CATEGORY"
KIND_SUBCATEGORY = "SUBCATEGORY"
KIND_LIKELIHOOD_CHECK = "LIKELIHOOD_CHECK"
KIND_DLE = "DLE"
KIND_ITW = "ITW"

TAXONOMY_DIR = "docs/taxonomy/"
LIKELIHOOD_PATH = "docs/guides/bug-likelihood-test.md"

# Upstream mixes ASCII hyphens with U+2011 (non-breaking hyphen) and en/em dashes in IDs.
_DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"), "-")

ADE_ID_RE = re.compile(r"\bADE([1-9])-(\d{2})\b")
CATEGORY_HEADING_RE = re.compile(r"^#\s+ADE([1-9])\s*[-:]\s*(.+?)\s*$", re.MULTILINE)
SUBCATEGORY_HEADING_RE = re.compile(r"^###\s+(ADE[1-9]-\d{2})\s*:\s*(.+?)\s*$")
CHECKBOX_RE = re.compile(r"^\s*-\s*\[[ xX]\]\s+(.*\S)\s*$")


def normalize_dashes(text: str) -> str:
    return (text or "").translate(_DASHES)


# ---------------------------------------------------------------------------
# Remote access
# ---------------------------------------------------------------------------

def fetch_latest_ade_sha(source_repo: str = DEFAULT_ADE_REPO, ref: str = DEFAULT_ADE_REF) -> str | None:
    owner, repo = parse_github_repo(source_repo)
    payload = _github_json(f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{normalize_git_ref(ref, DEFAULT_ADE_REF)}", timeout=15)
    return str(payload.get("sha") or "").strip() or None


def list_remote_ade_paths(source_repo: str = DEFAULT_ADE_REPO, ref: str = DEFAULT_ADE_REF) -> list[str]:
    """Return every upstream file path the importer cares about, sorted."""
    owner, repo = parse_github_repo(source_repo)
    payload = _github_json(
        f"{_GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{normalize_git_ref(ref, DEFAULT_ADE_REF)}?recursive=1",
        timeout=20,
    )
    return select_ade_paths(
        str(row.get("path") or "")
        for row in (payload.get("tree") or [])
        if isinstance(row, dict) and str(row.get("type") or "").lower() == "blob"
    )


def select_ade_paths(paths) -> list[str]:
    """Filter a list of repo paths down to the files the importer reads."""
    selected: list[str] = []
    for path in paths:
        lower = path.lower()
        if path.startswith(TAXONOMY_DIR) and lower.endswith(".md") and not lower.endswith("overview.md"):
            selected.append(path)
        elif path == LIKELIHOOD_PATH:
            selected.append(path)
        elif path.startswith("dle/") and lower.endswith((".yaml", ".yml")):
            selected.append(path)
        elif path.startswith("in-the-wild/") and lower.endswith((".yaml", ".yml")):
            selected.append(path)
    return sorted(set(selected))


def fetch_remote_ade_text(source_repo: str, ref: str, path: str) -> str:
    response = requests.get(build_remote_raw_url(source_repo, ref, path), headers=_REQUEST_HEADERS, timeout=30)
    response.raise_for_status()
    return response.text


# ---------------------------------------------------------------------------
# Markdown parsers
# ---------------------------------------------------------------------------

def _section_after(lines: list[str], start: int, stop_prefix: str = "## ") -> list[str]:
    """Return lines from ``start`` until the next heading of the same or higher level."""
    out: list[str] = []
    for line in lines[start:]:
        if line.startswith(stop_prefix) and not line.startswith("###"):
            break
        out.append(line)
    return out


def _definition_from_block(block: list[str]) -> str:
    """Pull the text after ``**Definition:**`` up to the next blank line."""
    for idx, line in enumerate(block):
        match = re.match(r"^\*\*Definition:\*\*\s*(.*)$", line.strip())
        if not match:
            continue
        parts = [match.group(1).strip()]
        for follow in block[idx + 1:]:
            if not follow.strip():
                break
            if follow.strip().startswith(("**", "-", "#")):
                break
            parts.append(follow.strip())
        return " ".join(p for p in parts if p)
    return ""


def parse_taxonomy_markdown(text: str, path: str = "") -> dict[str, Any]:
    """
    Parse one ``docs/taxonomy/adeN-*.md`` file.

    Returns ``{"category": {...} | None, "subcategories": [...], "warnings": [...]}``.
    Only headings that carry a colon and sit inside ``## Subcategories`` count, which excludes
    the ``### ADE4-01 Patterns`` headings further down the same files.
    """
    text = normalize_dashes(text)
    lines = text.splitlines()
    warnings: list[str] = []

    category = None
    heading = CATEGORY_HEADING_RE.search(text)
    if heading:
        number, title = heading.group(1), heading.group(2).strip()
        intro: list[str] = []
        for line in lines[1:]:
            if line.startswith("## "):
                break
            intro.append(line)
        category = {
            "ade_id": f"ADE{number}",
            "title": title,
            "definition": " ".join(p.strip() for p in "\n".join(intro).split("\n\n")[:1]).strip(),
            "source_path": path,
        }
    else:
        warnings.append(f"{path or 'taxonomy file'}: no '# ADEn - Title' heading found")

    start = next((i for i, line in enumerate(lines) if line.strip().lower() == "## subcategories"), None)
    subcategories: list[dict[str, Any]] = []
    if start is None:
        warnings.append(f"{path or 'taxonomy file'}: no '## Subcategories' section found")
    else:
        section = _section_after(lines, start + 1)
        current: dict[str, Any] | None = None
        buffer: list[str] = []

        def flush():
            if current is not None:
                current["definition"] = _definition_from_block(buffer)
                subcategories.append(current)

        for line in section:
            match = SUBCATEGORY_HEADING_RE.match(line)
            if match:
                flush()
                current = {
                    "ade_id": match.group(1),
                    "title": match.group(2).strip(),
                    "source_path": path,
                }
                buffer = []
            elif current is not None:
                buffer.append(line)
        flush()

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in subcategories:
        if item["ade_id"] in seen:
            warnings.append(f"{path or 'taxonomy file'}: duplicate subcategory {item['ade_id']} ignored")
            continue
        seen.add(item["ade_id"])
        if not item.get("definition"):
            warnings.append(f"{item['ade_id']}: no '**Definition:**' paragraph found")
        unique.append(item)

    return {"category": category, "subcategories": unique, "warnings": warnings}


def parse_likelihood_test(text: str, path: str = LIKELIHOOD_PATH) -> dict[str, Any]:
    """
    Parse the Bug Likelihood Test checklist.

    Each ``- [ ] question`` is one check. ADE IDs mentioned in the indented lines that follow
    (until the next checkbox) are recorded as ``related_ade``.
    """
    text = normalize_dashes(text)
    checks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        match = CHECKBOX_RE.match(line)
        if match:
            if current:
                checks.append(current)
            current = {"question": match.group(1).strip(), "related_ade": [], "notes": []}
            continue
        if current is not None and line.strip():
            if line.startswith("#"):
                checks.append(current)
                current = None
                continue
            current["notes"].append(line.strip())
            for found in ADE_ID_RE.finditer(line):
                ade_id = f"ADE{found.group(1)}-{found.group(2)}"
                if ade_id not in current["related_ade"]:
                    current["related_ade"].append(ade_id)
    if current:
        checks.append(current)

    for index, item in enumerate(checks, start=1):
        item["position"] = index
        item["source_path"] = path
        item["notes"] = " ".join(item["notes"])
    warnings = [] if checks else [f"{path}: no '- [ ]' checklist items found"]
    return {"checks": checks, "warnings": warnings}


# ---------------------------------------------------------------------------
# YAML records (DLE and ITW)
# ---------------------------------------------------------------------------

def _json_safe(value: Any) -> Any:
    """YAML can yield dates and other non-JSON types; coerce them for JSONField storage."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def parse_record_yaml(text: str, path: str = "") -> dict[str, Any]:
    """
    Parse one DLE or ITW YAML file.

    Returns ``{"record": {...} | None, "warnings": [...]}``. ``record`` carries the common
    fields used for display and diffing plus the full parsed document under ``content``.
    """
    if yaml is None:
        return {"record": None, "warnings": [f"{path}: PyYAML is not available"]}
    try:
        data = yaml.safe_load(text)
    except Exception as exc:
        return {"record": None, "warnings": [f"{path}: invalid YAML ({exc})"]}
    if not isinstance(data, dict):
        return {"record": None, "warnings": [f"{path}: top-level YAML is not a mapping"]}

    record_id = str(data.get("id") or "").strip()
    warnings: list[str] = []
    if not record_id:
        return {"record": None, "warnings": [f"{path}: missing 'id'"]}

    if record_id.upper().startswith("DLE-"):
        kind = KIND_DLE
        title = str((data.get("affected_detection_logic") or {}).get("name") or record_id) \
            if isinstance(data.get("affected_detection_logic"), dict) else record_id
        definition = str(data.get("bypass_description") or "").strip()
    elif record_id.upper().startswith("ITW-"):
        kind = KIND_ITW
        title = str(data.get("title") or record_id)
        definition = str(data.get("technique_description") or "").strip()
    else:
        return {"record": None, "warnings": [f"{path}: unrecognized record id '{record_id}'"]}

    related = [
        f"ADE{m.group(1)}-{m.group(2)}"
        for m in ADE_ID_RE.finditer(normalize_dashes(" ".join(map(str, data.get("related_ade") or []))))
    ]
    if not related:
        warnings.append(f"{record_id}: no related_ade IDs")

    attack = data.get("mitre_attack") or []
    return {
        "record": {
            "kind": kind,
            "ade_id": record_id,
            "title": title.strip(),
            "definition": definition,
            "related_ade": sorted(set(related)),
            "mitre_attack": [str(x) for x in attack] if isinstance(attack, list) else [str(attack)],
            "logsource": _json_safe(data.get("logsource") or {}),
            "schema_version": str(data.get("schema_version") or ""),
            "source_path": path,
            "content": _json_safe(data),
        },
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Normalization into entry rows
# ---------------------------------------------------------------------------

KNOWN_SCHEMA_VERSIONS = {"1.0"}


def _hash_entry(row: dict[str, Any]) -> str:
    payload = {k: row.get(k) for k in ("title", "definition", "related_ade", "mitre_attack", "logsource", "content")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def build_entries(file_rows: list[tuple[str, str]]) -> dict[str, Any]:
    """
    Turn ``[(path, text), ...]`` into normalized entry rows.

    Returns ``{"entries": [...], "warnings": [...], "counts": {kind: n}}``. Rows are plain dicts
    matching ``AdeEntry`` fields. Cross-reference problems (a record pointing at an ADE ID that
    has no subcategory, an unknown YAML ``schema_version``) become warnings, never errors, so a
    layout change upstream stages a visible-but-reviewable snapshot instead of silently vanishing.
    """
    entries: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_keys: set[str] = set()

    def add(row: dict[str, Any]) -> None:
        key = row["entry_key"]
        if key in seen_keys:
            warnings.append(f"Duplicate entry key {key} ({row.get('source_path')}) ignored")
            return
        seen_keys.add(key)
        row["source_hash"] = _hash_entry(row)
        entries.append(row)

    for path, text in sorted(file_rows):
        if path.startswith(TAXONOMY_DIR) and path.lower().endswith(".md"):
            parsed = parse_taxonomy_markdown(text, path)
            warnings.extend(parsed["warnings"])
            category = parsed["category"]
            if category:
                add({
                    "entry_key": f"{KIND_CATEGORY}:{category['ade_id']}", "kind": KIND_CATEGORY,
                    "ade_id": category["ade_id"], "parent_ade_id": "", "title": category["title"],
                    "definition": category["definition"], "related_ade": [], "mitre_attack": [],
                    "logsource": {}, "schema_version": "", "source_path": path, "content": {},
                })
            for sub in parsed["subcategories"]:
                add({
                    "entry_key": f"{KIND_SUBCATEGORY}:{sub['ade_id']}", "kind": KIND_SUBCATEGORY,
                    "ade_id": sub["ade_id"], "parent_ade_id": sub["ade_id"].split("-")[0],
                    "title": sub["title"], "definition": sub["definition"], "related_ade": [],
                    "mitre_attack": [], "logsource": {}, "schema_version": "", "source_path": path,
                    "content": {},
                })
        elif path == LIKELIHOOD_PATH:
            parsed = parse_likelihood_test(text, path)
            warnings.extend(parsed["warnings"])
            for check in parsed["checks"]:
                add({
                    "entry_key": f"{KIND_LIKELIHOOD_CHECK}:{check['position']:02d}",
                    "kind": KIND_LIKELIHOOD_CHECK, "ade_id": "", "parent_ade_id": "",
                    "title": check["question"][:512], "definition": check["question"],
                    "related_ade": check["related_ade"], "mitre_attack": [], "logsource": {},
                    "schema_version": "", "source_path": path,
                    "content": {"position": check["position"], "notes": check["notes"]},
                })
        elif path.lower().endswith((".yaml", ".yml")):
            parsed = parse_record_yaml(text, path)
            warnings.extend(parsed["warnings"])
            record = parsed["record"]
            if record:
                add({
                    "entry_key": f"{record['kind']}:{record['ade_id']}", "kind": record["kind"],
                    "ade_id": record["ade_id"], "parent_ade_id": "", "title": record["title"],
                    "definition": record["definition"], "related_ade": record["related_ade"],
                    "mitre_attack": record["mitre_attack"], "logsource": record["logsource"],
                    "schema_version": record["schema_version"], "source_path": path,
                    "content": record["content"],
                })

    known_ids = {e["ade_id"] for e in entries if e["kind"] == KIND_SUBCATEGORY}
    known_categories = {e["ade_id"] for e in entries if e["kind"] == KIND_CATEGORY}
    for entry in entries:
        if entry["kind"] == KIND_SUBCATEGORY and entry["parent_ade_id"] not in known_categories:
            warnings.append(f"{entry['ade_id']}: parent category {entry['parent_ade_id']} was not imported")
        if entry["kind"] in (KIND_DLE, KIND_ITW, KIND_LIKELIHOOD_CHECK):
            for ref in entry["related_ade"]:
                if ref not in known_ids:
                    warnings.append(f"{entry['ade_id'] or entry['entry_key']}: references unknown {ref}")
        if entry["kind"] in (KIND_DLE, KIND_ITW) and entry["schema_version"] not in KNOWN_SCHEMA_VERSIONS:
            warnings.append(
                f"{entry['ade_id']}: unrecognized schema_version '{entry['schema_version']}' "
                f"(known: {', '.join(sorted(KNOWN_SCHEMA_VERSIONS))})"
            )

    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
    return {"entries": entries, "warnings": warnings, "counts": counts}
