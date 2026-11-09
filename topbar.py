"""Accessible, optional desktop status bar with an independent top reservation."""
from __future__ import annotations

import logging
import math

import psutil
from PySide6.QtCore import QDateTime, QLocale, QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPen
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLayout, QMenu, QPushButton, QSizePolicy, QWidget

from appearance import palette
import native


class TopBar(QWidget):
    HEIGHT = 28

    def __init__(self, dock, test_mode=False):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.dock = dock
        self.test_mode = test_mode
        self.reservation = native.AppBar()
        self._reservation_signature = None
        self._native_monitor_rect = None
        self._closed = False
        self._style_key = None
        self.profile_menu = None
        self.dock_status = ""
        self.setObjectName("ntTopBar")
        self.setWindowTitle("NT Dock · Barra superior")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_StyledBackground)
        self.setFixedHeight(self.HEIGHT)
        self.locale = QLocale(QLocale.Portuguese, QLocale.Brazil)

        layout = QHBoxLayout(self)
        layout.setSizeConstraint(QLayout.SetNoConstraint)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)
        self.profile_button = self._button("Ambientes", self.show_profiles)
        self.profile_button.setObjectName("ntEnvironment")
        self.profile_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.profile_button.setMinimumWidth(28)
        layout.addWidget(self.profile_button)
        layout.addStretch(1)
        self.status_button = self._button("Configurações rápidas", lambda: self.open_panel("quick_settings"))
        self.status_button.setToolTip("Rede, volume e bateria · abrir controles do Windows")
        layout.addWidget(self.status_button)
        self.tray_button = self._button("Abrir controles da bandeja do Windows", lambda: self.open_panel("tray"))
        self.tray_button.setText("⌃")
        self.tray_button.setFixedWidth(25)
        layout.addWidget(self.tray_button)
        self.clock_button = self._button("Data e hora · abrir configurações de notificações", lambda: self.open_panel("notifications"))
        self.clock_button.setObjectName("ntClock")
        layout.addWidget(self.clock_button)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(1000)
        self.refresh_timer.timeout.connect(self.sync)
        if not test_mode:
            self.refresh_timer.start()
        self.sync()

    def _button(self, label, callback):
        button = QPushButton(self)
        button.setAccessibleName(label)
        button.setToolTip(label)
        button.setFlat(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setFocusPolicy(Qt.StrongFocus)
        button.clicked.connect(callback)
        return button

    def enabled_for_dock(self):
        config = self.dock.config
        return (config.get("topbar_enabled", True)
                and not getattr(self.dock, "manual_hidden", False))

    def sync(self):
        if self._closed:
            return
        if self.dock.config.get("dock_system_controls", "off") != "off":
            self.dock_status, _ = self._status(compact=False)
            self.dock.update()
        if not self.enabled_for_dock():
            self._release()
            self.hide()
            if self.profile_menu:
                self.profile_menu.close()
            return
        screen = self.dock.chosen_screen()
        if screen is None:
            self._release()
            self.hide()
            return
        geometry = screen.geometry()
        self.setGeometry(geometry.x(), geometry.y(), geometry.width(), self.HEIGHT)
        self._apply_palette()
        self._update_text()
        self.show()

        ratio = screen.devicePixelRatio()
        signature = (screen.name(), geometry.x(), geometry.y(), geometry.width(), geometry.height(), ratio)
        if signature != self._reservation_signature:
            self._release()
            if not self.test_mode:
                rect = native.monitor_rect(int(self.winId()))
                if rect is not None:
                    self._native_monitor_rect = rect
                    self.reservation.reserve(int(self.winId()), rect, "top", round(self.HEIGHT * ratio))
            self._reservation_signature = signature
        self._position_reserved(screen)

    def _position_reserved(self, screen):
        if self.reservation.data is None or self._native_monitor_rect is None:
            return
        rect = self.reservation.data.rect
        monitor_x, monitor_y, _, _ = self._native_monitor_rect
        geometry, ratio = screen.geometry(), screen.devicePixelRatio()
        if self.dock.config.get("replace_taskbar", False):
            self.setGeometry(geometry.x(), round(geometry.y() + (rect.top - monitor_y) / ratio), geometry.width(), self.HEIGHT)
            return
        self.setGeometry(round(geometry.x() + (rect.left - monitor_x) / ratio),
                         round(geometry.y() + (rect.top - monitor_y) / ratio),
                         max(1, round((rect.right - rect.left) / ratio)), self.HEIGHT)

    def appbar_changed(self):
        if self._closed or not self.enabled_for_dock() or self.reservation.data is None:
            return
        if self.reservation.reposition():
            self._position_reserved(self.dock.chosen_screen())

    def nativeEvent(self, event_type, message):
        if native.IS_WINDOWS and not self.test_mode:
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x8011 and msg.wParam == 1:
                QTimer.singleShot(0, self.appbar_changed)
        return super().nativeEvent(event_type, message)

    def _apply_palette(self):
        values = palette(self.dock.config, "topbar")
        family = self.dock.config.get("topbar_font", "Segoe UI Variable")
        size = self.dock.config.get("topbar_font_size", 12)
        key = (values["top"], values["bottom"], values["foreground"], values["border"], self.dock.config.get("blur", True), family, size)
        if key == self._style_key:
            return
        self._style_key = key
        self.setStyleSheet(
            "QWidget#ntTopBar {background:transparent;border:0;}"
            "QWidget#ntTopBar QPushButton {background:transparent;border:0;border-radius:4px;"
            f"color:{values['foreground']};font-family:'{family}';font-size:{size}px;font-weight:400;padding:3px 5px;}}"
            "QWidget#ntTopBar QPushButton#ntEnvironment {font-weight:600;}"
            "QWidget#ntTopBar QPushButton#ntClock {font-weight:500;}"
            "QWidget#ntTopBar QPushButton:hover {background:rgba(127,160,185,30);}"
            "QWidget#ntTopBar QPushButton:pressed {background:rgba(127,160,185,55);}"
            "QWidget#ntTopBar QPushButton:focus {border:1px solid rgba(127,185,220,150);}"
        )

    def _update_text(self):
        config = self.dock.config
        profile = config["profiles"][config["active"]]
        name = profile["name"]
        label_width = self.profile_button.fontMetrics().horizontalAdvance(name) + 20
        self.profile_button.setFixedWidth(max(28, min(label_width, 220, self.width() // 3)))
        available = max(16, self.profile_button.maximumWidth() - 16)
        self.profile_button.setText(self.profile_button.fontMetrics().elidedText(name, Qt.ElideRight, available))
        self.profile_button.setToolTip(f"{name} · trocar ambiente")
        self.profile_button.setAccessibleName(f"Ambiente {name}. Trocar ambiente")
        now = QDateTime.currentDateTime()
        date_pattern = "HH:mm" if self.width() < 420 else "ddd, dd MMM · HH:mm"
        self.clock_button.setText(self.locale.toString(now, date_pattern))
        self.clock_button.setToolTip(self.locale.toString(now, "dddd, dd 'de' MMMM 'de' yyyy · HH:mm") + "\nAbrir configurações de notificações do Windows")
        self.status_button.setVisible(config.get("topbar_status", True))
        self.tray_button.setVisible(config.get("topbar_tray", True))
        status, description = self._status()
        # Keep the center clear for the island, including larger chosen fonts.
        budget = max(110, (self.width() - 230) // 2 - 20)
        tray_width = 29 if config.get("topbar_tray", True) else 0
        clock_width = self.clock_button.fontMetrics().horizontalAdvance(self.clock_button.text()) + 10
        status_width = self.status_button.fontMetrics().horizontalAdvance(status) + 10 if config.get("topbar_status", True) else 0
        if clock_width + status_width + tray_width + 12 > budget:
            self.clock_button.setText(self.locale.toString(now, "HH:mm"))
            clock_width = self.clock_button.fontMetrics().horizontalAdvance(self.clock_button.text()) + 10
        status_room = max(24, budget - clock_width - tray_width - 12)
        if self.status_button.fontMetrics().horizontalAdvance(status) > status_room:
            parts = status.split("  ·  ")
            status = " · ".join(parts[1:] if len(parts) > 1 else parts).replace("Bateria", "Bat")
            if self.status_button.fontMetrics().horizontalAdvance(status) > status_room:
                status = status.replace("Som ", "").replace("Mudo ", "").replace("Bat ", "")
            status = self.status_button.fontMetrics().elidedText(status, Qt.ElideRight, status_room)
        self.status_button.setText(status)
        self.status_button.setToolTip(description + "\nAbrir controles do Windows")
        self.status_button.setAccessibleName("Abrir controles do Windows. " + description)

    def paintEvent(self, event):
        colors = palette(self.dock.config, "topbar")
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, 0, self.height())
        top, bottom = QColor(colors["top"]), QColor(colors["bottom"])
        alpha = 248 if self.dock.config.get("blur", True) else 255
        top.setAlpha(alpha); bottom.setAlpha(alpha)
        gradient.setColorAt(0, top); gradient.setColorAt(1, bottom)
        painter.fillRect(self.rect(), gradient)
        border = QColor(colors["border"]); border.setAlpha(100)
        painter.setPen(QPen(border, 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
        painter.end()

    def _status(self, compact=True):
        try:
            connected = any(state.isup for name, state in psutil.net_if_stats().items()
                            if name.casefold() not in ("lo", "loopback") and "loopback" not in name.casefold())
            network = "Interface de rede ativa" if connected else "Sem interface de rede ativa"
            indicator = "Rede" if connected else "Sem rede"
        except (OSError, psutil.Error, NotImplementedError):
            network, indicator = "Estado de rede indisponível", "Rede"

        volume = None
        muted = False
        media = getattr(self.dock, "media", None)
        if media is not None:
            try:
                snapshot = media.snapshot()
                if isinstance(snapshot, dict):
                    volume = snapshot.get("volume_percent", snapshot.get("volume"))
                    muted = bool(snapshot.get("muted", False))
            except (AttributeError, OSError, RuntimeError):
                pass
        if isinstance(volume, (int, float)) and not isinstance(volume, bool) and math.isfinite(volume) and 0 <= volume <= 100:
            sound = f"{'Mudo' if muted else 'Som'} {round(volume)}%"
            sound_description = f"Volume {round(volume)}%" + (", sem som" if muted else "")
        else:
            sound, sound_description = "Som", "Volume do sistema"

        try:
            battery = psutil.sensors_battery()
        except (AttributeError, OSError, psutil.Error, NotImplementedError):
            battery = None
        battery_text = ""
        descriptions = [network, sound_description]
        if battery is not None:
            battery_text = f"Bateria {round(battery.percent)}%"
            descriptions.append(f"Bateria {round(battery.percent)}%" + (", na tomada" if battery.power_plugged else ""))
        parts = [indicator, sound]
        if battery_text:
            parts.append(battery_text)
        if compact and self.width() < 420:
            parts = [indicator, "Som"]
        return "  ·  ".join(parts), ". ".join(descriptions)

    def show_profiles(self):
        if self.profile_menu is not None:
            self.profile_menu.close()
            self.profile_menu.deleteLater()
        menu = QMenu(self)
        self.profile_menu = menu
        for index, profile in enumerate(self.dock.config["profiles"]):
            action = menu.addAction(profile["name"])
            action.setCheckable(True)
            action.setChecked(index == self.dock.config["active"])
            action.setData(index)
        menu.triggered.connect(lambda action: self._switch_profile(action.data()))
        menu.popup(self.profile_button.mapToGlobal(QPoint(0, self.profile_button.height())))

    def _switch_profile(self, index):
        self.dock.switch_profile(index)
        self.sync()

    def open_panel(self, kind):
        callback = getattr(native, "open_system_panel", None)
        if callback is not None:
            callback(kind)
        else:
            logging.info("Painel do Windows indisponível: %s", kind)

    def _release(self):
        if self.reservation.data is not None:
            self.reservation.remove()
        self._reservation_signature = None
        self._native_monitor_rect = None

    def shutdown(self):
        self._closed = True
        self.refresh_timer.stop()
        if self.profile_menu is not None:
            self.profile_menu.close()
        self._release()
        self.hide()

    def closeEvent(self, event):
        self.shutdown()
        event.accept()
