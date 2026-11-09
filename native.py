"""Windows integration via documented Win32/DWM APIs. No shell replacement."""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import sys

import psutil

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    user = C.WinDLL("user32", use_last_error=True)
    dwm = C.WinDLL("dwmapi", use_last_error=True)
    shell = C.WinDLL("shell32", use_last_error=True)
    for name, args, result in [
        ("GetForegroundWindow", [], W.HWND),
        ("GetWindow", [W.HWND, W.UINT], W.HWND),
        ("GetWindowLongW", [W.HWND, C.c_int], W.LONG),
        ("IsWindow", [W.HWND], W.BOOL),
        ("IsWindowVisible", [W.HWND], W.BOOL),
        ("IsIconic", [W.HWND], W.BOOL),
        ("GetWindowTextLengthW", [W.HWND], C.c_int),
        ("GetWindowTextW", [W.HWND, W.LPWSTR, C.c_int], C.c_int),
        ("GetClassNameW", [W.HWND, W.LPWSTR, C.c_int], C.c_int),
        ("GetWindowThreadProcessId", [W.HWND, C.POINTER(W.DWORD)], W.DWORD),
        ("ShowWindow", [W.HWND, C.c_int], W.BOOL),
        ("ShowWindowAsync", [W.HWND, C.c_int], W.BOOL),
        ("SetForegroundWindow", [W.HWND], W.BOOL),
        ("PostMessageW", [W.HWND, W.UINT, W.WPARAM, W.LPARAM], W.BOOL),
        ("FindWindowW", [W.LPCWSTR, W.LPCWSTR], W.HWND),
        ("RegisterHotKey", [W.HWND, C.c_int, W.UINT, W.UINT], W.BOOL),
        ("UnregisterHotKey", [W.HWND, C.c_int], W.BOOL),
        ("MonitorFromWindow", [W.HWND, W.DWORD], W.HANDLE),
    ]:
        function = getattr(user, name)
        function.argtypes, function.restype = args, result
    ENUMPROC = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    user.EnumWindows.argtypes = [ENUMPROC, W.LPARAM]
    user.EnumWindows.restype = W.BOOL
    dwm.DwmGetWindowAttribute.argtypes = [W.HWND, W.DWORD, C.c_void_p, W.DWORD]
    dwm.DwmRegisterThumbnail.argtypes = [W.HWND, W.HWND, C.POINTER(W.HANDLE)]
    dwm.DwmRegisterThumbnail.restype = W.LONG
    dwm.DwmUnregisterThumbnail.argtypes = [W.HANDLE]
    dwm.DwmSetWindowAttribute.argtypes = [W.HWND, W.DWORD, C.c_void_p, W.DWORD]
    shell.SHAppBarMessage.argtypes = [W.DWORD, C.c_void_p]
    shell.SHAppBarMessage.restype = C.c_size_t


def windows():
    if not IS_WINDOWS:
        return []
    found = []
    @ENUMPROC
    def visit(hwnd, _):
        try:
            if not user.IsWindowVisible(hwnd) or user.GetWindow(hwnd, 4):
                return True
            if user.GetWindowLongW(hwnd, -20) & 0x80:
                return True
            title = C.create_unicode_buffer(512)
            user.GetWindowTextW(hwnd, title, len(title))
            if not title.value:
                return True
            cloaked = W.DWORD()
            dwm.DwmGetWindowAttribute(hwnd, 14, C.byref(cloaked), C.sizeof(cloaked))
            if cloaked.value:
                return True
            pid = W.DWORD()
            user.GetWindowThreadProcessId(hwnd, C.byref(pid))
            if pid.value == os.getpid():
                return True
            process = psutil.Process(pid.value)
            found.append({"hwnd": int(hwnd), "pid": pid.value,
                          "created": process.create_time(), "exe": process.exe(),
                          "title": title.value, "minimized": bool(user.IsIconic(hwnd))})
        except (OSError, psutil.Error):
            pass
        return True
    user.EnumWindows(visit, 0)
    return found


def alive(record):
    if not IS_WINDOWS or not user.IsWindow(record["hwnd"]):
        return False
    pid = W.DWORD()
    user.GetWindowThreadProcessId(record["hwnd"], C.byref(pid))
    try:
        return pid.value == record["pid"] and abs(psutil.Process(pid.value).create_time() - record["created"]) < .01
    except psutil.Error:
        return False


