import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication

from core import Pomodoro, default_config
from island import Island, island_state


class IslandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.now = 100.
        self.config = default_config(); self.config.update(island_enabled=True, island_always_visible=True)
        timer = Pomodoro(lambda: self.now); timer.remaining = 300
        pomodoro = Pomodoro(lambda: self.now)
        self.engine = SimpleNamespace(timer=timer, pomodoro=pomodoro, options={})
        def reset(key):
            value = getattr(self.engine, key); value.reset()
            if key == "timer": value.remaining = 300
        self.engine.reset = reset
        self.dock = SimpleNamespace(config=self.config, engine=self.engine, chosen_screen=lambda: self.app.primaryScreen(), launch=Mock())
        self.island = Island(self.dock, test_mode=True); self.island._now = lambda: self.now
        self.addCleanup(self.island.shutdown)

    def test_quick_timer_pause_resume_preserves_remaining(self):
        self.island.start_timer(15)
        self.assertEqual(self.engine.timer.deadline, 1000.)
        self.now += 30; self.island.sync(); self.island.toggle_timer()
        self.assertEqual(self.engine.timer.remaining, 870)
        self.assertIsNone(self.engine.timer.deadline)
        self.assertFalse(self.island.current_state["running"])
        self.now += 50; self.island.toggle_timer()
        self.assertEqual(self.engine.timer.deadline, self.now + 870)
        self.island.reset_timer()
        self.assertEqual(self.island.current_state["kind"], "idle")

    def test_notification_temporarily_takes_priority_then_returns_to_timer(self):
        self.island.start_timer(5)
        self.island.notify("Download pronto", "Documento.pdf", seconds=6)
        self.assertEqual(self.island.current_state["kind"], "notice")
        self.now += 7; self.island.sync()
        self.assertEqual(self.island.current_state["kind"], "timer")
        self.assertEqual(self.island.current_state["remaining"], 293)
        self.assertIsNone(self.island._notice)

    def test_disabled_island_stays_hidden_even_for_notices_and_stops_ticker(self):
        self.config["island_enabled"] = False
        self.island.notify("Aviso", "Mensagem real")
        self.assertTrue(self.island.isHidden())
        self.assertFalse(self.island._ticker.isActive())

    def test_only_active_mode_hides_idle_but_reveals_running_focus(self):
        self.config["island_always_visible"] = False
        self.island.sync(); self.assertTrue(self.island.isHidden())
        self.engine.pomodoro.toggle(); self.island.sync()
        self.assertFalse(self.island.isHidden())
        self.assertEqual(self.island.current_state["kind"], "pomodoro")

    def test_local_file_actions_use_supplied_path_and_urls_are_not_actions(self):
        path = str(Path.home() / "arquivo.pdf")
        self.island.notify("Arquivo", "Pronto", path=path)
        self.island.open_notification(); self.dock.launch.assert_called_once_with(path)
        with patch("island.native.reveal") as reveal:
            self.island.reveal_notification(); reveal.assert_called_once_with(path)
        self.island.notify("Link", "Não deve executar URL", path="https://example.com")
        self.assertIsNone(self.island.current_state["path"])

    def test_idle_calendar_status_does_not_invent_events_and_shutdown_stops_timers(self):
        self.assertEqual(island_state(self.dock)["kind"], "idle")
        self.assertIn("calendário não conectado", self.island.idle_hint.text())
        self.island._collapse_timer.start(); self.island.shutdown()
        self.assertFalse(self.island._ticker.isActive())
        self.assertFalse(self.island._collapse_timer.isActive())
        self.island.sync(); self.assertTrue(self.island.isHidden())

    def test_media_uses_provider_and_only_enables_supported_controls(self):
        media = {"available": True, "title": "Faixa real", "artist": "Artista real", "playing": True,
                 "can_toggle": True, "can_next": False, "can_previous": True}
        provider = SimpleNamespace(snapshot=lambda: dict(media), control=Mock(return_value=True))
        self.dock.media = provider
        self.island.sync()
        self.assertEqual(self.island.current_state["kind"], "media")
        self.assertEqual(self.island.current_state["title"], "Faixa real")
        self.assertTrue(self.island.play_button.isEnabled())
        self.assertFalse(self.island.next_button.isEnabled())
        self.island.play_button.click(); provider.control.assert_called_once_with("play_pause")
        self.island.start_timer(5)
        self.assertEqual(self.island.current_state["kind"], "timer")
        self.island.notify("Aviso", "Prioridade temporária")
        self.assertEqual(self.island.current_state["kind"], "notice")

    def test_expired_engine_timer_does_not_reappear_as_a_new_paused_timer(self):
        self.island.start_timer(5)
        self.now += 301
        self.engine.timer.tick(); self.engine.reset("timer")
        self.island.sync()
        self.assertEqual(self.island.current_state["kind"], "idle")
