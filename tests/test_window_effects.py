from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import native
from window_effects import BottomCorners, frame_target, restore_corners


class WindowEffectTests(unittest.TestCase):
    def test_failed_restore_keeps_undo_for_guard_and_manual_recovery(self):
        undo = {"hwnd": 7, "pid": 10, "created": 100., "corner_hash": "ours"}
        recovery = SimpleNamespace(corner_records=[undo], persist=MagicMock())
        with patch("window_effects.restore_corners", return_value=[undo]):
            BottomCorners(recovery).clear()
        self.assertEqual(recovery.corner_records, [undo]); recovery.persist.assert_called_once()

    def test_stale_maximized_frame_uses_actual_borders_instead_of_old_workarea(self):
        self.assertEqual(frame_target([-11, -11, 1931, 1027], [0, 0, 1920, 1016],
                                    [0, 42, 1920, 1100]), [-11, 31, 1931, 1111])

    def test_invalid_frame_geometry_is_not_repositioned(self):
        self.assertIsNone(frame_target([0, 0, 1920, 1200], [100, 0, 1920, 1200], [0, 42, 1920, 1100]))

    def test_changed_application_region_is_never_removed_on_restore(self):
        user = MagicMock(); record = {"hwnd": 7, "pid": 10, "created": 100., "corner_hash": "ours"}
        with patch.object(native, "IS_WINDOWS", True), patch.object(native, "user", user, create=True), \
             patch("window_effects._api"), patch.object(native, "alive", return_value=True), \
             patch("window_effects.region_state", return_value=("apps-new-region", None)):
            restore_corners([record])
        user.SetWindowRgn.assert_not_called()

    def test_region_undo_is_persisted_before_application(self):
        record = {"hwnd": 7, "pid": 10, "created": 100.}
        recovery = SimpleNamespace(corner_records=[])
        recovery.persist = MagicMock()
        user = MagicMock(); user.GetDpiForWindow.return_value = 144
        def apply(hwnd, region, redraw):
            recovery.persist.assert_called_once()
            self.assertEqual(recovery.corner_records[0]["corner_hash"], "ours")
            return 1
        user.SetWindowRgn.side_effect = apply
        gdi = MagicMock(); gdi.CreateRoundRectRgn.return_value = 101; gdi.CreateRectRgn.return_value = 102
        with patch.object(native, "IS_WINDOWS", True), patch.object(native, "user", user, create=True), \
             patch("window_effects._api", return_value=gdi), patch("window_effects._digest", return_value="ours"), \
             patch("window_effects.region_state", return_value=(None, None)), \
             patch("window_effects._geometry", return_value=([0, 42, 1920, 1100], [0, 42, 1920, 1100], [0, 42, 1920, 1100])):
            BottomCorners(recovery).sync([record], True)
        user.SetWindowRgn.assert_called_once_with(7, 101, True)

    def test_failed_undo_write_does_not_modify_window(self):
        recovery = SimpleNamespace(corner_records=[], persist=MagicMock(side_effect=OSError("disk full")))
        user = MagicMock(); user.GetDpiForWindow.return_value = 144
        gdi = MagicMock(); gdi.CreateRoundRectRgn.return_value = 101; gdi.CreateRectRgn.return_value = 102
        with patch.object(native, "IS_WINDOWS", True), patch.object(native, "user", user, create=True), \
             patch("window_effects._api", return_value=gdi), patch("window_effects._digest", return_value="ours"), \
             patch("window_effects.region_state", return_value=(None, None)), \
             patch("window_effects._geometry", return_value=([0, 42, 1920, 1100], [0, 42, 1920, 1100], [0, 42, 1920, 1100])):
            with self.assertRaises(OSError): BottomCorners(recovery).sync([{"hwnd": 7, "pid": 10, "created": 100.}], True)
        user.SetWindowRgn.assert_not_called(); self.assertEqual(recovery.corner_records, [])