def activate(record, toggle=True):
    if not alive(record):
        return
    hwnd = record["hwnd"]
    if toggle and user.GetForegroundWindow() == hwnd:
        user.ShowWindowAsync(hwnd, 6)
    else:
        user.ShowWindowAsync(hwnd, 9 if user.IsIconic(hwnd) else 5)
        user.SetForegroundWindow(hwnd)


def close_window(record):
    if alive(record):
        user.PostMessageW(record["hwnd"], 0x10, 0, 0)


def window_icon(record):
    """Borrow a window icon; caller must copy it and must not destroy it."""
    if not alive(record): return 0
    user.SendMessageTimeoutW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM, W.UINT, W.UINT, C.POINTER(C.c_size_t)]
    user.SendMessageTimeoutW.restype = W.LPARAM
    for kind in (1, 2, 0):
        result = C.c_size_t()
        if user.SendMessageTimeoutW(record["hwnd"], 0x7F, kind, 0, 2, 40, C.byref(result)) and result.value:
            return result.value
    get_class_icon = getattr(user, "GetClassLongPtrW", user.GetClassLongW)
    get_class_icon.argtypes = [W.HWND, C.c_int]; get_class_icon.restype = C.c_size_t
    return get_class_icon(record["hwnd"], -14) or get_class_icon(record["hwnd"], -34)


def recycle_icon():
    """Return an owned stock Recycle Bin HICON, released with release_icon."""
    if not IS_WINDOWS: return 0
    class StockIconInfo(C.Structure):
        _fields_ = [("size", W.DWORD), ("icon", W.HICON), ("image_index", C.c_int),
                    ("icon_index", C.c_int), ("path", W.WCHAR * 260)]
    data = StockIconInfo(); data.size = C.sizeof(data)
    shell.SHGetStockIconInfo.argtypes = [C.c_int, W.UINT, C.POINTER(StockIconInfo)]
    shell.SHGetStockIconInfo.restype = W.LONG
    return data.icon if shell.SHGetStockIconInfo(31, 0x100, C.byref(data)) == 0 else 0


def release_icon(handle):
    if IS_WINDOWS and handle:
        user.DestroyIcon.argtypes = [W.HICON]; user.DestroyIcon(handle)


def taskbars():
    if not IS_WINDOWS:
        return []
    found = []
    @ENUMPROC
    def visit(hwnd, _):
        name = C.create_unicode_buffer(128)
        user.GetClassNameW(hwnd, name, len(name))
        if name.value in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            found.append(int(hwnd))
        return True
    user.EnumWindows(visit, 0)
    return found


def set_taskbars(visible):
    if IS_WINDOWS:
        for hwnd in taskbars():
            user.ShowWindow(hwnd, 5 if visible else 0)


def start_menu():
    if IS_WINDOWS:
        # Ctrl+Escape is the documented keyboard shortcut for Start.
        user.keybd_event(0x11, 0, 0, 0)
        user.keybd_event(0x1B, 0, 0, 0)
        user.keybd_event(0x1B, 0, 2, 0)
        user.keybd_event(0x11, 0, 2, 0)


def open_system_panel(kind):
    """Open Windows controls through shell URIs, without synthesizing hotkeys."""
    if not IS_WINDOWS: return False
    if kind == "tray":
        hwnd = user.FindWindowW("NotifyIconOverflowWindow", None)
        if hwnd:
            user.ShowWindow(hwnd, 5); user.SetForegroundWindow(hwnd)
            return True
    uri = {"quick_settings": "ms-settings:controlcenter", "notifications": "ms-settings:notifications",
           "tray": "ms-settings:taskbar", "sound": "ms-settings:sound"}.get(kind)
    if uri is None: return False
    try:
        os.startfile(uri); return True
    except OSError:
        return False


def known_folder(kind):
    defaults = {"downloads": Path.home() / "Downloads", "screenshots": Path.home() / "Pictures" / "Screenshots"}
    if kind not in defaults: raise ValueError("Pasta conhecida inválida.")
    if IS_WINDOWS:
        from comtypes import GUID
        ids = {"downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
               "screenshots": "{B7BEDE81-DF94-4682-A7D8-57A52620B86F}"}
        folder = W.LPWSTR()
        shell.SHGetKnownFolderPath.argtypes = [C.POINTER(GUID), W.DWORD, W.HANDLE, C.POINTER(W.LPWSTR)]
        shell.SHGetKnownFolderPath.restype = W.LONG
        if shell.SHGetKnownFolderPath(C.byref(GUID(ids[kind])), 0x4000, None, C.byref(folder)) == 0:
            try: return Path(folder.value)
            finally:
                ole = C.WinDLL("ole32")
                ole.CoTaskMemFree.argtypes = [C.c_void_p]; ole.CoTaskMemFree.restype = None
                ole.CoTaskMemFree(C.cast(folder, C.c_void_p))
    return defaults[kind]


