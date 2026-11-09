import copy
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect
from PySide6.QtWidgets import QApplication

from core import default_config
from topbar import TopBar
import native


class Screen:
    def __init__(self, width=800): self.width = width
    def geometry(self): return QRect(50, 80, self.width, 600)
    def devicePixelRatio(self): return 1.5
    def name(self): return "TopBar test monitor"


class Reservation:
    def __init__(self):
        self.data = None
        self.calls = []
        self.removals = 0
    def reserve(self, hwnd, rect, position, thickness):
        self.calls.append((hwnd, rect, position, thickness))
        self.data = SimpleNamespace(rect=native.W.RECT(rect[0], rect[1], rect[0] + rect[2], rect[1] + thickness))
    def remove(self):
        self.removals += 1
        self.data = None
    def reposition(self): return False


class TopBarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        config = default_config(); config.update(island_enabled=True, topbar_enabled=True)
        self.screen = Screen()
        self.dock = SimpleNamespace(config=config, manual_hidden=False, chosen_screen=lambda: self.screen)
        def switch(index): self.dock.config["active"] = index
        self.dock.switch_profile = Mock(side_effect=switch)
        self.patches = [patch("topbar.psutil.net_if_stats", return_value={"Ethernet": SimpleNamespace(isup=True)}),
                        patch("topbar.psutil.sensors_battery", return_value=None)]
        for item in self.patches: item.start(); self.addCleanup(item.stop)
        self.bar = TopBar(self.dock, test_mode=True)
        self.addCleanup(self.clean)

    def clean(self):
        self.bar.shutdown(); self.bar.deleteLater(); self.app.processEvents()

    def test_dependency_and_manual_hide_release_visibility(self):
        self.assertTrue(self.bar.isVisible())
        self.dock.config["island_enabled"] = False; self.bar.sync()
        self.assertTrue(self.bar.isVisible())
        for field in ("topbar_enabled",):
            self.dock.config[field] = False; self.bar.sync(); self.assertFalse(self.bar.isVisible())
            self.dock.config[field] = True; self.bar.sync(); self.assertTrue(self.bar.isVisible())
        self.dock.manual_hidden = True; self.bar.sync(); self.assertFalse(self.bar.isVisible())
        self.dock.manual_hidden = False; self.bar.sync(); self.assertTrue(self.bar.isVisible())

    def test_narrow_monitor_elides_profile_and_keeps_controls_inside(self):
        self.screen.width = 240
        self.dock.config["profiles"][0]["name"] = "Ambiente com um nome bastante comprido"
        self.bar.sync(); self.app.processEvents()
        self.assertIn("…", self.bar.profile_button.text())
        self.assertNotIn("·", self.bar.clock_button.text())
        for button in (self.bar.profile_button, self.bar.clock_button, self.bar.status_button, self.bar.tray_button):
            self.assertTrue(self.bar.rect().contains(button.geometry()), button.accessibleName())

    def test_custom_font_and_color_apply_without_expanding_the_bar(self):
        self.dock.config.update(topbar_color="#F8F8F8", topbar_font="Calibri", topbar_font_size=15)
        self.bar.sync(); self.app.processEvents()
        self.assertEqual(self.bar.height(), 28)
        self.assertIn("Calibri", self.bar.styleSheet())
        self.assertIn("15px", self.bar.styleSheet())
        self.assertIn("#000000", self.bar.styleSheet())

    def test_profiles_menu_switches_with_no_configuration_copy_loss(self):
        original = copy.deepcopy(self.dock.config["profiles"])
        self.bar.show_profiles()
        self.bar.profile_menu.actions()[1].trigger()
        self.dock.switch_profile.assert_called_once_with(1)
        self.assertEqual(self.dock.config["active"], 1)
        self.assertIn(self.dock.config["profiles"][1]["name"], self.bar.profile_button.accessibleName())
        self.assertEqual(self.dock.config["profiles"], original)

    def test_status_reports_only_real_volume_and_battery_values(self):
        self.dock.media = SimpleNamespace(snapshot=lambda: {"volume": None, "muted": False})
        self.bar.sync(); self.assertNotIn("%", self.bar.status_button.text())
        self.dock.media.snapshot = lambda: {"volume": 42, "muted": True}
        with patch("topbar.psutil.sensors_battery", return_value=SimpleNamespace(percent=83, power_plugged=True)):
            self.bar.sync()
        self.assertIn("42%", self.bar.status_button.text())
        self.assertIn("83%", self.bar.status_button.text())
        self.assertIn("sem som", self.bar.status_button.accessibleName())

    def test_system_controls_use_declared_native_callbacks(self):
        with patch.object(native, "open_system_panel", create=True) as open_panel:
            self.bar.clock_button.click(); self.bar.status_button.click(); self.bar.tray_button.click()
        self.assertEqual([call.args for call in open_panel.call_args_list], [("notifications",), ("quick_settings",), ("tray",)])

    def test_top_reservation_is_independent_idempotent_and_released(self):
        self.bar.shutdown()
        self.bar.deleteLater()
        reservation = Reservation()
        with patch("topbar.native.AppBar", return_value=reservation), patch("topbar.native.monitor_rect", return_value=(100, 200, 1200, 900)):
            self.bar = TopBar(self.dock, test_mode=False)
            self.bar.refresh_timer.stop()
            self.assertEqual(reservation.calls[0][2:], ("top", 42))
            self.bar.sync(); self.assertEqual(len(reservation.calls), 1)
            self.dock.config["auto_hide"] = True; self.bar.sync()
            self.assertIsNotNone(reservation.data)
            self.dock.config["auto_hide"] = False; self.bar.sync()
            self.assertEqual(len(reservation.calls), 1)
            self.dock.manual_hidden = True; self.bar.sync()
            self.assertIsNone(reservation.data)
            self.dock.manual_hidden = False; self.bar.sync()
            self.assertEqual(len(reservation.calls), 2)
            self.bar.shutdown(); self.assertIsNone(reservation.data)
            self.bar.sync(); self.assertFalse(self.bar.isVisible())
            self.assertEqual(len(reservation.calls), 2)
