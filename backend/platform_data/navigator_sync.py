import json
import os
import re
import tempfile
from pathlib import Path
from typing import Callable

import requests


NAVIGATOR_DATA_ROOT = Path("/navigator-data")
ATTACK_STIX_BASE_URL = "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master"

# Version the embedded Navigator falls back to when /navigator-data has not been
# synced yet. MUST stay in sync with the committed static fallback index at
# frontend/public/navigator/data/index.json. When no local bundles exist, nginx
# serves that file, so the coverage layer must declare this exact version or the
# Navigator rejects the layer ("invalid domain") and renders a blank matrix.
FALLBACK_NAVIGATOR_ATTACK_VERSION = "19.1"

DOMAIN_FILENAMES = {
    "enterprise-attack": "enterprise-attack",
    "ics-attack": "ics-attack",
    "mobile-attack": "mobile-attack",
}

# Navigator coloring is gated per-feature: a cell is painted only when the
# matching flag is enabled (getFeature("background_color") for manual colors,
# "non_aggregate_score_color"/"aggregate_score_color" for gradient/score colors).
# getFeature() returns undefined for any flag missing from these arrays, so an
# EMPTY customize_features/features list silently disables ALL cell coloring and
# the sub-technique controls. These lists must mirror the committed static
# config at frontend/public/navigator/assets/config.json.
_CUSTOMIZE_FEATURES = [
    {"name": "multiselect", "enabled": True},
    {"name": "export_render", "enabled": True},
    {"name": "export_excel", "enabled": True},
    {"name": "legend", "enabled": True},
    {"name": "background_color", "enabled": True},
    {"name": "non_aggregate_score_color", "enabled": True},
    {"name": "aggregate_score_color", "enabled": True},
    {"name": "comment_underline", "enabled": True},
    {"name": "metadata_underline", "enabled": True},
    {"name": "link_underline", "enabled": True},
]

_FEATURES = [
    {"name": "leave_site_dialog", "enabled": True},
    {"name": "tabs", "enabled": True},
    {"name": "header", "enabled": True},
    {"name": "selection_controls", "enabled": True, "subfeatures": [
        {"name": "search", "enabled": True},
        {"name": "deselect_all", "enabled": True},
        {"name": "selecting_techniques", "enabled": True},
    ]},
    {"name": "layer_controls", "enabled": True, "subfeatures": [
        {"name": "layer_settings", "enabled": True},
        {"name": "download_layer", "enabled": True},
        {"name": "filters", "enabled": True},
        {"name": "sorting", "enabled": True},
        {"name": "color_setup", "enabled": True},
        {"name": "toggle_hide_disabled", "enabled": True},
        {"name": "subtechniques", "enabled": True},
    ]},
    {"name": "technique_controls", "enabled": True, "subfeatures": [
        {"name": "disable_techniques", "enabled": True},
        {"name": "manual_color", "enabled": True},
        {"name": "scoring", "enabled": True},
        {"name": "comments", "enabled": True},
        {"name": "links", "enabled": True},
        {"name": "metadata", "enabled": True},
        {"name": "clear_annotations", "enabled": True},
    ]},
    {"name": "toolbar_controls", "enabled": True, "subfeatures": [
        {"name": "sticky_toolbar", "enabled": True},
    ]},
]

# Navigator expects these keys to always be present in assets/config.json.
# Missing arrays (e.g., features/customize_features) cause runtime crashes
# in loadConfig() where the app calls .forEach() unconditionally.
_BASE_NAVIGATOR_CONFIG = {
    "custom_context_menu_items": [],
    "default_layers": {
        "enabled": False,
        "urls": [],
    },
    "comment_color": "yellow",
    "link_color": "blue",
    "metadata_color": "purple",
    "banner": "",
    "customize_features": _CUSTOMIZE_FEATURES,
    "features": _FEATURES,
}

_VERSION_DIR_RE = re.compile(r"^v(\d+\.\d+)$")


def _normalize_version(version: str) -> str:
    return str(version).lstrip("v").strip()


def _ensure_dir_0755(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o755)


def _repair_version_directories(data_dir: Path) -> None:
    if not data_dir.exists():
        return
    for child in data_dir.iterdir():
        if child.is_dir():
            os.chmod(child, 0o755)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    _ensure_dir_0755(path.parent)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as tmp_file:
            tmp_file.write(data)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, path)
        os.chmod(path, 0o644)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _download_bytes(url: str) -> bytes:
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.content