def reveal(target):
    target = os.path.expandvars(os.path.expanduser(target))
    if IS_WINDOWS:
        subprocess.Popen(["explorer.exe", "/select,", target])


def resolved_exe(target):
    target = os.path.expandvars(os.path.expanduser(target))
    if IS_WINDOWS and target.lower().endswith(".lnk"):
        try:
            from comtypes.client import CreateObject
            target = CreateObject("WScript.Shell", dynamic=True).CreateShortcut(target).TargetPath
        except Exception:
            pass
    return os.path.normcase(os.path.abspath(target))


def set_autostart(enabled):
    if not IS_WINDOWS:
        raise OSError("A inicialização automática está disponível no Windows.")
    import winreg
    command = [sys.executable]
    if not getattr(sys, "frozen", False):
        executable = Path(sys.executable).with_name("pythonw.exe")
        command = [str(executable if executable.exists() else sys.executable), str(Path(__file__).with_name("app.py"))]
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        if enabled:
            winreg.SetValueEx(key, "NTDock", 0, winreg.REG_SZ, subprocess.list2cmdline(command))
        else:
            try:
                winreg.DeleteValue(key, "NTDock")
            except FileNotFoundError:
                pass


def autostart_enabled():
    if not IS_WINDOWS:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            return bool(winreg.QueryValueEx(key, "NTDock")[0])
    except OSError:
        return False


class ThumbnailProperties(C.Structure):
    _fields_ = [("flags", W.DWORD), ("destination", W.RECT), ("source", W.RECT),
                ("opacity", W.BYTE), ("visible", W.BOOL), ("client_only", W.BOOL)]


class Thumbnail:
    def __init__(self, destination, source):
        self.handle = W.HANDLE()
        self.valid = IS_WINDOWS and dwm.DwmRegisterThumbnail(destination, source, C.byref(self.handle)) == 0

    def update(self, x, y, width, height):
        if self.valid:
            props = ThumbnailProperties(0x1 | 0x4 | 0x8 | 0x10, W.RECT(x, y, x + width, y + height), W.RECT(), 255, True, True)
            dwm.DwmUpdateThumbnailProperties.argtypes = [W.HANDLE, C.POINTER(ThumbnailProperties)]
            dwm.DwmUpdateThumbnailProperties(self.handle, C.byref(props))

    def close(self):
        if self.valid:
            dwm.DwmUnregisterThumbnail(self.handle)
            self.valid = False


class AppBarData(C.Structure):
    _fields_ = [("size", W.DWORD), ("hwnd", W.HWND), ("callback", W.UINT),
                ("edge", W.UINT), ("rect", W.RECT), ("param", W.LPARAM)]


ABS_AUTOHIDE = 0x1


def get_taskbar_state():
    """ABM_GETSTATE returns shell flags, not window visibility."""
    if not IS_WINDOWS:
        return 0
    data = AppBarData()
    data.size = C.sizeof(data)
    return int(shell.SHAppBarMessage(0x4, C.byref(data))) & 0x3


def set_taskbar_state(state):
    """Let Explorer recalculate work areas using its public auto-hide API.

    Hiding Shell_TrayWnd alone does not release its reservation. Recovery also
    repairs a stale taskbar strip when Explorer ignores the auto-hide request.
    """
    if not IS_WINDOWS:
        return
    if type(state) is not int or not 0 <= state <= 3:
        raise ValueError("Estado da barra de tarefas inválido.")
    hwnd = user.FindWindowW("Shell_TrayWnd", None)
    if not hwnd:
        raise OSError("A barra de tarefas do Explorer não está disponível.")
    data = AppBarData()
    data.size, data.hwnd, data.param = C.sizeof(data), hwnd, state
    shell.SHAppBarMessage(0xA, C.byref(data))


