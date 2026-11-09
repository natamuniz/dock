"""Original compact status island for Dock; no external information is inferred."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

import native


def _time_text(seconds):
    seconds = max(0, int(seconds))
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def island_state(dock, notification=None, preferred=None, now=None):
    """Priority selection: notice, running timer, focus, media, paused timer, idle.

    A preferred timer identifies a pause initiated here. The engine remains the
    source of truth for deadlines and remaining time; this module never ticks it.
    """
    now = time.monotonic() if now is None else now
    if notification and notification["until"] > now:
        return {"kind": "notice", "title": notification["title"], "text": notification["text"],
                "path": notification.get("path"), "remaining": None, "key": None, "running": False}
    timers = (("timer", dock.engine.timer), ("pomodoro", dock.engine.pomodoro))
    for key, timer in timers:
        if timer.deadline is not None:
            return {"kind": key, "title": "Temporizador" if key == "timer" else "Pomodoro · " + timer.phase,
                    "text": "Em andamento", "remaining": timer.seconds(), "key": key, "running": True, "path": None}
    provider = getattr(dock, "media", None)
    if provider is not None:
        try:
            media = provider.snapshot()
            if media.get("available"):
                return {"kind": "media", "title": str(media.get("title") or "Mídia"),
                        "text": str(media.get("artist") or "Mídia do Windows"), "remaining": None,
                        "key": None, "running": bool(media.get("playing")), "path": None, "media": media}
        except Exception:
            pass
    if preferred in ("timer", "pomodoro"):
        timer = getattr(dock.engine, preferred)
        if timer.seconds() > 0:
            return {"kind": preferred, "title": "Temporizador" if preferred == "timer" else "Pomodoro · " + timer.phase,
                    "text": "Pausado", "remaining": timer.seconds(), "key": preferred, "running": False, "path": None}
    return {"kind": "idle", "title": "Hoje", "text": "Nada rolando", "remaining": None,
            "key": None, "running": False, "path": None}


class Island(QWidget):
    """Top-center overlay using the dock's real timers and supplied notifications."""
    def __init__(self, dock, test_mode=False):
        flags = Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
        super().__init__(None, flags)
        self.dock = dock
        self.test_mode = test_mode
        self._now = time.monotonic
        self._notice = None
        self._preferred = None
        self._expanded = False
        self._hovered = False
        self._closed = False
        self._deadlines = {}
        self.current_state = island_state(dock)
        self.setWindowTitle("Dock · Ilha")
        self.setObjectName("NTIsland")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.setStyleSheet("""
            #NTIsland {font-family:'Segoe UI';}
            #NTIsland QLabel {color:#F5F5F7;background:transparent;font-size:11px;}
            #NTIsland QPushButton {color:#F5F5F7;background:#252529;border:1px solid #38383C;
                border-radius:7px;padding:2px 9px;font-size:11px;}
            #NTIsland QPushButton:hover {background:#35353B;border-color:#56565D;}
            #NTIsland QPushButton:pressed {background:#17171B;}
            #NTIsland QPushButton:focus {border-color:#9CC8FF;}
        """)
        layout = QVBoxLayout(self); layout.setContentsMargins(14, 3, 14, 7); layout.setSpacing(4)
        header = QHBoxLayout(); header.setSpacing(7)
        self.indicator = QLabel("●"); self.indicator.setFixedWidth(10)
        self.header_title = QLabel("Hoje"); self.header_title.setMinimumWidth(0)
        self.header_title.setStyleSheet("font-size:11px;font-weight:600")
        self.header_value = QLabel(); self.header_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.header_value.setStyleSheet("font-size:11px;color:#B9B9C2")
        header.addWidget(self.indicator); header.addWidget(self.header_title, 1); header.addWidget(self.header_value)
        header.setContentsMargins(0, 0, 0, 0)
        header_widget = QWidget(); header_widget.setLayout(header); header_widget.setFixedHeight(23)
        layout.addWidget(header_widget)
        self.body = QWidget(); body = QVBoxLayout(self.body); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(4)
        self.status_title = QLabel(); self.status_title.setStyleSheet("font-size:14px;font-weight:600")
        self.status_detail = QLabel(); self.status_detail.setStyleSheet("color:#ACADB7;font-size:11px")
        body.addWidget(self.status_title); body.addWidget(self.status_detail)
        quick = QHBoxLayout(); quick.setSpacing(6)
        quick.addWidget(QLabel("Timer"))
        self.quick_buttons = {}
        for minutes in (5, 15, 25):
            button = QPushButton(f"{minutes} min"); button.setAccessibleName(f"Iniciar temporizador de {minutes} minutos")
            button.setFixedHeight(23); button.clicked.connect(lambda _, value=minutes: self.start_timer(value))
            quick.addWidget(button); self.quick_buttons[minutes] = button
        quick.addStretch(); body.addLayout(quick)
        actions = QHBoxLayout(); actions.setSpacing(6)
        self.pause_button = QPushButton("Pausar"); self.pause_button.setFixedHeight(23)
        self.pause_button.clicked.connect(self.toggle_timer); actions.addWidget(self.pause_button)
        self.reset_button = QPushButton("Zerar"); self.reset_button.setFixedHeight(23)
        self.reset_button.clicked.connect(self.reset_timer); actions.addWidget(self.reset_button)
        self.open_button = QPushButton("Abrir arquivo"); self.open_button.setFixedHeight(23)
        self.open_button.clicked.connect(self.open_notification); actions.addWidget(self.open_button)
        self.reveal_button = QPushButton("Mostrar na pasta"); self.reveal_button.setFixedHeight(23)
        self.reveal_button.clicked.connect(self.reveal_notification); actions.addWidget(self.reveal_button)
        self.idle_hint = QLabel("Nenhuma mídia · calendário não conectado")
        self.idle_hint.setStyleSheet("color:#80818C;font-size:10px"); actions.addWidget(self.idle_hint)
        actions.addStretch(); body.addLayout(actions); layout.addWidget(self.body)
        self.media_controls = QWidget(); media_row = QHBoxLayout(self.media_controls)
        media_row.setContentsMargins(0, 0, 0, 0); media_row.setSpacing(6)
        self.previous_button = QPushButton("Anterior")
        self.play_button = QPushButton("Reproduzir")
        self.next_button = QPushButton("Próxima")
        for button, action in ((self.previous_button, "previous"), (self.play_button, "play_pause"), (self.next_button, "next")):
            button.setFixedHeight(23); button.clicked.connect(lambda _, value=action: self.media_control(value))
            media_row.addWidget(button)
        media_row.addStretch(); body.addWidget(self.media_controls)
        self._ticker = QTimer(self); self._ticker.setInterval(250); self._ticker.timeout.connect(self.sync)
        self._collapse_timer = QTimer(self); self._collapse_timer.setSingleShot(True); self._collapse_timer.setInterval(160)
        self._collapse_timer.timeout.connect(lambda: self.set_expanded(False))
        self.destroyed.connect(self._ticker.stop)
        self.destroyed.connect(self._collapse_timer.stop)
        self.set_expanded(False)
        self.sync()

    def set_expanded(self, expanded):
        if self._closed:
            return
        self._expanded = bool(expanded)
        self.body.setVisible(self._expanded)
        screen = self.dock.chosen_screen().geometry()
        width = min(400 if self._expanded else 230, max(180, screen.width() - 16))
        self.setFixedSize(width, 136 if self._expanded else 32)
        self.move(screen.x() + (screen.width() - self.width()) // 2, screen.y())
        self.update()

    def sync(self):
        if self._closed:
            return
        now = self._now()
        for key in ("timer", "pomodoro"):
            timer = getattr(self.dock.engine, key)
            previous = self._deadlines.get(key)
            if previous is not None and timer.deadline is None and timer.clock() >= previous and self._preferred == key:
                self._preferred = None
            self._deadlines[key] = timer.deadline
        if self._notice and self._notice["until"] <= now:
            self._notice = None
            if not self._hovered:
                self.set_expanded(False)
        self.current_state = island_state(self.dock, self._notice, self._preferred, now)
        state = self.current_state
        if state["key"] is not None and state["running"]:
            self._preferred = state["key"]
        enabled = self.dock.config.get("island_enabled", False) and not getattr(self.dock, "manual_hidden", False)
        visible = enabled and (self.dock.config.get("island_always_visible", True) or state["kind"] != "idle" or self._hovered)
        if not enabled:
            self._ticker.stop(); self.hide(); return
        if not self._ticker.isActive():
            self._ticker.start()
        self.setVisible(visible)
        self.set_expanded(self._expanded)
        profile = self.dock.config["profiles"][self.dock.config["active"]]
        accent = profile.get("color", "#70A7FF")
        self.indicator.setStyleSheet(f"color:{accent};font-size:10px")
        title = state["title"]
        value = _time_text(state["remaining"]) if state["remaining"] is not None else ("Agora" if state["kind"] == "notice" else ("Tocando" if state["running"] else "Pausado") if state["kind"] == "media" else profile["name"])
        self.header_title.setText(self.header_title.fontMetrics().elidedText(title, Qt.ElideRight, max(50, self.width() - 120)))
        self.header_title.setToolTip(title)
        self.header_value.setText(self.header_value.fontMetrics().elidedText(value, Qt.ElideRight, 105))
        if state["kind"] == "idle":
            title = "Nada rolando"
            detail = f"{profile['name']} · {datetime.now():%d/%m/%Y}"
        elif state["remaining"] is not None:
            title = f"{state['title']}  {_time_text(state['remaining'])}"
            detail = state["text"]
        else:
            detail = state["text"]
        self.status_title.setText(self.status_title.fontMetrics().elidedText(title, Qt.ElideRight, self.width() - 28))
        self.status_detail.setText(self.status_detail.fontMetrics().elidedText(detail, Qt.ElideRight, self.width() - 28))
        self.status_detail.setToolTip(detail)
        timer = state["key"] is not None
        self.pause_button.setVisible(timer); self.reset_button.setVisible(timer)
        self.pause_button.setText("Pausar" if state["running"] else "Retomar")
        self.pause_button.setAccessibleName("Pausar temporizador" if state["running"] else "Retomar temporizador")
        self.open_button.setVisible(bool(state["path"])); self.reveal_button.setVisible(bool(state["path"]))
        self.idle_hint.setVisible(state["kind"] == "idle")
        self.media_controls.setVisible(state["kind"] == "media")
        if state["kind"] == "media":
            media = state["media"]
            self.previous_button.setEnabled(bool(media.get("can_previous")))
            self.play_button.setEnabled(bool(media.get("can_toggle")))
            self.next_button.setEnabled(bool(media.get("can_next")))
            self.play_button.setText("Pausar" if media.get("playing") else "Reproduzir")

    def notify(self, title, text, path=None, seconds=6):
        if self._closed:
            return
        # A notification can offer a local file; it cannot introduce URL execution.
        path = str(path) if path is not None else None
        if path is not None and (not Path(path).is_absolute() or "://" in path):
            path = None
        self._notice = {"title": str(title), "text": str(text), "path": path,
                        "until": self._now() + max(1, float(seconds))}
        self.set_expanded(True); self.sync()

    def start_timer(self, minutes):
        if minutes not in (5, 15, 25):
            return
        timer = self.dock.engine.timer
        timer.reset(); timer.remaining = minutes * 60
        timer.deadline = timer.clock() + timer.remaining
        self._preferred = "timer"
        self._notice = None
        self.set_expanded(True); self.sync()

    def toggle_timer(self):
        key = self.current_state["key"]
        if key is not None:
            getattr(self.dock.engine, key).toggle()
            self._preferred = key
            self.sync()

    def reset_timer(self):
        key = self.current_state["key"]
        if key is not None:
            self.dock.engine.reset(key)
            self._preferred = None
            self.sync()

    def open_notification(self):
        path = self.current_state.get("path")
        if path:
            self.dock.launch(path)

    def reveal_notification(self):
        path = self.current_state.get("path")
        if path:
            native.reveal(path)

    def media_control(self, action):
        provider = getattr(self.dock, "media", None)
        if provider is None or action not in ("previous", "play_pause", "next"):
            return
        try:
            accepted = provider.control(action)
            if accepted is False:
                self.notify("Mídia", "Este controle não está disponível para a reprodução atual.")
        except Exception:
            self.notify("Mídia", "Não foi possível controlar a reprodução atual.")

    def enterEvent(self, event):
        self._hovered = True; self._collapse_timer.stop(); self.set_expanded(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False; self._collapse_timer.start()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.position().y() <= 30:
            self.set_expanded(not self._expanded)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath(); path.addRoundedRect(self.rect().adjusted(1, -14, -1, -1), 17, 17)
        painter.setPen(QPen(QColor(255, 255, 255, 24), 1)); painter.setBrush(QColor(9, 9, 12, 248))
        painter.drawPath(path); painter.end()

    def shutdown(self):
        self._closed = True; self._ticker.stop(); self._collapse_timer.stop(); self.hide()

    def closeEvent(self, event):
        self.shutdown(); event.accept()
