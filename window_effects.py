"""Fit maximized windows and apply reversible bottom-only corner clipping."""
import ctypes as C
import hashlib
import native as n


def frame_target(bounds, visible, work):
    margins = [visible[0] - bounds[0], visible[1] - bounds[1], bounds[2] - visible[2], bounds[3] - visible[3]]
    if any(value < 0 or value > 64 for value in margins): return None
    if visible[2] <= visible[0] or visible[3] <= visible[1]: return None
    return [work[0] - margins[0], work[1] - margins[1], work[2] + margins[2], work[3] + margins[3]]


def _geometry(record, applied=None):
    if not n.IS_WINDOWS or not n.alive(record): return None
    hwnd = record["hwnd"]
    n.user.IsZoomed.argtypes = [n.W.HWND]; n.user.IsZoomed.restype = n.W.BOOL
    if not n.user.IsWindowVisible(hwnd) or not n.user.IsZoomed(hwnd): return None
    if not n.user.GetWindowLongW(hwnd, -16) & 0x40000: return None
    if n.user.GetWindowLongW(hwnd, -20) & 0x400000: return None  # RTL regions have a different origin.
    n.user.GetWindowRect.argtypes = [n.W.HWND, C.POINTER(n.W.RECT)]
    bounds, visible = n.W.RECT(), n.W.RECT()
    if not n.user.GetWindowRect(hwnd, C.byref(bounds)): return None
    if n.dwm.DwmGetWindowAttribute(hwnd, 9, C.byref(visible), C.sizeof(visible)) != 0: return None
    info = n.monitor_info(hwnd)
    if info is None: return None
    outer, frame, work = n.rect_values(bounds), n.rect_values(visible), n.rect_values(info.work)
    # ApplicationFrameHost sometimes includes the invisible maximized top border
    # in its DWM bounds after SetWindowPos. Do not chase that border every tick.
    if frame[1] == outer[1] and outer[1] < work[1] and n.user.GetWindowLongW(hwnd, -16) & 0xC00000:
        n.user.GetDpiForWindow.argtypes = [n.W.HWND]; n.user.GetDpiForWindow.restype = n.W.UINT
        n.user.GetSystemMetricsForDpi.argtypes = [C.c_int, n.W.UINT]
        dpi = n.user.GetDpiForWindow(hwnd) or 96
        border = n.user.GetSystemMetricsForDpi(33, dpi) + n.user.GetSystemMetricsForDpi(92, dpi)
        if abs(work[1] - outer[1] - border) <= 1: frame[1] = work[1]
    if applied is not None and all(applied.get(key) == record.get(key) for key in ("pid", "created")) and region_state(hwnd)[0] == applied.get("corner_hash"):
        margins = applied.get("frame_margins", [])
        if len(margins) == 4 and all(type(value) is int and 0 <= value <= 64 for value in margins):
            frame = [outer[0] + margins[0], outer[1] + margins[1], outer[2] - margins[2], outer[3] - margins[3]]
    if frame == n.rect_values(info.monitor) and frame != work and not n.user.GetWindowLongW(hwnd, -16) & 0xC00000:
        return None  # Borderless full screen must stay full screen.
    return outer, frame, work


def fit_maximized(records, corner_records=()):
    """Use DWM frame margins, even when an app ignored an earlier work-area change."""
    if not n.IS_WINDOWS: return
    n.user.SetWindowPos.argtypes = [n.W.HWND, n.W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, n.W.UINT]
    corners = {record["hwnd"]: record for record in corner_records}
    for record in records:
        geometry = _geometry(record, corners.get(record["hwnd"]))
        if geometry is None: continue
        outer, visible, work = geometry
        target = frame_target(outer, visible, work)
        if target is not None and any(abs(a - b) > 1 for a, b in zip(outer, target)):
            left, top, right, bottom = target
            n.user.SetWindowPos(record["hwnd"], None, left, top, right - left, bottom - top, 0x4014)


_gdi = None


def _api():
    global _gdi
    if _gdi is None:
        _gdi = C.WinDLL("gdi32", use_last_error=True)
        for name, args, result in (
            ("CreateRectRgn", [C.c_int] * 4, n.W.HANDLE),
            ("CreateRoundRectRgn", [C.c_int] * 6, n.W.HANDLE),
            ("CombineRgn", [n.W.HANDLE] * 3 + [C.c_int], C.c_int),
            ("GetRgnBox", [n.W.HANDLE, C.POINTER(n.W.RECT)], C.c_int),
            ("GetRegionData", [n.W.HANDLE, n.W.DWORD, C.c_void_p], n.W.DWORD),
            ("DeleteObject", [n.W.HANDLE], n.W.BOOL),
        ):
            function = getattr(_gdi, name); function.argtypes = args; function.restype = result
        n.user.GetWindowRgn.argtypes = [n.W.HWND, n.W.HANDLE]
        n.user.SetWindowRgn.argtypes = [n.W.HWND, n.W.HANDLE, n.W.BOOL]
        n.user.SetWindowRgn.restype = C.c_int
    return _gdi