def restore_taskbar_snapshot(data):
    """Shared by normal exit, crash recovery and the manual recovery script.

    Older recovery files have no taskbar_state and still restore visibility.
    Resolve the current primary taskbar in set_taskbar_state, since Explorer
    can restart and replace its original window handle.
    """
    if not IS_WINDOWS:
        return
    for hwnd in data.get("taskbars", []):
        if user.IsWindow(hwnd):
            user.ShowWindow(hwnd, 5)
    state = data.get("taskbar_state")
    if type(state) is int and 0 <= state <= 3:
        set_taskbar_state(state)
    for snapshot in data.get("workareas", []):
        restore_workarea(snapshot)


class MonitorInfo(C.Structure):
    _fields_ = [("size", W.DWORD), ("monitor", W.RECT), ("work", W.RECT), ("flags", W.DWORD)]


def rect_values(rect):
    return [rect.left, rect.top, rect.right, rect.bottom]


def monitor_info(hwnd):
    if not IS_WINDOWS: return None
    info = MonitorInfo(); info.size = C.sizeof(info)
    user.GetMonitorInfoW.argtypes = [W.HANDLE, C.POINTER(MonitorInfo)]
    if not user.GetMonitorInfoW(user.MonitorFromWindow(hwnd, 2), C.byref(info)): return None
    return info


def workarea_snapshot(hwnd):
    """Capture only the strip actually occupied by this Explorer taskbar."""
    info = monitor_info(hwnd)
    if info is None: return None
    bar = W.RECT()
    user.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
    if not user.GetWindowRect(hwnd, C.byref(bar)): return None
    monitor, work, rect = rect_values(info.monitor), rect_values(info.work), rect_values(bar)
    vertical = bar.bottom - bar.top > bar.right - bar.left
    candidates = (0, 2) if vertical else (1, 3)
    for edge in candidates:
        inner = (2, 3, 0, 1)[edge]
        if rect[edge] == monitor[edge] and work[edge] == rect[inner] and work[edge] != monitor[edge]:
            return {"hwnd": hwnd, "monitor": monitor, "before": work, "edge": edge}
    return None


def set_workarea(rect):
    maximized = maximized_windows_for_area(rect)
    user.SystemParametersInfoW.argtypes = [W.UINT, W.UINT, C.c_void_p, W.UINT]
    user.SystemParametersInfoW.restype = W.BOOL
    if not user.SystemParametersInfoW(0x2F, 0, C.byref(W.RECT(*rect)), 0):
        raise C.WinError(C.get_last_error())
    # A broadcast to Explorer can immediately recreate its stale reservation.
    # Notify other processes (including Qt's hidden screen observer) instead.
    shell_pid = W.DWORD()
    user.GetWindowThreadProcessId(user.FindWindowW("Shell_TrayWnd", None), C.byref(shell_pid))
    @ENUMPROC
    def notify(hwnd, _):
        pid = W.DWORD()
        user.GetWindowThreadProcessId(hwnd, C.byref(pid))
        if pid.value != shell_pid.value:
            user.PostMessageW(hwnd, 0x1A, 0x2F, 0)
        return True
    user.EnumWindows(notify, 0)
    user.SetWindowPos.argtypes = [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT]
    user.SetWindowPos.restype = W.BOOL
    for hwnd, before, bounds in maximized:
        adjusted = adjusted_maximized_rect(bounds, before, rect)
        if adjusted is not None:
            left, top, right, bottom = adjusted
            user.SetWindowPos(hwnd, None, left, top, right - left, bottom - top, 0x4014)


def adjusted_maximized_rect(bounds, before, after):
    """Keep invisible resize borders while fitting an already-maximized window."""
    insets = [before[0] - bounds[0], before[1] - bounds[1], bounds[2] - before[2], bounds[3] - before[3]]
    if any(inset < 0 or inset > 64 for inset in insets): return None
    return [after[0] - insets[0], after[1] - insets[1], after[2] + insets[2], after[3] + insets[3]]


def maximized_windows_for_area(rect):
    if not IS_WINDOWS: return []
    found = []
    user.IsZoomed.argtypes = [W.HWND]; user.IsZoomed.restype = W.BOOL
    user.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
    @ENUMPROC
    def visit(hwnd, _):
        if not user.IsWindowVisible(hwnd) or not user.IsZoomed(hwnd): return True
        # Borderless full-screen windows must keep their original geometry.
        if not user.GetWindowLongW(hwnd, -16) & 0x00C00000: return True
        info = monitor_info(hwnd)
        if info is None: return True
        monitor = rect_values(info.monitor)
        if not (monitor[0] <= rect[0] < rect[2] <= monitor[2] and monitor[1] <= rect[1] < rect[3] <= monitor[3]): return True
        bounds = W.RECT()
        if user.GetWindowRect(hwnd, C.byref(bounds)):
            found.append((int(hwnd), rect_values(info.work), rect_values(bounds)))
        return True
    user.EnumWindows(visit, 0)
    return found