def _scan_existing_versions(data_dir: Path) -> list[str]:
    """Return sorted list of all existing vX.Y version strings found in data_dir."""
    if not data_dir.exists():
        return []
    versions = []
    for child in data_dir.iterdir():
        m = _VERSION_DIR_RE.match(child.name)
        if m and child.is_dir():
            versions.append(m.group(1))
    versions.sort(key=lambda v: [int(x) for x in v.split(".")])
    return versions


def _version_has_any_bundles(version: str, data_dir: Path) -> bool:
    """Return True when at least one domain bundle exists for the given version."""
    version_dir = data_dir / f"v{version}"
    if not version_dir.exists():
        return False
    for filename in DOMAIN_FILENAMES.values():
        if (version_dir / f"{filename}.json").exists():
            return True
    return False


def get_served_attack_versions(
    domain: str = "enterprise-attack",
    data_root: Path = NAVIGATOR_DATA_ROOT,
) -> list[str]:
    """Return the ATT&CK versions the embedded Navigator can actually render for ``domain``.

    These are the versions with on-disk STIX bundles under ``/navigator-data/data``
    (what nginx serves at ``/navigator/data/...``). Returns an ascending-sorted list,
    or an empty list when the volume has not been synced yet.
    """
    data_dir = Path(data_root) / "data"
    domain_file = DOMAIN_FILENAMES.get(domain, domain)
    served = []
    for ver in _scan_existing_versions(data_dir):
        if (data_dir / f"v{ver}" / f"{domain_file}.json").exists():
            served.append(ver)
    return served


def resolve_navigator_attack_version(
    preferred: str | None = None,
    domain: str = "enterprise-attack",
    data_root: Path = NAVIGATOR_DATA_ROOT,
) -> str:
    """Resolve the ATT&CK version a coverage layer must declare so the Navigator applies it.

    The Navigator rejects a layer whose ``versions.attack`` has no matching loaded
    collection, so the layer must declare a version the embedded Navigator actually
    serves. Prefers ``preferred`` (e.g. the imported ``PlatformDataVersion``) when it
    is available, otherwise falls back to the latest served version, and finally to
    the committed static fallback when nothing has been synced.
    """
    preferred_norm = _normalize_version(preferred) if preferred else None
    served = get_served_attack_versions(domain, data_root)
    if served:
        if preferred_norm and preferred_norm in served:
            return preferred_norm
        return served[-1]
    # Nothing synced: the Navigator (via nginx) serves only the committed static
    # fallback index, so the layer MUST declare that exact version regardless of the
    # imported version, otherwise the layer is rejected as an invalid domain.
    return FALLBACK_NAVIGATOR_ATTACK_VERSION


def _resolve_latest_local_version(data_dir: Path) -> str | None:
    """Pick the newest on-disk ATT&CK version that has at least one bundle file."""
    versions = _scan_existing_versions(data_dir)
    for ver in reversed(versions):
        if _version_has_any_bundles(ver, data_dir):
            return ver
    return None


def _build_collection_index(version: str, data_dir: Path) -> dict:
    """Build the collection index including all existing on-disk versions plus the given one."""
    existing = _scan_existing_versions(data_dir)
    if version not in existing:
        existing.append(version)
        existing.sort(key=lambda v: [int(x) for x in v.split(".")])

    def _domain_versions(domain_file: str) -> list[dict]:
        entries = []
        for ver in existing:
            bundle_path = data_dir / f"v{ver}" / f"{domain_file}.json"
            if bundle_path.exists() or ver == version:
                entries.append({
                    "version": ver,
                    "url": f"/navigator/data/v{ver}/{domain_file}.json",
                })
        return entries

    return {
        "id": "hefaistos-navigator-index",
        "name": "Hefaistos ATT&CK Navigator Collections",
        "description": "Generated local ATT&CK collection index for embedded Navigator.",
        "collections": [
            {
                "name": "Enterprise ATT&CK",
                "versions": _domain_versions("enterprise-attack"),
            },
            {
                "name": "ICS ATT&CK",
                "versions": _domain_versions("ics-attack"),
            },
            {
                "name": "Mobile ATT&CK",
                "versions": _domain_versions("mobile-attack"),
            },
        ]
    }