def _digest(region):
    gdi = _api(); size = gdi.GetRegionData(region, 0, None)
    if not 0 < size <= 65536: return None
    buffer = C.create_string_buffer(size)
    if not gdi.GetRegionData(region, size, buffer): return None
    return hashlib.sha256(buffer.raw).hexdigest()


def region_state(hwnd):
    gdi = _api(); region = gdi.CreateRectRgn(0, 0, 0, 0)
    if not region: return None, None
    try:
        C.set_last_error(0); kind = n.user.GetWindowRgn(hwnd, region)
        if kind == 0: return (None, None) if not C.get_last_error() else ("unavailable", None)
        box = n.W.RECT(); gdi.GetRgnBox(region, C.byref(box))
        return _digest(region), n.rect_values(box) if kind == 2 else None
    finally: gdi.DeleteObject(region)


def restore_corners(records):
    if not n.IS_WINDOWS or not records: return []
    gdi = _api()
    pending = []
    for record in records:
        if not n.alive(record): continue
        digest, _ = region_state(record["hwnd"])
        if digest != record.get("corner_hash"): continue  # Never replace a region now owned by the app.
        region = None
        if record.get("original_full_rect"):
            rect = n.W.RECT()
            n.user.GetWindowRect.argtypes = [n.W.HWND, C.POINTER(n.W.RECT)]
            if not n.user.GetWindowRect(record["hwnd"], C.byref(rect)):
                pending.append(record); continue
            region = gdi.CreateRectRgn(0, 0, rect.right - rect.left, rect.bottom - rect.top)
            if not region:
                pending.append(record); continue
        if not n.user.SetWindowRgn(record["hwnd"], region, True):
            if region: gdi.DeleteObject(region)
            pending.append(record)
    return pending


class BottomCorners:
    def __init__(self, recovery):
        self.recovery = recovery; self.signatures = {}

    def clear(self):
        pending = restore_corners(self.recovery.corner_records)
        self.recovery.corner_records[:] = pending
        self.signatures.clear(); self.recovery.persist()

    def sync(self, records, enabled):
        if not n.IS_WINDOWS: return
        if not enabled:
            if self.recovery.corner_records: self.clear()
            return
        active = {record["hwnd"]: record for record in records}
        for previous in list(self.recovery.corner_records):
            current = active.get(previous["hwnd"])
            geometry = _geometry(previous, previous) if current is not None else None
            if geometry is None or self.signatures.get(previous["hwnd"]) != geometry[:2] or region_state(previous["hwnd"])[0] != previous.get("corner_hash"):
                if restore_corners([previous]): continue
                self.recovery.corner_records.remove(previous)
                self.signatures.pop(previous["hwnd"], None); self.recovery.persist()
        gdi = _api()
        for record in records:
            hwnd = record["hwnd"]
            if hwnd in self.signatures: continue
            geometry = _geometry(record)
            if geometry is None: continue
            outer, visible, work = geometry
            if any(abs(a - b) > 1 for a, b in zip(visible, work)): continue
            digest, box = region_state(hwnd)
            width, height = outer[2] - outer[0], outer[3] - outer[1]
            full = box == [0, 0, width, height]
            if digest is not None and not full: continue  # Preserve custom-shaped app windows.
            left, top = visible[0] - outer[0], visible[1] - outer[1]
            right, bottom = visible[2] - outer[0], visible[3] - outer[1]
            n.user.GetDpiForWindow.argtypes = [n.W.HWND]; n.user.GetDpiForWindow.restype = n.W.UINT
            radius = max(8, round(10 * (n.user.GetDpiForWindow(hwnd) or 96) / 96))
            rounded = gdi.CreateRoundRectRgn(left, top, right + 1, bottom + 1, radius * 2, radius * 2)
            upper = gdi.CreateRectRgn(0, 0, width, bottom - radius)
            if not rounded or not upper:
                if rounded: gdi.DeleteObject(rounded)
                if upper: gdi.DeleteObject(upper)
                continue
            gdi.CombineRgn(rounded, rounded, upper, 2); gdi.DeleteObject(upper)
            own_hash = _digest(rounded)
            if own_hash is None: gdi.DeleteObject(rounded); continue
            undo = {key: record[key] for key in ("hwnd", "pid", "created")}
            undo.update(corner_hash=own_hash, original_full_rect=full,
                        frame_margins=[left, top, outer[2] - visible[2], outer[3] - visible[3]])
            self.recovery.corner_records.append(undo)
            try:
                self.recovery.persist()  # Persist undo before changing a foreign window.
            except Exception:
                self.recovery.corner_records.remove(undo); gdi.DeleteObject(rounded); raise
            if n.user.SetWindowRgn(hwnd, rounded, True): self.signatures[hwnd] = geometry[:2]
            else:
                gdi.DeleteObject(rounded); self.recovery.corner_records.remove(undo); self.recovery.persist()