def update_workarea(snapshot, restore=False, reservation=None):
    info = monitor_info(snapshot["hwnd"])
    if info is None or rect_values(info.monitor) != snapshot["monitor"]: return
    edge = snapshot["edge"]
    current = rect_values(info.work)
    source = snapshot["monitor"] if restore else snapshot["before"]
    destination = snapshot["before"] if restore else snapshot["monitor"]
    source_boundary, destination_boundary = source[edge], destination[edge]
    if not restore and reservation is not None and reservation.data is not None and reservation.data.edge == edge:
        offset = reservation.thickness * (1 if edge < 2 else -1)
        source_boundary += offset; destination_boundary += offset
    # Preserve reservations on every other edge, including our own AppBar.
    # A changed boundary belongs to another toolbar and must not be overwritten.
    if current[edge] == source_boundary and current[edge] != destination_boundary:
        current[edge] = destination_boundary
        set_workarea(current)


def restore_workarea(snapshot):
    update_workarea(snapshot, restore=True)


def monitor_rect(hwnd):
    if not IS_WINDOWS: return None
    info = MonitorInfo(); info.size = C.sizeof(info)
    user.GetMonitorInfoW.argtypes = [W.HANDLE, C.POINTER(MonitorInfo)]
    if not user.GetMonitorInfoW(user.MonitorFromWindow(hwnd, 2), C.byref(info)): return None
    rect = info.monitor
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


class AppBar:
    def __init__(self):
        self.data = None
        self.monitor = None
        self.thickness = 0

    def reserve(self, hwnd, rect, position, thickness):
        self.remove()
        if not IS_WINDOWS:
            return
        edge = {"left": 0, "top": 1, "right": 2, "bottom": 3}[position]
        x, y, width, height = rect
        data = AppBarData(C.sizeof(AppBarData), hwnd, 0x8000 + 17, edge, W.RECT(x, y, x + width, y + height), 0)
        shell.SHAppBarMessage(0, C.byref(data))
        self.data = data
        self.monitor, self.thickness = rect, thickness
        self.reposition(force=True)

    def reposition(self, force=False):
        if self.data is None or not IS_WINDOWS: return False
        data = self.data
        old = (data.rect.left, data.rect.top, data.rect.right, data.rect.bottom)
        x, y, width, height = self.monitor
        data.rect = W.RECT(x, y, x + width, y + height)
        shell.SHAppBarMessage(2, C.byref(data))
        if data.edge == 0: data.rect.right = data.rect.left + self.thickness
        elif data.edge == 1: data.rect.bottom = data.rect.top + self.thickness
        elif data.edge == 2: data.rect.left = data.rect.right - self.thickness
        else: data.rect.top = data.rect.bottom - self.thickness
        changed = old != (data.rect.left, data.rect.top, data.rect.right, data.rect.bottom)
        if force or changed: shell.SHAppBarMessage(3, C.byref(data))
        return changed

    def remove(self):
        if self.data is not None and IS_WINDOWS:
            shell.SHAppBarMessage(1, C.byref(self.data))
        self.data = None


def desktop_id():
    if not IS_WINDOWS:
        return ""
    try:
        from comtypes import IUnknown, GUID, COMMETHOD, HRESULT, CoCreateInstance
        class IVirtualDesktopManager(IUnknown):
            _iid_ = GUID("{a5cd92ff-29be-454c-8d04-d82879fb3f1b}")
            _methods_ = [
                COMMETHOD([], HRESULT, "IsWindowOnCurrentVirtualDesktop", (["in"], W.HWND, "window"), (["out"], C.POINTER(W.BOOL), "current")),
                COMMETHOD([], HRESULT, "GetWindowDesktopId", (["in"], W.HWND, "window"), (["out"], C.POINTER(GUID), "desktop")),
                COMMETHOD([], HRESULT, "MoveWindowToDesktop", (["in"], W.HWND, "window"), (["in"], C.POINTER(GUID), "desktop"))]
        manager = CoCreateInstance(GUID("{aa509086-5ca9-4c25-8f95-589d3c07b48a}"), interface=IVirtualDesktopManager)
        return str(manager.GetWindowDesktopId(user.GetForegroundWindow()))
    except Exception:
        return ""


