import os
import stat
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from platform_data.navigator_sync import (
    sync_navigator_data,
    _build_collection_index,
    _build_config,
    rebuild_navigator_config_only,
    get_served_attack_versions,
    resolve_navigator_attack_version,
    FALLBACK_NAVIGATOR_ATTACK_VERSION,
)


class NavigatorSyncPermissionsTests(SimpleTestCase):
    def _mode(self, path: Path) -> int:
        return stat.S_IMODE(os.stat(path).st_mode)

    def _fake_fetcher(self, _url: str) -> bytes:
        return b'{"type":"bundle","objects":[]}'

    def test_fresh_sync_creates_0755_dirs_and_0644_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sync_navigator_data("19.0", data_root=root, fetcher=self._fake_fetcher)

            self.assertEqual(self._mode(root), 0o755)
            self.assertEqual(self._mode(root / "data"), 0o755)
            self.assertEqual(self._mode(root / "data" / "v19.0"), 0o755)

            self.assertEqual(self._mode(root / "config.json"), 0o644)
            self.assertEqual(self._mode(root / "data" / "index.json"), 0o644)
            self.assertEqual(self._mode(root / "data" / "v19.0" / "enterprise-attack.json"), 0o644)
            self.assertEqual(self._mode(root / "data" / "v19.0" / "ics-attack.json"), 0o644)
            self.assertEqual(self._mode(root / "data" / "v19.0" / "mobile-attack.json"), 0o644)

    def test_sync_repairs_preexisting_0700_version_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing_data_dir = root / "data"
            existing_v18_dir = existing_data_dir / "v18.0"
            existing_v19_dir = existing_data_dir / "v19.0"

            existing_v18_dir.mkdir(parents=True, exist_ok=True)
            existing_v19_dir.mkdir(parents=True, exist_ok=True)
            os.chmod(root, 0o700)
            os.chmod(existing_data_dir, 0o700)
            os.chmod(existing_v18_dir, 0o700)
            os.chmod(existing_v19_dir, 0o700)

            sync_navigator_data("19.0", data_root=root, fetcher=self._fake_fetcher)

            self.assertEqual(self._mode(root), 0o755)
            self.assertEqual(self._mode(existing_data_dir), 0o755)
            self.assertEqual(self._mode(existing_v18_dir), 0o755)
            self.assertEqual(self._mode(existing_v19_dir), 0o755)

    def test_sync_writes_non_empty_collection_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sync_navigator_data("19.0", data_root=root, fetcher=self._fake_fetcher)

            index_data = json.loads((root / "data" / "index.json").read_text(encoding="utf-8"))
            self.assertTrue(index_data.get("collections"))
            self.assertIn("id", index_data)
            self.assertEqual(len(index_data["collections"]), 3)


