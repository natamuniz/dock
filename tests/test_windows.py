import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

import native


@unittest.skipUnless(native.IS_WINDOWS, "Requires a real Windows desktop")
class WindowsIntegrationTests(unittest.TestCase):
    def test_watchdog_restores_bottom_corners_after_crash(self):
        from window_effects import region_state
        helper = Path(__file__).with_name("native_helper.py")
        env = dict(os.environ, QT_QPA_PLATFORM="windows", NT_CORNER_VICTIM="1")
        with tempfile.TemporaryDirectory() as directory:
            record_path = Path(directory) / "record.json"; recovery_path = Path(directory) / "recovery.json"
            victim = subprocess.Popen([sys.executable, str(helper), "victim", str(record_path)], env=env)
            self.addCleanup(lambda: victim.terminate() if victim.poll() is None else None)
            deadline = time.monotonic() + 8
            while not record_path.exists() and time.monotonic() < deadline: time.sleep(.1)
            self.assertTrue(record_path.exists())
            record = json.loads(record_path.read_text())
            self.assertIsNone(region_state(record["hwnd"])[0])
            hider = subprocess.run([sys.executable, str(helper), "corner-hider", str(record_path), str(recovery_path)], env=env, timeout=8)
            self.assertEqual(hider.returncode, 77)
            deadline = time.monotonic() + 8
            while recovery_path.exists() and time.monotonic() < deadline: time.sleep(.1)
            self.assertFalse(recovery_path.exists())
            self.assertIsNone(region_state(record["hwnd"])[0])
            victim.terminate(); victim.wait(timeout=5)

    def test_watchdog_restores_disposable_foreign_window_after_crash(self):
        helper = Path(__file__).with_name("native_helper.py")
        env = dict(os.environ, QT_QPA_PLATFORM="windows")
        with tempfile.TemporaryDirectory() as directory:
            record_path = Path(directory) / "record.json"; recovery_path = Path(directory) / "recovery.json"
            victim = subprocess.Popen([sys.executable, str(helper), "victim", str(record_path)], env=env)
            self.addCleanup(lambda: victim.terminate() if victim.poll() is None else None)
            deadline = time.monotonic() + 8
            while not record_path.exists() and time.monotonic() < deadline: time.sleep(.1)
            self.assertTrue(record_path.exists(), "Disposable test window did not start")
            record = json.loads(record_path.read_text())
            self.assertTrue(native.alive(record))
            hider = subprocess.run([sys.executable, str(helper), "hider", str(record_path), str(recovery_path)], env=env, timeout=8)
            self.assertEqual(hider.returncode, 77)
            deadline = time.monotonic() + 8
            while recovery_path.exists() and time.monotonic() < deadline: time.sleep(.1)
            self.assertFalse(recovery_path.exists(), "Watchdog did not finish")
            self.assertTrue(native.user.IsWindowVisible(record["hwnd"]))
            victim.terminate(); victim.wait(timeout=5)
