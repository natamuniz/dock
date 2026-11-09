import copy
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from appearance import palette, _luminance
from core import default_config, validate_config
from settings import SettingsDialog
from widgets import WidgetEngine


class AppearanceTests(unittest.TestCase):
    def test_custom_colors_are_independent_and_choose_readable_text(self):
        config = default_config(); config.update(dock_color="#FFFFFF", topbar_color="#101522")
        dock, bar = palette(config), palette(config, "topbar")
        self.assertEqual(dock["foreground"], "#000000")
        self.assertEqual(bar["foreground"], "#FFFFFF")
        for values in (dock, bar):
            text = _luminance(values["foreground"])
            for edge in ("top", "bottom"):
                background = _luminance(values[edge])
                self.assertGreaterEqual((max(text, background) + .05) / (min(text, background) + .05), 4.5)
        self.assertNotEqual(dock["bottom"], bar["bottom"])
        config["dock_color"] = ""
        self.assertEqual(palette(config)["bottom"], palette(default_config())["bottom"])

    def test_custom_color_and_font_edits_are_transactional(self):
        config = default_config(); original = copy.deepcopy(config)
        engine = WidgetEngine(); self.addCleanup(engine.close)
        dialog = SettingsDialog(config, engine); self.addCleanup(dialog.deleteLater)
        dialog.dock_color.setText("#804FC0"); dialog.topbar_color.setText("#F3F0E9")
        dialog.topbar_font.setCurrentText("Calibri"); dialog.topbar_font_size.setValue(14)
        result = dialog.collect()
        self.assertEqual(result["dock_color"], "#804FC0")
        self.assertEqual(result["topbar_color"], "#F3F0E9")
        self.assertEqual(result["topbar_font"], "Calibri")
        self.assertEqual(result["topbar_font_size"], 14)
        dialog.reject(); self.assertEqual(config, original)

    def test_invalid_color_or_font_import_is_rejected(self):
        for key, value in (("dock_color", "red"), ("topbar_color", "#fff"), ("dock_color", None),
                           ("topbar_font", "broken';color:red"), ("topbar_font_size", True), ("topbar_font_size", 20)):
            with self.subTest(key=key, value=value):
                config = default_config(); config[key] = value
                with self.assertRaises(ValueError): validate_config(config)

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_legacy_light_and_dark_configs_keep_distinct_readable_palettes(self):
        light, dark = palette({"theme": "light"}), palette({"theme": "dark"})
        self.assertNotEqual(light["foreground"], dark["foreground"])
        self.assertNotEqual(light["bottom"], dark["bottom"])
        light["top"] = "changed"
        self.assertNotEqual(palette({"theme": "light"})["top"], "changed")

    def test_invalid_imported_appearance_fields_are_rejected(self):
        for key, value in (("appearance_preset", []), ("appearance_preset", "missing"),
                           ("motion", "slow"), ("launch_animation", "unknown"),
                           ("bar_padding", True), ("bar_padding", 17),
                           ("show_trash", "true"), ("profile_dots", 1),
                           ("island_enabled", "true"), ("topbar_status", 1), ("media_enabled", []), ("rounded_windows", "true")):
            with self.subTest(key=key, value=value):
                config = default_config(); config[key] = value
                with self.assertRaises(ValueError): validate_config(config)

    def test_theme_and_motion_edits_collect_without_mutating_running_config(self):
        config = default_config(); original = copy.deepcopy(config)
        engine = WidgetEngine(); self.addCleanup(engine.close)
        dialog = SettingsDialog(config, engine); self.addCleanup(dialog.deleteLater)
        dialog.preset.setCurrentIndex(dialog.preset.findData("lagoon"))
        dialog.padding.setValue(3)
        dialog.motion.setCurrentIndex(dialog.motion.findData("grow"))
        dialog.flags["show_trash"].setChecked(False)
        collected = dialog.collect()
        self.assertEqual(config, original)
        self.assertEqual(collected["appearance_preset"], "lagoon")
        self.assertEqual(collected["bar_padding"], 3)
        self.assertEqual(collected["motion"], "grow")
        self.assertFalse(collected["show_trash"])
        dialog.reject()
        self.assertEqual(config, original)

    def test_saving_legacy_settings_does_not_silently_select_a_new_theme(self):
        config = default_config(); config.pop("appearance_preset"); config["theme"] = "light"
        engine = WidgetEngine(); self.addCleanup(engine.close)
        dialog = SettingsDialog(config, engine); self.addCleanup(dialog.deleteLater)
        result = dialog.collect()
        self.assertNotIn("appearance_preset", result)
        self.assertEqual(result["theme"], "light")
        self.assertTrue(dialog.theme.isEnabled())
