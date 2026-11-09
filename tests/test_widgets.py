import json
from pathlib import Path
import tempfile
import time
import unittest

from datetime import datetime, timedelta
from widgets import CATALOG, WidgetEngine, claude_tokens


class WidgetTests(unittest.TestCase):
    def setUp(self):
        self.engine = WidgetEngine(); self.addCleanup(self.engine.close)

    def test_every_builtin_returns_display_text_offline(self):
        self.assertGreaterEqual(len(CATALOG), 40)
        for key in CATALOG:
            with self.subTest(widget=key): self.assertIsInstance(self.engine.value(key), str)
        self.assertFalse(self.engine.pending)

    def test_slow_metrics_do_not_block_timer_updates_or_queue_duplicate_work(self):
        from threading import Event
        from unittest.mock import patch
        entered, release = Event(), Event()
        def slow_metrics(options):
            entered.set(); release.wait(2)
        with patch.object(WidgetEngine, "_collect_local", side_effect=slow_metrics):
            engine = WidgetEngine()
            try:
                self.assertTrue(entered.wait(1))
                job = engine.metrics_future
                self.assertFalse(job.done())
                engine.timer.deadline = engine.timer.clock() - 1
                _, completed = engine.sample()
                self.assertTrue(completed)
                self.assertIs(engine.metrics_future, job)
                self.assertFalse(job.done())
            finally:
                release.set(); engine.close()

    def test_remote_failures_are_collected_and_throttled(self):
        self.engine.options["online"] = True
        def failing(): raise OSError("offline")
        self.engine.request("sample", failing, 100)
        future = self.engine.pending["sample"]
        try: future.result(timeout=1)
        except OSError: pass
        self.engine.sample()
        self.assertIn("sample", self.engine.errors)
        self.engine.request("sample", lambda: 123, 100)
        self.assertNotIn("sample", self.engine.pending)

    def test_remote_success_is_visible_after_sampling(self):
        self.engine.options["online"] = True
        self.engine.request("test", lambda: {"result": "OK"}, 10)
        self.engine.pending["test"].result(timeout=1); self.engine.sample()
        self.assertEqual(self.engine.remote["test"], {"result": "OK"})

    def test_custom_widgets_ignore_bad_json_and_unsafe_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "note.json").write_text(json.dumps({"type": "text", "title": "Minha nota", "value": "OK"}))
            (root / "bad.json").write_text("invalid")
            (root / "unsafe.json").write_text(json.dumps({"type": "url", "title": "Bad", "value": "javascript://alert(1)"}))
            self.engine.load_custom(root)
            self.assertEqual(list(self.engine.custom), ["custom:note"])
            self.assertEqual(self.engine.value("custom:note"), "OK")

    def test_user_selected_usage_file_is_parsed_without_network(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.json"; path.write_text('{"tokens_today":12000}')
            self.engine.options["claude_usage_file"] = str(path)
            self.engine.value("claude"); self.engine.pending["claude"].result(timeout=1); self.engine.sample()
            self.assertIn("12,000", self.engine.value("claude")); self.assertFalse(self.engine.pending)

    def test_local_claude_deduplicates_streaming_usage_and_filters_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.jsonl"
            now = datetime.now().astimezone()
            def entry(ident, tokens, timestamp=now):
                return {"type": "assistant", "timestamp": timestamp.isoformat(), "message": {"id": ident, "usage": {"input_tokens": 10, "output_tokens": tokens, "cache_read_input_tokens": 3}}}
            path.write_text("\n".join(json.dumps(item) for item in [entry("a", 1), entry("a", 5), entry("b", 9, now-timedelta(days=1)), entry("c", 2)]))
            self.assertEqual(claude_tokens(directory), 18 + 15)

    def test_hydration_and_stopwatch_reset(self):
        self.engine.click("hydration"); self.assertEqual(self.engine.cups, 1)
        self.engine.reset("hydration"); self.assertEqual(self.engine.cups, 0)
        self.engine.click("stopwatch"); self.assertIsNotNone(self.engine.stop_started)
        self.engine.reset("stopwatch"); self.assertIsNone(self.engine.stop_started)
