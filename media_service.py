"""Non-blocking Windows SMTC media and Core Audio endpoint integration.

Only reads Windows' current media session until a caller explicitly submits a
control. Imports and COM objects stay on a private worker, never on the Qt thread.
SMTC requires Windows 10 1809+ and optional PyWinRT projections. Volume uses the
documented IMMDeviceEnumerator / IAudioEndpointVolume interfaces via ctypes.
"""
from __future__ import annotations

import asyncio
import ctypes
import math
import queue
import sys
import threading
from uuid import UUID


def _empty_snapshot():
    return {"title": "", "artist": "", "playing": False, "available": False,
            "volume": None, "muted": None, "can_toggle": False,
            "can_next": False, "can_previous": False, "error": None}


class _CoreAudio:
    """COM pointers are created, used and released in one worker apartment."""
    def __init__(self):
        self.ole = ctypes.OleDLL("ole32")
        self.ole.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self.ole.CoInitializeEx.restype = ctypes.c_long
        self.initialized = False

    def start(self):
        result = self.ole.CoInitializeEx(None, 0)  # COINIT_MULTITHREADED
        if result < 0: raise OSError("COM apartment unavailable")
        self.initialized = True

    @staticmethod
    def _method(pointer, index, restype, *argtypes):
        vtable = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(vtable[index])

    @classmethod
    def _release(cls, pointer):
        if pointer.value: cls._method(pointer, 2, ctypes.c_ulong)(pointer)

    @staticmethod
    def _guid(value):
        return (ctypes.c_ubyte * 16).from_buffer_copy(UUID(value).bytes_le)

    def endpoint(self, operation, value=None):
        enumerator, device, endpoint = (ctypes.c_void_p() for _ in range(3))
        guid_type = ctypes.POINTER(ctypes.c_ubyte * 16)
        output = ctypes.POINTER(ctypes.c_void_p)
        self.ole.CoCreateInstance.argtypes = [guid_type, ctypes.c_void_p, ctypes.c_ulong, guid_type, output]
        self.ole.CoCreateInstance.restype = ctypes.c_long
        try:
            result = self.ole.CoCreateInstance(
                ctypes.byref(self._guid("BCDE0395-E52F-467C-8E3D-C4579291692E")), None, 1,
                ctypes.byref(self._guid("A95664D2-9614-4F35-A746-DE8DB63617E6")), ctypes.byref(enumerator))
            if result < 0: raise OSError("Audio enumerator unavailable")
            # IMMDeviceEnumerator::GetDefaultAudioEndpoint(eRender, eMultimedia)
            result = self._method(enumerator, 4, ctypes.c_long, ctypes.c_int, ctypes.c_int, output)(
                enumerator, 0, 1, ctypes.byref(device))
            if result < 0: raise OSError("No playback endpoint")
            result = self._method(device, 3, ctypes.c_long, guid_type, ctypes.c_ulong, ctypes.c_void_p, output)(
                device, ctypes.byref(self._guid("5CDF2C82-841E-4546-9722-0CF74078229A")), 1, None, ctypes.byref(endpoint))
            if result < 0: raise OSError("Endpoint volume unavailable")
            if operation == "read":
                volume, muted = ctypes.c_float(), ctypes.c_int()
                result = self._method(endpoint, 9, ctypes.c_long, ctypes.POINTER(ctypes.c_float))(endpoint, ctypes.byref(volume))
                if result < 0: raise OSError("Cannot read endpoint volume")
                result = self._method(endpoint, 15, ctypes.c_long, ctypes.POINTER(ctypes.c_int))(endpoint, ctypes.byref(muted))
                if result < 0: raise OSError("Cannot read endpoint mute")
                return {"volume": round(max(0., min(1., volume.value)) * 100), "muted": bool(muted.value)}
            if operation == "volume":
                result = self._method(endpoint, 7, ctypes.c_long, ctypes.c_float, ctypes.c_void_p)(endpoint, value / 100, None)
            else:
                result = self._method(endpoint, 14, ctypes.c_long, ctypes.c_int, ctypes.c_void_p)(endpoint, int(value), None)
            return result >= 0
        finally:
            for pointer in (endpoint, device, enumerator): self._release(pointer)

    def close(self):
        if self.initialized:
            self.ole.CoUninitialize(); self.initialized = False


