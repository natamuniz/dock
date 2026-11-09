import asyncio
import threading
import time
import unittest

from media_service import MediaService


class FakeBackend:
    def __init__(self):
        self.opened = False
        self.closed = False
        self.calls = []
        self.playing = False
        self.volume = 40
        self.read_error = False
        self.delay = 0

    async def open(self): self.opened = True

    async def read(self):
        await asyncio.sleep(self.delay)
        if self.read_error: raise OSError("private path or source details")
        return {"available": True, "title": "Faixa", "artist": "Artista", "playing": self.playing,
                "volume": self.volume, "can_toggle": True, "can_next": True, "can_previous": True}

    async def control(self, action, value=None):
        self.calls.append((action, value, threading.get_ident()))
        if action == "play_pause": self.playing = not self.playing
        if action == "volume": self.volume = value
        return True

    async def close(self): self.closed = True


class MediaServiceTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.service = MediaService(backend_factory=lambda: self.backend, poll_interval=.05, timeout=.1)
        self.addCleanup(self.service.shutdown)

    def wait_until(self, condition):
        deadline = time.monotonic() + 2
        while not condition() and time.monotonic() < deadline: time.sleep(.01)
        self.assertTrue(condition(), self.service.snapshot())

    def test_start_and_poll_only_read_and_snapshots_are_independent(self):
        self.service.start(); self.service.start()
        self.wait_until(lambda: self.service.snapshot()["available"])
        state = self.service.snapshot(); state["title"] = "Changed"
        self.assertEqual(self.service.snapshot()["title"], "Faixa")
        self.assertEqual(self.backend.calls, [])

    def test_controls_run_on_worker_only_after_explicit_submission(self):
        self.service.start(); self.wait_until(lambda: self.service.snapshot()["available"])
        self.assertTrue(self.service.control("play_pause"))
        self.wait_until(lambda: self.service.snapshot()["playing"])
        self.assertEqual(self.backend.calls[0][:2], ("play_pause", None))
        self.assertNotEqual(self.backend.calls[0][2], threading.get_ident())
        self.assertTrue(self.service.set_volume(68))
        self.wait_until(lambda: self.service.snapshot()["volume"] == 68)

    def test_invalid_commands_and_volume_never_reach_backend(self):
        self.service.start(); self.wait_until(lambda: self.backend.opened)
        self.assertFalse(self.service.control("launch"))
        for value in (-1, 101, float("nan"), float("inf"), True, None, "no"):
            self.assertFalse(self.service.set_volume(value))
        self.assertEqual(self.backend.calls, [])

    def test_failures_clear_stale_session_and_do_not_expose_exception_details(self):
        self.service.start(); self.wait_until(lambda: self.service.snapshot()["available"])
        self.backend.read_error = True
        self.wait_until(lambda: self.service.snapshot()["error"] is not None)
        self.assertFalse(self.service.snapshot()["available"])
        self.assertEqual(self.service.snapshot()["title"], "")
        self.assertNotIn("private", self.service.snapshot()["error"])
        self.backend.read_error = False
        self.wait_until(lambda: self.service.snapshot()["available"])
        self.assertIsNone(self.service.snapshot()["error"])

    def test_slow_backend_does_not_block_gui_and_shutdown_cancels_it(self):
        self.backend.delay = 20
        self.service.start(); self.wait_until(lambda: self.backend.opened)
        start = time.monotonic()
        self.assertFalse(self.service.snapshot()["available"])
        self.assertLess(time.monotonic() - start, .1)
        self.service.shutdown()
        self.assertTrue(self.backend.closed)
        self.assertFalse(self.service._thread.is_alive())
        self.assertFalse(self.service.control("next"))

    def test_missing_backend_is_graceful(self):
        self.service = MediaService(backend_factory=lambda: (_ for _ in ()).throw(ImportError("missing")))
        self.addCleanup(self.service.shutdown)
        self.service.start()
        self.wait_until(lambda: self.service.snapshot()["error"] is not None)
        self.assertFalse(self.service.snapshot()["available"])


if __name__ == "__main__": unittest.main()
