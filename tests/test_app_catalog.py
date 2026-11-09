import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app_catalog import AppPickerDialog, installed_apps


class CatalogTests(unittest.TestCase):
    def test_inventory_excludes_utilities_and_deduplicates_resolved_apps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exe = root / "browser.exe"; exe.write_bytes(b"")
            other = root / "editor.exe"; other.write_bytes(b"")
            for name in ("Browser", "Browser (Duplicate)", "Editor", "Uninstall Editor", "Editor Help", "Broken"):
                (root / (name + ".lnk")).write_bytes(b"")
            def resolve(path):
                if path.stem.startswith("Browser"): return str(exe)
                if path.stem == "Broken": return str(root / "missing.exe")
                return str(other)
            result = installed_apps([root], resolver=resolve, include_system=False)
            self.assertEqual([item["name"] for item in result], ["Browser", "Editor"])
            self.assertTrue(all(Path(item["target"]).suffix == ".lnk" for item in result))

    def test_unresolved_shortcuts_are_preserved_and_other_file_types_are_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "Packaged App.lnk").write_bytes(b"")
            (root / "notes.txt").write_text("notes")
            result = installed_apps([root], resolver=lambda _: "", include_system=False)
            self.assertEqual(result, [{"name": "Packaged App", "target": str(root / "Packaged App.lnk")}])


class PickerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_filter_and_accept_returns_selected_shortcut_without_launching_it(self):
        records = [{"name": "Editor", "target": str(Path.home() / "editor.lnk")},
                   {"name": "Browser", "target": str(Path.home() / "browser.lnk")}]
        with patch("app_catalog.installed_apps", return_value=records):
            picker = AppPickerDialog(existing_targets=[records[0]["target"]])
            try:
                picker._future.result(timeout=2); picker.populate()
                self.assertFalse(picker.list.item(0).flags() & Qt.ItemIsEnabled)
                picker.search.setText("brow")
                self.assertTrue(picker.list.item(0).isHidden())
                self.assertFalse(picker.list.item(1).isHidden())
                picker.list.setCurrentRow(1); picker.choose()
                self.assertEqual(picker.value, records[1])
                self.assertTrue(picker._closed)
            finally:
                picker.reject()

    def test_cancel_keeps_value_empty_and_closes_worker(self):
        with patch("app_catalog.installed_apps", return_value=[]):
            picker = AppPickerDialog(); picker.reject()
            self.assertIsNone(picker.value)
            self.assertTrue(picker._closed)