class NavigatorSyncMultiVersionTests(SimpleTestCase):
    """Tests that multi-version scenarios produce correct index and config."""

    def _fake_fetcher(self, _url: str) -> bytes:
        return b'{"type":"bundle","objects":[]}'

    def test_second_sync_preserves_first_version_in_index(self):
        """After syncing v18.0 then v19.0, both appear in index.json."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sync_navigator_data("18.0", data_root=root, fetcher=self._fake_fetcher)
            sync_navigator_data("19.0", data_root=root, fetcher=self._fake_fetcher)

            index_data = json.loads((root / "data" / "index.json").read_text(encoding="utf-8"))
            for collection in index_data["collections"]:
                versions_in_collection = [v["version"] for v in collection["versions"]]
                self.assertIn("18.0", versions_in_collection, msg=f"{collection['name']} missing v18.0")
                self.assertIn("19.0", versions_in_collection, msg=f"{collection['name']} missing v19.0")

    def test_second_sync_preserves_first_version_in_config(self):
        """After syncing v18.0 then v19.0, both appear in config.json versions entries."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sync_navigator_data("18.0", data_root=root, fetcher=self._fake_fetcher)
            sync_navigator_data("19.0", data_root=root, fetcher=self._fake_fetcher)

            config_data = json.loads((root / "config.json").read_text(encoding="utf-8"))
            self.assertTrue(config_data["versions"]["enabled"])
            entry_versions = [e["version"] for e in config_data["versions"]["entries"]]
            self.assertIn("18.0", entry_versions)
            self.assertIn("19.0", entry_versions)

    def test_build_collection_index_includes_new_version_even_before_download(self):
        """_build_collection_index always includes the given version even if its dir is empty."""
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()
            # Pre-populate an older version directory with bundle files
            v18_dir = data_dir / "v18.0"
            v18_dir.mkdir()
            (v18_dir / "enterprise-attack.json").write_bytes(b'{}')
            (v18_dir / "ics-attack.json").write_bytes(b'{}')
            (v18_dir / "mobile-attack.json").write_bytes(b'{}')

            index = _build_collection_index("19.0", data_dir)
            for collection in index["collections"]:
                ver_list = [v["version"] for v in collection["versions"]]
                self.assertIn("18.0", ver_list)
                self.assertIn("19.0", ver_list)

    def test_config_omits_collection_index_url_when_entries_exist(self):
        """config.json should not include collection_index_url when versions entries exist."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sync_navigator_data("19.0", data_root=root, fetcher=self._fake_fetcher)
            config_data = json.loads((root / "config.json").read_text(encoding="utf-8"))
            self.assertNotIn("collection_index_url", config_data)

    def test_build_config_omits_collection_index_url_with_requested_version_only(self):
        """_build_config omits collection_index_url when requested version creates entries."""
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()

            config = _build_config("19.0", data_dir)

            self.assertTrue(config["versions"]["entries"])
            self.assertNotIn("collection_index_url", config)
            self.assertIn("custom_context_menu_items", config)
            self.assertIn("features", config)
            self.assertIn("customize_features", config)
            self.assertIsInstance(config["custom_context_menu_items"], list)
            self.assertIsInstance(config["features"], list)
            self.assertIsInstance(config["customize_features"], list)

            # The Navigator only paints cells when these flags are present & enabled;
            # an empty customize_features list silently disables ALL coverage coloring.
            color_flags = {
                f["name"]: f.get("enabled")
                for f in config["customize_features"]
            }
            for flag in ("background_color", "non_aggregate_score_color", "aggregate_score_color"):
                self.assertTrue(color_flags.get(flag), msg=f"coloring flag '{flag}' must be enabled")
            # Sub-technique controls live under layer_controls in features.
            self.assertTrue(config["features"], "features must not be empty")

    def test_build_config_includes_collection_index_url_when_no_entries(self):
        """_build_config includes collection_index_url only in the no-entry fallback branch."""
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            data_dir.mkdir()

            with patch.dict("platform_data.navigator_sync.DOMAIN_FILENAMES", {}, clear=True):
                config = _build_config("19.0", data_dir)

            self.assertEqual(config["versions"]["entries"], [])
            self.assertIn("collection_index_url", config)
            self.assertEqual(config["collection_index_url"], "/navigator/data/index.json")
            self.assertIn("custom_context_menu_items", config)
            self.assertIn("features", config)
            self.assertIn("customize_features", config)


class NavigatorConfigOnlyRebuildTests(SimpleTestCase):
    def _write_bundle(self, data_dir: Path, version: str, domain_file: str) -> None:
        path = data_dir / f"v{version}" / f"{domain_file}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"type":"bundle","objects":[]}', encoding="utf-8")

    def test_rebuild_uses_latest_local_version_when_not_specified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            self._write_bundle(data_dir, "18.0", "enterprise-attack")
            self._write_bundle(data_dir, "19.1", "enterprise-attack")

            resolved = rebuild_navigator_config_only(data_root=root)

            self.assertEqual(resolved, "19.1")
            config = json.loads((root / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["versions"]["entries"][-1]["version"], "19.1")

    def test_rebuild_with_explicit_existing_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "data"
            self._write_bundle(data_dir, "19.1", "enterprise-attack")
            self._write_bundle(data_dir, "19.1", "ics-attack")
            self._write_bundle(data_dir, "19.1", "mobile-attack")

            resolved = rebuild_navigator_config_only(version="19.1", data_root=root)

            self.assertEqual(resolved, "19.1")
            self.assertTrue((root / "config.json").exists())
            self.assertTrue((root / "data" / "index.json").exists())

    def test_rebuild_errors_when_no_local_bundles_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValueError):
                rebuild_navigator_config_only(data_root=root)

    def test_rebuild_errors_when_requested_version_missing_bundles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data" / "v19.1").mkdir(parents=True, exist_ok=True)
            with self.assertRaises(ValueError):
                rebuild_navigator_config_only(version="19.1", data_root=root)


class ResolveNavigatorAttackVersionTests(SimpleTestCase):
    """The coverage layer must declare a version the embedded Navigator can render."""

    def _seed_bundle(self, root: Path, version: str) -> None:
        version_dir = root / "data" / f"v{version}"
        version_dir.mkdir(parents=True, exist_ok=True)
        (version_dir / "enterprise-attack.json").write_text("{}", encoding="utf-8")

    def test_no_synced_data_falls_back_to_static_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Even when an imported version exists, with nothing synced the Navigator
            # only serves the committed static fallback, so the layer must match it.
            self.assertEqual(
                resolve_navigator_attack_version("17.1", data_root=root),
                FALLBACK_NAVIGATOR_ATTACK_VERSION,
            )
            self.assertEqual(
                resolve_navigator_attack_version(None, data_root=root),
                FALLBACK_NAVIGATOR_ATTACK_VERSION,
            )

    def test_served_versions_reflect_on_disk_bundles(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_bundle(root, "18.0")
            self._seed_bundle(root, "19.1")
            self.assertEqual(get_served_attack_versions(data_root=root), ["18.0", "19.1"])

    def test_preferred_version_used_when_served(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_bundle(root, "18.0")
            self._seed_bundle(root, "19.1")
            self.assertEqual(resolve_navigator_attack_version("v18.0", data_root=root), "18.0")

    def test_unservable_preferred_falls_back_to_latest_served(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed_bundle(root, "18.0")
            self._seed_bundle(root, "19.1")
            # Imported 17.1 has no bundle -> use the newest version that can render.
            self.assertEqual(resolve_navigator_attack_version("17.1", data_root=root), "19.1")