class Recovery:
    """External guard restores only windows/taskbars actually hidden by this dock."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records = []
        self.bars = []
        self.taskbar_state = None
        self.bars_active = False
        self.workareas = []
        self.corner_records = []
        self.process = None
        self.persist()
        if IS_WINDOWS:
            args = [sys.executable, "--watchdog"] if getattr(sys, "frozen", False) else [sys.executable, str(Path(__file__).with_name("app.py")), "--watchdog"]
            args += [str(os.getpid()), str(psutil.Process().create_time()), str(self.path)]
            self.process = subprocess.Popen(args, creationflags=0x08000000)

    def persist(self):
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps({"windows": self.records, "taskbars": self.bars, "taskbar_state": self.taskbar_state, "workareas": self.workareas, "corners": self.corner_records}), encoding="utf-8")
        os.replace(temp, self.path)

    def hide_bars(self):
        if not IS_WINDOWS or self.bars_active:
            return
        original = get_taskbar_state()
        self.bars = [hwnd for hwnd in taskbars() if user.IsWindowVisible(hwnd)]
        self.workareas = [snapshot for hwnd in self.bars if (snapshot := workarea_snapshot(hwnd))]
        # Persist recovery BEFORE changing the shell's setting or visibility.
        # An existing auto-hide preference needs no shell mutation or undo.
        self.taskbar_state = original if not original & ABS_AUTOHIDE else None
        self.persist()
        self.bars_active = True
        try:
            if self.taskbar_state is not None:
                set_taskbar_state(original | ABS_AUTOHIDE)
            for hwnd in self.bars:
                user.ShowWindow(hwnd, 0)
            for snapshot in self.workareas:
                update_workarea(snapshot)
        except Exception:
            self.restore_bars()
            raise

    def restore_bars(self):
        restore_taskbar_snapshot({"taskbars": self.bars, "taskbar_state": self.taskbar_state, "workareas": self.workareas})
        self.bars = []
        self.taskbar_state = None
        self.bars_active = False
        self.workareas = []
        self.persist()

    def maintain_bars(self, reservation=None):
        if not IS_WINDOWS or not self.bars_active: return
        for hwnd in taskbars():
            if hwnd not in self.bars and user.IsWindowVisible(hwnd):
                snapshot = workarea_snapshot(hwnd)
                self.bars.append(hwnd)
                if snapshot: self.workareas.append(snapshot)
                self.persist()
        for hwnd in self.bars:
            if user.IsWindow(hwnd) and user.IsWindowVisible(hwnd): user.ShowWindow(hwnd, 0)
        for snapshot in self.workareas:
            update_workarea(snapshot, reservation=reservation)

    def hide(self, record):
        if alive(record) and record not in self.records:
            self.records.append(record)
            self.persist()
            user.ShowWindow(record["hwnd"], 0)

    def show(self, record):
        if alive(record):
            user.ShowWindowAsync(record["hwnd"], 7 if record.get("minimized") else 8)
        if record in self.records:
            self.records.remove(record)
            self.persist()

    def restore(self):
        from window_effects import restore_corners
        self.corner_records[:] = restore_corners(self.corner_records)
        for record in list(self.records):
            self.show(record)
        self.restore_bars()


def watchdog(pid, created, path):
    import time
    enable_physical_coordinates()
    while True:
        try:
            if abs(psutil.Process(pid).create_time() - created) > .01:
                break
        except psutil.Error:
            break
        time.sleep(.75)
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if IS_WINDOWS:
            from window_effects import restore_corners
            pending_corners = restore_corners(data.get("corners", []))
            for record in data.get("windows", []):
                if alive(record):
                    user.ShowWindowAsync(record["hwnd"], 7 if record.get("minimized") else 8)
            restore_taskbar_snapshot(data)
            if pending_corners:
                data.update(corners=pending_corners, windows=[], taskbars=[], taskbar_state=None, workareas=[])
                Path(path).write_text(json.dumps(data), encoding="utf-8")
                return
        Path(path).unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def enable_physical_coordinates():
    """Match Qt's physical monitor snapshots in recovery processes without Qt."""
    if IS_WINDOWS:
        user.SetProcessDpiAwarenessContext.argtypes = [W.HANDLE]
        user.SetProcessDpiAwarenessContext.restype = W.BOOL
        user.SetProcessDpiAwarenessContext(W.HANDLE(-4))