class _WindowsMediaBackend:
    def __init__(self):
        self.manager = None
        self.manager_type = None
        self.playing_status = None
        self.audio = None
        self.projection_missing = False

    async def open(self):
        if sys.platform != "win32": return
        self.audio = _CoreAudio()
        self.audio.start()
        try:
            from winrt.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager,
                GlobalSystemMediaTransportControlsSessionPlaybackStatus,
            )
            self.manager_type = GlobalSystemMediaTransportControlsSessionManager
            self.playing_status = GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING
        except ImportError:
            self.projection_missing = True

    async def _manager(self):
        if self.manager is None and self.manager_type is not None:
            self.manager = await self.manager_type.request_async()
        return self.manager

    async def read(self):
        result = _empty_snapshot()
        if sys.platform != "win32":
            result["error"] = "Controles de mídia disponíveis no Windows."
            return result
        if self.audio is not None:
            try: result.update(self.audio.endpoint("read"))
            except OSError: pass  # A machine can legitimately have no audio endpoint.
        if self.projection_missing:
            result["error"] = "Integração de mídia não instalada."
            return result
        try:
            manager = await self._manager()
            session = manager.get_current_session() if manager is not None else None
            if session is None: return result
            properties = await session.try_get_media_properties_async()
            playback = session.get_playback_info()
            controls = playback.controls
            result.update(title=str(properties.title or ""), artist=str(properties.artist or ""),
                          available=True, playing=playback.playback_status == self.playing_status,
                          can_toggle=bool(controls.is_play_pause_toggle_enabled),
                          can_next=bool(controls.is_next_enabled), can_previous=bool(controls.is_previous_enabled))
        except Exception:
            self.manager = None
            result["error"] = "Não foi possível consultar a mídia do Windows."
        return result

    async def control(self, action, value=None):
        if action in ("volume", "volume_up", "volume_down", "mute"):
            if self.audio is None: return False
            if action == "volume": return self.audio.endpoint("volume", value)
            current = self.audio.endpoint("read")
            if action == "mute": return self.audio.endpoint("mute", not current["muted"])
            step = 5 if action == "volume_up" else -5
            return self.audio.endpoint("volume", max(0, min(100, current["volume"] + step)))
        manager = await self._manager()
        session = manager.get_current_session() if manager is not None else None
        if session is None: return False
        playback = session.get_playback_info()
        mapping = {"play_pause": ("is_play_pause_toggle_enabled", "try_toggle_play_pause_async"),
                   "next": ("is_next_enabled", "try_skip_next_async"),
                   "previous": ("is_previous_enabled", "try_skip_previous_async")}
        capability, method = mapping[action]
        if not getattr(playback.controls, capability): return False
        return bool(await getattr(session, method)())

    async def close(self):
        self.manager = None
        if self.audio is not None: self.audio.close(); self.audio = None


class MediaService:
    """Snapshot reads and command submission never wait for Windows APIs.

    control() / set_volume() return whether a command was queued, not whether
    another application accepted it. Poll snapshot() for the resulting state.
    An injected backend exposes async open/read/control/close for isolated tests.
    """
    def __init__(self, *, backend_factory=None, poll_interval=1., timeout=3.):
        self._backend_factory = backend_factory or _WindowsMediaBackend
        self._poll_interval = max(.05, float(poll_interval))
        self._timeout = max(.05, float(timeout))
        self._snapshot = _empty_snapshot()
        self._lock = threading.Lock()
        self._commands = queue.Queue(maxsize=32)
        self._thread = None
        self._loop = None
        self._task = None
        self._wake = None
        self._stopping = threading.Event()

    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive(): return
            self._stopping.clear()
            self._thread = threading.Thread(target=self._worker, name="ntdock-media", daemon=True)
            self._thread.start()

    def snapshot(self):
        with self._lock: return dict(self._snapshot)

    def _publish(self, value):
        state = _empty_snapshot(); state.update(value)
        state["title"] = str(state["title"] or "")[:500]
        state["artist"] = str(state["artist"] or "")[:500]
        with self._lock: self._snapshot = state

    def control(self, action):
        action = {"toggle": "play_pause", "playpause": "play_pause"}.get(action, action)
        if action not in ("play_pause", "next", "previous", "volume_up", "volume_down", "mute"):
            return False
        return self._enqueue(action)

    def set_volume(self, percent):
        if isinstance(percent, bool): return False
        try: percent = float(percent)
        except (ValueError, TypeError): return False
        if not math.isfinite(percent) or not 0 <= percent <= 100: return False
        return self._enqueue("volume", round(percent))

    def _enqueue(self, action, value=None):
        if self._stopping.is_set() or self._thread is None or not self._thread.is_alive(): return False
        try: self._commands.put_nowait((action, value))
        except queue.Full: return False
        loop, wake = self._loop, self._wake
        if loop is not None and wake is not None:
            try: loop.call_soon_threadsafe(wake.set)
            except RuntimeError: return False
        return True

    def _worker(self):
        asyncio.run(self._run())

    async def _run(self):
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.current_task()
        self._wake = asyncio.Event()
        backend = None
        try:
            backend = self._backend_factory()
            await asyncio.wait_for(backend.open(), self._timeout)
            while not self._stopping.is_set():
                command_error = None
                for _ in range(8):
                    try: action, value = self._commands.get_nowait()
                    except queue.Empty: break
                    try:
                        accepted = await asyncio.wait_for(backend.control(action, value), self._timeout)
                        if not accepted: command_error = "O aplicativo não aceitou este comando."
                    except Exception:
                        command_error = "Não foi possível executar o controle de mídia."
                try:
                    state = await asyncio.wait_for(backend.read(), self._timeout)
                    if command_error: state["error"] = command_error
                    self._publish(state)
                except Exception:
                    self._publish({"error": "Não foi possível atualizar a mídia do Windows."})
                self._wake.clear()
                if not self._commands.empty(): continue
                try: await asyncio.wait_for(self._wake.wait(), self._poll_interval)
                except asyncio.TimeoutError: pass
        except asyncio.CancelledError:
            pass
        except Exception:
            self._publish({"error": "Integração de mídia indisponível neste computador."})
        finally:
            if backend is not None:
                try: await asyncio.wait_for(backend.close(), 1.)
                except (Exception, asyncio.CancelledError): pass
            self._loop = self._task = self._wake = None

    def shutdown(self):
        self._stopping.set()
        loop, task = self._loop, self._task
        if loop is not None and task is not None:
            try: loop.call_soon_threadsafe(task.cancel)
            except RuntimeError: pass
        thread = self._thread
        if thread is not None and thread is not threading.current_thread(): thread.join(timeout=2.)
        while True:
            try: self._commands.get_nowait()
            except queue.Empty: break
        self._publish({})
