import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core import Pomodoro, default_config, load_config, save_config, validate_config, validate_target


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "config.json"

    def test_round_trip_unicode_and_profile_widgets(self):
        config = default_config(); config["profiles"][0]["name"] = "Natã · Produção"
        config["profiles"][0]["widgets"] = ["clock", "ram"]
        save_config(config, self.path)
        self.assertEqual(load_config(self.path), (config, None))

    def test_failure_keeps_previous_file(self):
        config = default_config(); save_config(config, self.path)
        altered = copy.deepcopy(config); altered["active"] = 2
        with patch("core.os.replace", side_effect=OSError("disco indisponível")):
            with self.assertRaises(OSError): save_config(altered, self.path)
        self.assertEqual(load_config(self.path)[0], config)
        self.assertFalse(list(self.path.parent.glob(".ntdock-*")))

    def test_corrupt_main_recovers_backup(self):
        config = default_config(); save_config(config, self.path); save_config(config, self.path)
        self.path.write_text("{invalid", encoding="utf-8")
        recovered, message = load_config(self.path)
        self.assertEqual(recovered, config); self.assertIn("backup", message)
        self.assertEqual(load_config(self.path), (config, None))

    def test_corrupt_file_is_preserved(self):
        self.path.write_text("broken", encoding="utf-8")
        config, message = load_config(self.path)
        self.assertEqual(config, default_config())
        self.assertTrue(list(self.path.parent.glob("config-invalida-*.json")))
        self.assertIn("preservada", message)

    def test_invalid_import_never_overwrites(self):
        original = default_config(); save_config(original, self.path)
        invalid = copy.deepcopy(original); invalid["active"] = 999
        with self.assertRaises(ValueError): save_config(invalid, self.path)
        self.assertEqual(load_config(self.path)[0], original)

    def test_rejects_invalid_domain_values(self):
        cases = [{"icon_size": float("nan")}, {"magnification": float("inf")}, {"profiles": []},
                 {"active": True}, {"position": "top"}, {"widgets": ["clock"] * 7},
                 {"widget_options": {"latitude": "bad"}}, {"widget_options": {"online": "false"}},
                 {"widget_options": {"timer_minutes": 0}}]
        for changed in cases:
            with self.subTest(changed=changed):
                config = default_config(); config.update(changed)
                with self.assertRaises(ValueError): validate_config(config)

    def test_widget_numeric_strings_normalized(self):
        config = default_config(); config["widget_options"] = {"timer_minutes": "15", "latitude": "-22.9"}
        clean = validate_config(config)
        self.assertEqual(clean["widget_options"]["timer_minutes"], 15)
        self.assertEqual(clean["widget_options"]["latitude"], -22.9)

    def test_rejects_executable_url_schemes(self):
        for target in ("javascript://alert(1)", "file:///tmp/a", "https://", "calc.exe && echo x", "https://example.com\nabc"):
            with self.subTest(target=target), self.assertRaises(ValueError): validate_target(target)
        self.assertEqual(validate_target("https://example.com"), "https://example.com")
        self.assertEqual(validate_target(str(Path(self.temp.name))), str(Path(self.temp.name)))


class TimerTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.; self.timer = Pomodoro(clock=lambda: self.now)

    def test_pause_resume_does_not_lose_elapsed_time(self):
        self.timer.toggle(); self.now += 17.3
        self.timer.toggle(); left = self.timer.seconds()
        self.now += 100; self.assertEqual(self.timer.seconds(), left)
        self.timer.toggle(); self.now += 5; self.assertEqual(self.timer.seconds(), left - 5)

    def test_completed_phase_stops_and_transitions_once(self):
        self.timer.toggle(); self.now += 1501
        self.assertTrue(self.timer.tick()); self.assertEqual(self.timer.phase, "Pausa")
        self.assertEqual(self.timer.seconds(), 300); self.assertFalse(self.timer.tick())
        self.timer.toggle(); self.now += 300
        self.assertTrue(self.timer.tick()); self.assertEqual(self.timer.phase, "Foco")

    def test_reset_cancels_deadline(self):
        self.timer.toggle(); self.now += 5; self.timer.reset()
        self.assertIsNone(self.timer.deadline); self.assertEqual(self.timer.seconds(), 1500)