def _build_config(version: str, data_dir: Path) -> dict:
    """Build the Navigator config.json referencing the local collection index and explicit version entries."""
    existing = _scan_existing_versions(data_dir)
    if version not in existing:
        existing.append(version)
        existing.sort(key=lambda v: [int(x) for x in v.split(".")])

    entries = []
    for ver in existing:
        domains = []
        for domain_name, domain_file in DOMAIN_FILENAMES.items():
            bundle_path = data_dir / f"v{ver}" / f"{domain_file}.json"
            if bundle_path.exists() or ver == version:
                domains.append({
                    "name": domain_name.replace("-attack", "").replace("-", " ").title(),
                    "identifier": domain_name,
                    "data": [f"/navigator/data/v{ver}/{domain_file}.json"],
                })
        if domains:
            entries.append({
                "name": f"ATT&CK v{ver}",
                "version": ver,
                "domains": domains,
            })

    config = {
        **_BASE_NAVIGATOR_CONFIG,
        "versions": {
            "enabled": True,
            "entries": entries,
        },
    }
    # Only fall back to the collection-index path if we have no explicit entries.
    # When both keys are present, Navigator 5.x's union code path expects the
    # STIX 2.1 Collection Index schema, which our local index.json does not
    # implement, causing an Angular APP_INITIALIZER crash
    # ("Cannot read properties of undefined (reading 'forEach')").
    if not entries:
        config["collection_index_url"] = "/navigator/data/index.json"
    return config


def _iter_version_file_urls(version: str):
    for _, filename in DOMAIN_FILENAMES.items():
        yield filename, f"{ATTACK_STIX_BASE_URL}/{filename}/{filename}-{version}.json"


def sync_navigator_data(
    attack_version: str,
    data_root: Path = NAVIGATOR_DATA_ROOT,
    fetcher: Callable[[str], bytes] = _download_bytes,
) -> None:
    version = _normalize_version(attack_version)
    root = Path(data_root)
    data_dir = root / "data"
    version_dir = data_dir / f"v{version}"

    _ensure_dir_0755(root)
    _ensure_dir_0755(data_dir)
    _repair_version_directories(data_dir)
    _ensure_dir_0755(version_dir)

    # Download STIX bundles first so the index/config can see them on disk
    for filename, url in _iter_version_file_urls(version):
        _atomic_write_bytes(version_dir / f"{filename}.json", fetcher(url))

    config_bytes = json.dumps(_build_config(version, data_dir), ensure_ascii=False, indent=2).encode("utf-8")
    index_bytes = json.dumps(_build_collection_index(version, data_dir), ensure_ascii=False, indent=2).encode("utf-8")
    _atomic_write_bytes(root / "config.json", config_bytes)
    _atomic_write_bytes(data_dir / "index.json", index_bytes)


def rebuild_navigator_config_only(
    version: str | None = None,
    data_root: Path = NAVIGATOR_DATA_ROOT,
) -> str:
    """
    Rebuild Navigator config/index from already-downloaded local STIX bundles.

    This does NOT download ATT&CK data. It only refreshes:
    - /navigator-data/config.json
    - /navigator-data/data/index.json
    """
    root = Path(data_root)
    data_dir = root / "data"

    _ensure_dir_0755(root)
    _ensure_dir_0755(data_dir)
    _repair_version_directories(data_dir)

    resolved_version = _normalize_version(version) if version else _resolve_latest_local_version(data_dir)
    if not resolved_version:
        raise ValueError(
            "No local ATT&CK bundle versions found under /navigator-data/data. "
            "Run an ATT&CK import first or pass --version for an existing local bundle."
        )

    if not _version_has_any_bundles(resolved_version, data_dir):
        raise ValueError(
            f"Version v{resolved_version} has no local STIX bundles in /navigator-data/data/v{resolved_version}."
        )

    config_bytes = json.dumps(
        _build_config(resolved_version, data_dir),
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    index_bytes = json.dumps(
        _build_collection_index(resolved_version, data_dir),
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    _atomic_write_bytes(root / "config.json", config_bytes)
    _atomic_write_bytes(data_dir / "index.json", index_bytes)

    return resolved_version
