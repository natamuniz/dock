import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from app import Dock, FolderStack, STYLE, WidgetsPanel, HotKeys
from core import default_config
from settings import SettingsDialog


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([]); cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.dock = Dock(default_config(), test_mode=True); self.dock.show(); self.app.processEvents()
        self.addCleanup(self.clean)

    def clean(self):
        self.dock.shutdown_services()
        self.dock.clock.stop(); self.dock.edge_timer.stop(); self.dock.animation.stop(); self.dock.pet_timer.stop(); self.dock.engine.close()
        self.dock.hide(); self.dock.deleteLater(); self.app.processEvents()

    def test_dense_layout_stays_inside_window_in_all_positions(self):
        for position in ("bottom", "left", "right"):
            with self.subTest(position=position):
                self.dock.config["position"] = position
                self.dock.profile["items"] = [{"name": f"Atalho {i}", "target": str(Path.home())} for i in range(12)]
                self.dock.profile["widgets"] = ["clock", "ram", "cpu", "pomodoro", "battery", "day"]
                self.dock.rebuild(); self.dock.scales = [2.] * len(self.dock.entries); self.dock.place()
                self.app.processEvents()
                for rect in self.dock.rects: self.assertTrue(self.dock.rect().contains(rect.toRect()))
                self.assertFalse(self.dock.grab().isNull())

    def test_lens_grows_and_returns_to_baseline(self):
        self.dock.pointer = self.dock.rects[1].center()
        for _ in range(30): self.dock.animate()
        self.assertGreater(self.dock.scales[1], 1.2)
        self.dock.pointer = None
        for _ in range(40): self.dock.animate()
        self.assertAlmostEqual(self.dock.scales[1], 1, places=2)

    def test_lens_keeps_reference_centers_fixed_during_magnification(self):
        centers = list(self.dock.base_centers)
        self.dock.scales = [1.8] * len(self.dock.entries)
        self.dock.compute_layout()
        self.assertEqual(self.dock.base_centers, centers)

    def test_lens_has_same_response_at_60_and_120_frames_per_second(self):
        results = []
        for frames, dt in ((8, 1 / 60), (16, 1 / 120)):
            self.dock.scales = [1.] * len(self.dock.entries); self.dock.compute_layout()
            self.dock.pointer = self.dock.rects[1].center()
            for _ in range(frames): self.dock.animate(dt)
            results.append(self.dock.scales[1])
        self.assertAlmostEqual(results[0], results[1], places=10)

    def test_hidden_dock_does_not_reclaim_space_on_screen_change(self):
        self.dock.manual_hidden = True
        with patch.object(self.dock.appbar, "reserve") as reserve:
            self.dock.reserve()
        reserve.assert_not_called()
        self.assertIsNone(self.dock.appbar.data)

    def test_island_and_topbar_follow_manual_visibility_and_shutdown(self):
        self.dock.config["island_enabled"] = True; self.dock.sync_panels()
        self.assertTrue(self.dock.island.isVisible()); self.assertTrue(self.dock.topbar.isVisible())
        self.dock.toggle_visibility()
        self.assertFalse(self.dock.island.isVisible()); self.assertFalse(self.dock.topbar.isVisible())
        self.dock.toggle_visibility()
        self.assertTrue(self.dock.island.isVisible()); self.assertTrue(self.dock.topbar.isVisible())
        self.dock.shutdown_services()
        self.assertFalse(self.dock.island.isVisible()); self.assertFalse(self.dock.topbar.isVisible())
        self.assertFalse(self.dock.island._ticker.isActive())
        self.assertFalse(self.dock.topbar.refresh_timer.isActive())

    def test_native_appbar_callback_uses_windows_message_handle_and_ignores_other_bars(self):
        import ctypes
        from ctypes import wintypes
        from types import SimpleNamespace
        msg = wintypes.MSG(); msg.hWnd = int(self.dock.winId()); msg.message = 0x8011; msg.wParam = 1
        with patch("app.native.IS_WINDOWS", True), patch("app.QTimer.singleShot") as schedule:
            HotKeys.nativeEventFilter(SimpleNamespace(dock=self.dock), b"windows_generic_MSG", ctypes.addressof(msg))
            schedule.assert_called_once_with(0, self.dock.appbar_changed)
            schedule.reset_mock(); msg.hWnd = 1234
            HotKeys.nativeEventFilter(SimpleNamespace(dock=self.dock), b"windows_generic_MSG", ctypes.addressof(msg))
            schedule.assert_not_called()

    def test_trailing_controls_preserve_apps_first_and_allow_clean_dock(self):
        self.assertEqual(self.dock.entries[0]["kind"], "app")
        self.assertEqual([e["kind"] for e in self.dock.entries[-3:]], ["trash", "settings", "profile"])
        self.dock.config.update(show_trash=False, show_settings=False, show_start=True)
        self.dock.rebuild()
        self.assertEqual(self.dock.entries[0]["kind"], "start")
        self.assertNotIn("trash", [e["kind"] for e in self.dock.entries])
        self.assertNotIn("settings", [e["kind"] for e in self.dock.entries])

    def test_environment_dots_select_the_corresponding_profile(self):
        index = len(self.dock.entries) - 1
        self.dock.hover = index
        self.dock.pointer = self.dock.profile_points(self.dock.rects[index])[2]
        self.dock.activate_entry(self.dock.entries[index])
        self.assertEqual(self.dock.config["active"], 2)

    def test_no_motion_keeps_icons_still_and_grow_only_enlarges_hovered_app(self):
        self.dock.pointer = self.dock.rects[1].center(); self.dock.hover = 1
        self.dock.config["motion"] = "none"
        for _ in range(30): self.dock.animate()
        self.assertTrue(all(scale == 1 for scale in self.dock.scales))
        self.dock.config["motion"] = "grow"
        for _ in range(30): self.dock.animate()
        self.assertGreater(self.dock.scales[1], 1.2)
        self.assertEqual(self.dock.scales[0], 1)

    def test_shelf_encloses_unmagnified_icons_at_every_size(self):
        for position in ("bottom", "left", "right"):
            for size in (32, 48, 64):
                self.dock.config.update(position=position, icon_size=size)
                self.dock.rebuild(); self.dock.place()
                for entry, rect in zip(self.dock.entries, self.dock.rects):
                    if entry["kind"] == "app": self.assertTrue(self.dock.bar_rect.contains(rect))

    def test_cancelling_settings_leaves_configuration_unchanged(self):
        original = copy.deepcopy(self.dock.config)
        dialog = SettingsDialog(self.dock.config, self.dock.engine, self.dock)
        dialog.profile_name.setText("Alterado"); dialog.store_profile(); dialog.reject()
        self.assertEqual(self.dock.config, original)

    def test_profile_edits_roundtrip_and_remove_without_losing_other_profile(self):
        dialog = SettingsDialog(self.dock.config, self.dock.engine, self.dock)
        dialog.profile_name.setText("Desenvolvimento Natã")
        dialog.profiles.setCurrentRow(1); dialog.profiles.setCurrentRow(0)
        self.assertEqual(dialog.profile_name.text(), "Desenvolvimento Natã")
        dialog.remove_profile(); self.assertEqual(dialog.collect()["profiles"][0]["name"], "Trabalho")
        dialog.reject()

    def test_widgets_panel_has_a_card_for_every_widget(self):
        panel = WidgetsPanel(self.dock)
        self.assertEqual(len(panel.cards), len(self.dock.engine.catalog()))
        panel.filter("Pomodoro")
        self.assertFalse(panel.cards["pomodoro"][0].isHidden()); self.assertTrue(panel.cards["cpu"][0].isHidden())
        panel.close()

    def test_folder_stack_lists_files_and_navigates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "Documento.txt").write_text("Olá"); (root / "Subpasta").mkdir()
            stack = FolderStack(root, self.dock); self.assertEqual(stack.list.count(), 2)
            stack.open_item(stack.list.item(0)); self.assertEqual(stack.path.name, "Subpasta"); stack.close()

    def test_profile_switch_and_pin_unpin(self):
        self.dock.switch_profile(2); self.assertEqual(self.dock.profile["name"], "Estudo")
        self.dock.pin_widget("cpu"); self.assertIn("cpu", self.dock.profile["widgets"])
        self.dock.unpin_widget("cpu"); self.assertNotIn("cpu", self.dock.profile["widgets"])

    def test_explicit_window_ownership_separates_two_windows_of_same_app(self):
        import os
        exe = str(Path.home() / "browser.exe")
        for profile in self.dock.config["profiles"][:2]: profile["items"] = [{"name": "Browser", "target": exe}]
        records = [{"hwnd": i, "pid": 101, "created": 123., "exe": os.path.normcase(exe)} for i in (1, 2)]
        class Recovery:
            def __init__(self): self.records = []
            def hide(self, record):
                if record not in self.records: self.records.append(record)
            def show(self, record):
                if record in self.records: self.records.remove(record)
        self.dock.recovery = Recovery()
        self.dock.window_owners = {self.dock.window_key(record): i for i, record in enumerate(records)}
        with patch("app.native.windows", return_value=records):
            self.dock.isolate_windows(0); self.assertEqual(self.dock.recovery.records, [records[1]])
            self.dock.isolate_windows(1); self.assertEqual(self.dock.recovery.records, [records[0]])
        self.dock.recovery = None

    def test_new_file_count_is_computed_in_background(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.txt").write_text("a"); (root / "b.txt").write_text("b")
            self.dock.profile["items"] = [{"name": "Pasta", "target": directory, "track_new": True}]
            self.dock.config["folder_seen"] = {directory: 0}
            self.dock.refresh_folders()
            self.assertEqual(self.dock.folder_futures[directory].result(timeout=1), 2)
            self.dock.refresh_folders(); self.assertEqual(self.dock.folder_counts[directory], 2)
