"""Taskbar transition tests with an injected shell; no real desktop changes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import native


class TaskbarTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "recovery.json"
        # Avoid launching the native guard or touching the real Windows shell.
        with patch.object(native, "IS_WINDOWS", False):
            self.recovery = native.Recovery(self.path)
        self.user = MagicMock()
        self.user.IsWindowVisible.side_effect = lambda hwnd: hwnd == 11
        self.user.IsWindow.return_value = True
        self.stack = []
        for patcher in (
            patch.object(native, "IS_WINDOWS", True),
            patch.object(native, "user", self.user, create=True),
            patch.object(native, "taskbars", return_value=[11, 22]),
            patch.object(native, "workarea_snapshot", return_value=None),
        ):
            patcher.start(); self.addCleanup(patcher.stop)

    def test_releases_reservation_only_after_persisting_undo(self):
        def set_state(state):
            data = json.loads(self.path.read_text())
            self.assertEqual(data["taskbar_state"], 0)
            self.assertEqual(data["taskbars"], [11])
            self.stack.append(("state", state))
        self.user.ShowWindow.side_effect = lambda hwnd, mode: self.stack.append(("show", hwnd, mode))
        with patch.object(native, "get_taskbar_state", return_value=0), patch.object(native, "set_taskbar_state", side_effect=set_state):
            self.recovery.hide_bars()
        self.assertEqual(self.stack, [("state", 1), ("show", 11, 0)])

    def test_repeated_hide_does_not_capture_our_own_modified_state(self):
        with patch.object(native, "get_taskbar_state", side_effect=[0, 1]) as get, patch.object(native, "set_taskbar_state") as set:
            self.recovery.hide_bars(); self.recovery.hide_bars()
        get.assert_called_once(); set.assert_called_once_with(1)
        self.assertEqual(self.recovery.taskbar_state, 0)

    def test_restores_visibility_then_original_state_and_clears_undo(self):
        self.recovery.bars, self.recovery.taskbar_state, self.recovery.bars_active = [11], 2, True
        self.user.ShowWindow.side_effect = lambda hwnd, mode: self.stack.append(("show", hwnd, mode))
        with patch.object(native, "set_taskbar_state", side_effect=lambda state: self.stack.append(("state", state))):
            self.recovery.restore_bars()
        self.assertEqual(self.stack, [("show", 11, 5), ("state", 2)])
        data = json.loads(self.path.read_text())
        self.assertEqual(data["taskbars"], []); self.assertIsNone(data["taskbar_state"])
        self.assertFalse(self.recovery.bars_active)

    def test_preserves_an_existing_auto_hide_preference(self):
        with patch.object(native, "get_taskbar_state", return_value=1), patch.object(native, "set_taskbar_state") as set:
            self.recovery.hide_bars(); self.recovery.restore_bars()
        set.assert_not_called()

    def test_old_recovery_file_does_not_change_shell_settings(self):
        with patch.object(native, "set_taskbar_state") as set:
            native.restore_taskbar_snapshot({"taskbars": [11]})
        self.user.ShowWindow.assert_called_once_with(11, 5); set.assert_not_called()

    def test_shell_failure_rolls_back_from_saved_snapshot(self):
        with patch.object(native, "get_taskbar_state", return_value=0), patch.object(native, "set_taskbar_state", side_effect=[OSError("failed"), None]) as set:
            with self.assertRaises(OSError): self.recovery.hide_bars()
        self.assertEqual([call.args[0] for call in set.call_args_list], [1, 0])
        self.user.ShowWindow.assert_called_once_with(11, 5)
        self.assertIsNone(self.recovery.taskbar_state)

    def test_guard_restores_shell_state_and_windows_using_the_same_snapshot(self):
        self.path.write_text(json.dumps({"windows": [], "taskbars": [11], "taskbar_state": 0}))
        import psutil
        with patch.object(native.psutil, "Process", side_effect=psutil.NoSuchProcess(999)), patch.object(native, "set_taskbar_state") as set:
            native.watchdog(999, 123., str(self.path))
        set.assert_called_once_with(0)
        self.user.ShowWindow.assert_called_once_with(11, 5)
        self.assertFalse(self.path.exists())

    def test_fallback_releases_only_taskbar_edge_and_preserves_dock(self):
        info = native.MonitorInfo()
        info.monitor = native.W.RECT(0, 0, 1920, 1200)
        info.work = native.W.RECT(72, 30, 1920, 1077)
        snapshot = {"hwnd": 11, "monitor": [0, 0, 1920, 1200], "before": [72, 30, 1920, 1200], "edge": 0}
        with patch.object(native, "monitor_info", return_value=info), patch.object(native, "set_workarea") as set_area:
            native.update_workarea(snapshot)
        set_area.assert_called_once_with([0, 30, 1920, 1077])

    def test_fallback_handles_dock_on_same_edge_without_double_reservation(self):
        for edge, before, current, expected in (
            (0, [72, 0, 1920, 1200], [195, 0, 1920, 1200], [123, 0, 1920, 1200]),
            (1, [0, 72, 1920, 1200], [0, 195, 1920, 1200], [0, 123, 1920, 1200]),
            (2, [0, 0, 1848, 1200], [0, 0, 1725, 1200], [0, 0, 1797, 1200]),
            (3, [0, 0, 1920, 1128], [0, 0, 1920, 1005], [0, 0, 1920, 1077]),
        ):
            with self.subTest(edge=edge):
                info = native.MonitorInfo(); info.monitor = native.W.RECT(0, 0, 1920, 1200); info.work = native.W.RECT(*current)
                reservation = MagicMock(); reservation.data.edge = edge; reservation.thickness = 123
                snapshot = {"hwnd": 11, "monitor": [0, 0, 1920, 1200], "before": before, "edge": edge}
                with patch.object(native, "monitor_info", return_value=info), patch.object(native, "set_workarea") as set_area:
                    native.update_workarea(snapshot, reservation=reservation)
                set_area.assert_called_once_with(expected)

    def test_restore_preserves_other_edges_and_does_not_overwrite_new_toolbar(self):
        info = native.MonitorInfo(); info.monitor = native.W.RECT(0, 0, 1920, 1200)
        snapshot = {"hwnd": 11, "monitor": [0, 0, 1920, 1200], "before": [72, 0, 1920, 1200], "edge": 0}
        with patch.object(native, "monitor_info", return_value=info), patch.object(native, "set_workarea") as set_area:
            info.work = native.W.RECT(0, 30, 1920, 1077)
            native.restore_workarea(snapshot)
            set_area.assert_called_once_with([72, 30, 1920, 1077])
            set_area.reset_mock(); info.work.left = 100
            native.restore_workarea(snapshot)
            set_area.assert_not_called()

    def test_existing_maximized_window_fits_new_area_without_losing_its_frame(self):
        self.assertEqual(native.adjusted_maximized_rect([61, -11, 1931, 1076],
                         [72, 0, 1920, 1065], [0, 0, 1920, 1100]), [-11, -11, 1931, 1111])

    def test_custom_or_fullscreen_geometry_is_not_forced_into_workarea(self):
        self.assertIsNone(native.adjusted_maximized_rect([0, 0, 1920, 1200],
                          [72, 0, 1920, 1200], [0, 0, 1920, 1100]))
        self.assertIsNone(native.adjusted_maximized_rect([200, 100, 1000, 800],
                          [0, 0, 1920, 1200], [0, 0, 1920, 1100]))
