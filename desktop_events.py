"""Local desktop event sampling. File contents are never opened or uploaded."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import time

import native

_PARTIAL = (".part", ".partial", ".crdownload", ".download", ".tmp", ".temp")


def scan_files(roots):
    result = {}
    for family, directory in roots.items():
        found = {}
        try:
            with os.scandir(directory) as entries:
                for index, entry in enumerate(entries):
                    if index >= 4000: break
                    try:
                        if not entry.is_file(follow_symlinks=False) or entry.name.lower().endswith(_PARTIAL): continue
                        stat = entry.stat(follow_symlinks=False)
                        found[str(Path(entry.path).absolute())] = (stat.st_size, stat.st_mtime_ns)
                    except OSError:
                        continue
        except FileNotFoundError:
            found = {}
        except OSError:
            # A temporarily inaccessible folder must not reset its baseline.
            found = None
        result[family] = found
    return result


class FileArrivalTracker:
    def __init__(self):
        self.previous = {}; self.pending = {}

    def update(self, snapshot):
        events = []
        for family, files in snapshot.items():
            if files is None: continue
            if family not in self.previous:
                self.previous[family] = dict(files); continue
            previous = self.previous[family]
            for path, fingerprint in files.items():
                key = (family, path)
                if path not in previous:
                    self.pending[key] = fingerprint
                elif key in self.pending:
                    if fingerprint == self.pending[key]:
                        events.append({"title": "Download concluído" if family == "downloads" else "Captura salva",
                                       "text": Path(path).name, "path": path, "family": family})
                        del self.pending[key]
                    else: self.pending[key] = fingerprint
            for key in list(self.pending):
                if key[0] == family and key[1] not in files: del self.pending[key]
            self.previous[family] = dict(files)
        return events


class DesktopEvents:
    def __init__(self, roots=None, clock=time.monotonic):
        self.roots = roots if roots is not None else {key: native.known_folder(key) for key in ("downloads", "screenshots")}
        self.clock = clock; self.last_scan = -1e9; self.future = None
        self.tracker = FileArrivalTracker(); self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ntdock-events")
        self.last_battery = None; self.last_volume = None; self.closed = False

    def poll(self, config, battery=None, volume=None):
        if self.closed or not config.get("island_enabled", False): return []
        events = []
        if self.future is not None and self.future.done():
            try:
                events.extend(event for event in self.tracker.update(self.future.result())
                              if config.get("island_" + event["family"], True))
            except Exception:
                pass
            self.future = None
        if self.future is None and self.clock() - self.last_scan >= 2:
            self.last_scan = self.clock(); self.future = self.pool.submit(scan_files, self.roots)
        if battery is not None:
            current = (bool(battery.power_plugged), int(battery.percent))
            if self.last_battery is not None and config.get("island_battery", True):
                plugged, percent = current; old_plugged, old_percent = self.last_battery
                if plugged != old_plugged:
                    events.append({"title": "Energia", "text": "Carregador conectado" if plugged else "Usando a bateria"})
                crossed = [level for level in (5, 10, 20) if old_percent > level >= percent]
                if not plugged and crossed:
                    events.append({"title": "Bateria fraca", "text": f"{percent}% de carga"})
            self.last_battery = current
        if volume is not None:
            current = round(volume)
            if self.last_volume is not None and current != self.last_volume and config.get("island_volume", True):
                events.append({"title": "Volume", "text": f"{current}%"})
            self.last_volume = current
        return events

    def shutdown(self):
        self.closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)
