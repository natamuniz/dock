"""Isolated disposable windows used only by the Windows recovery test."""
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native
import psutil

mode, record_path = sys.argv[1:3]
if mode == "victim":
    from PySide6.QtWidgets import QApplication, QWidget
    from PySide6.QtCore import QTimer
    app = QApplication([]); widget = QWidget(); widget.setWindowTitle("NT Dock · Janela descartável de teste")
    widget.resize(300, 180)
    widget.showMaximized() if os.environ.get("NT_CORNER_VICTIM") == "1" else widget.show()
    app.processEvents()
    record = {"hwnd": int(widget.winId()), "pid": os.getpid(), "created": psutil.Process().create_time(), "minimized": False}
    Path(record_path).write_text(json.dumps(record))
    QTimer.singleShot(25000, app.quit); app.exec()
elif mode == "hider":
    record = json.loads(Path(record_path).read_text())
    recovery = native.Recovery(sys.argv[3]); recovery.hide(record)
    time.sleep(.2)
    os._exit(77)  # Deliberately exercise external watchdog recovery.
elif mode == "corner-hider":
    from window_effects import BottomCorners, region_state
    native.enable_physical_coordinates()
    record = json.loads(Path(record_path).read_text())
    recovery = native.Recovery(sys.argv[3])
    BottomCorners(recovery).sync([record], True)
    assert recovery.corner_records, "Disposable window did not accept rounded corners"
    assert region_state(record["hwnd"])[0] == recovery.corner_records[0]["corner_hash"]
    os._exit(77)
