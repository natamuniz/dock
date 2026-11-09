from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from desktop_events import FileArrivalTracker, DesktopEvents, scan_files


class DesktopEventTests(unittest.TestCase):
    def test_existing_files_are_baseline_and_new_files_wait_for_completion(self):
        tracker = FileArrivalTracker()
        self.assertEqual(tracker.update({"downloads": {"old": (5, 1)}}), [])
        self.assertEqual(tracker.update({"downloads": {"old": (5, 1), "new": (2, 2)}}), [])
        self.assertEqual(tracker.update({"downloads": {"old": (5, 1), "new": (4, 3)}}), [])
        events = tracker.update({"downloads": {"old": (5, 1), "new": (4, 3)}})
        self.assertEqual([event["path"] for event in events], ["new"])
        self.assertEqual(tracker.update({"downloads": {"old": (5, 1), "new": (4, 3)}}), [])

    def test_unavailable_directory_does_not_reannounce_its_old_files(self):
        tracker = FileArrivalTracker(); tracker.update({"screenshots": {"old": (1, 1)}})
        self.assertEqual(tracker.update({"screenshots": None}), [])
        self.assertEqual(tracker.update({"screenshots": {"old": (1, 1)}}), [])

    def test_scanner_ignores_partial_downloads_and_only_reads_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / "unfinished.crdownload").write_bytes(b"a")
            (root / "done.txt").write_bytes(b"a")
            result = scan_files({"downloads": root})["downloads"]
            self.assertEqual([Path(path).name for path in result], ["done.txt"])
            self.assertEqual(scan_files({"screenshots": root / "missing"})["screenshots"], {})

    def test_battery_and_volume_changes_are_not_announced_on_first_sample(self):
        feed = DesktopEvents(roots={}); self.addCleanup(feed.shutdown)
        options = {"island_enabled": True}
        self.assertEqual(feed.poll(options, SimpleNamespace(power_plugged=True, percent=25), 50), [])
        events = feed.poll(options, SimpleNamespace(power_plugged=False, percent=19), 60)
        self.assertEqual([event["title"] for event in events], ["Energia", "Bateria fraca", "Volume"])
        self.assertEqual(feed.poll(options, SimpleNamespace(power_plugged=False, percent=19), 60), [])

    def test_disabled_island_and_shutdown_do_not_start_scans(self):
        feed = DesktopEvents(roots={}); self.addCleanup(feed.shutdown)
        self.assertEqual(feed.poll({}), []); self.assertIsNone(feed.future)
        feed.shutdown(); self.assertEqual(feed.poll({"island_enabled": True}), [])
