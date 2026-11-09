"""NT Dock: personal Windows dock with macOS-inspired glass and magnification."""
from __future__ import annotations

import ctypes
from datetime import datetime
import json
import logging
import math
import os
from pathlib import Path
import sys
import time

if "--watchdog" in sys.argv:
    import native
    index = sys.argv.index("--watchdog")
    native.watchdog(int(sys.argv[index + 1]), float(sys.argv[index + 2]), sys.argv[index + 3])
    raise SystemExit(0)

from PySide6.QtCore import (
    QAbstractNativeEventFilter, QFileInfo, QMimeData, QPoint, QPointF,
    QRectF, QSize, Qt, QTimer, QUrl,
)
from PySide6.QtGui import (
    QColor, QCursor, QDesktopServices, QDrag, QFont, QIcon, QLinearGradient,
    QPainter, QPainterPath, QPen, QPixmap, QImage, QShortcut, QKeySequence,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileIconProvider, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox,
    QPushButton, QScrollArea, QStyle, QSystemTrayIcon, QTextEdit,
    QVBoxLayout, QWidget,
)

from core import MAX_ITEMS, config_path, load_config, save_config, validate_target
import native
from settings import SettingsDialog, ShortcutDialog
from widgets import CATALOG, WidgetEngine
from appearance import palette
from island import Island
from topbar import TopBar
from media_service import MediaService
from desktop_events import DesktopEvents
from window_effects import BottomCorners, fit_maximized


STYLE = """
QDialog,QMenu {background:#202530;color:#eff4fc;font-family:'Segoe UI';font-size:13px;}
QWidget {font-family:'Segoe UI';font-size:13px;}
QDialog QLabel,QDialog QCheckBox {color:#edf2fa;}
QLineEdit,QTextEdit,QListWidget,QComboBox,QDoubleSpinBox {background:#151a24;color:#edf2fa;border:1px solid #3a4253;border-radius:7px;padding:7px;}
QPushButton {background:#354153;color:#f4f7fc;border:1px solid #47566b;border-radius:7px;padding:8px 13px;}
QPushButton:hover {background:#46576d;}
QPushButton:pressed {background:#263140;border-color:#708096;}
QPushButton:focus {border-color:#8AB9FF;}
QTabWidget::pane {border:1px solid #3a4253;border-radius:8px;}
QTabBar::tab {background:#2c3443;color:#dce5f3;padding:10px 15px;}
QTabBar::tab:selected {background:#43536c;color:white;}
QMenu::item {padding:8px 20px;} QMenu::item:selected {background:#43536c;}
QToolTip {background:#242b39;color:white;border:1px solid #58667d;padding:6px;}
"""


def badge_icon(label, color="#65ACFF"):
    pixmap = QPixmap(96, 96); pixmap.fill(Qt.transparent)
    p = QPainter(pixmap); p.setRenderHint(QPainter.Antialiasing)
    gradient = QLinearGradient(0, 0, 0, 96)
    gradient.setColorAt(0, QColor(color).lighter(120)); gradient.setColorAt(1, QColor(color).darker(130))
    p.setPen(QPen(QColor(255, 255, 255, 75), 2)); p.setBrush(gradient)
    p.drawRoundedRect(QRectF(5, 5, 86, 86), 21, 21)
    p.setFont(QFont("Segoe UI", 27 if len(label) < 3 else 21, QFont.Bold)); p.setPen(Qt.white)
    p.drawText(QRectF(5, 5, 86, 86), Qt.AlignCenter, label); p.end()
    return QIcon(pixmap)


class QuickView(QDialog):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.setWindowTitle(path.name); self.resize(820, 620)
        layout = QVBoxLayout(self)
        suffix = path.suffix.lower()
        if suffix in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif"):
            label = QLabel(); label.setAlignment(Qt.AlignCenter)
            pixmap = QPixmap(str(path))
            label.setPixmap(pixmap.scaled(780, 540, Qt.KeepAspectRatio, Qt.SmoothTransformation)); layout.addWidget(label)
        elif suffix == ".pdf":
            from PySide6.QtPdf import QPdfDocument
            from PySide6.QtPdfWidgets import QPdfView
            self.document = QPdfDocument(self); self.document.load(str(path))
            viewer = QPdfView(); viewer.setDocument(self.document); layout.addWidget(viewer)
        elif suffix in (".txt", ".md", ".py", ".php", ".json", ".log", ".csv", ".xml", ".html", ".css", ".js", ".yaml", ".yml"):
            view = QTextEdit(); view.setReadOnly(True)
            with path.open("r", encoding="utf-8", errors="replace") as stream: view.setPlainText(stream.read(100000))
            layout.addWidget(view)
        else:
            layout.addWidget(QLabel("Prévia disponível para imagens, PDF e arquivos de texto."))
        button = QPushButton("Abrir no aplicativo padrão")
        button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))))
        layout.addWidget(button)


class FolderStack(QDialog):
    def __init__(self, path, dock):
        super().__init__(dock, Qt.Tool)
        self.dock, self.path = dock, Path(path)
        self.resize(600, 460); self.setWindowTitle("Pasta")
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        back = QPushButton("↑"); back.clicked.connect(self.parent_folder); toolbar.addWidget(back)
        self.title = QLabel(); toolbar.addWidget(self.title, 1)
        mode = QPushButton("Grade / lista"); mode.clicked.connect(self.toggle_mode); toolbar.addWidget(mode)
        explorer = QPushButton("Explorer"); explorer.clicked.connect(lambda: self.dock.launch(str(self.path))); toolbar.addWidget(explorer)
        layout.addLayout(toolbar)
        self.list = QListWidget(); self.list.setViewMode(QListWidget.IconMode); self.list.setIconSize(QSize(48, 48)); self.list.setGridSize(QSize(110, 100))
        self.list.setMovement(QListWidget.Static); self.list.itemDoubleClicked.connect(self.open_item)
        layout.addWidget(self.list); layout.addWidget(QLabel("Duplo clique para abrir · Espaço para prévia · até 500 itens por pasta"))
        self.preview_shortcut = QShortcut(QKeySequence(Qt.Key_Space), self)
        self.preview_shortcut.activated.connect(self.preview_selected)
        self.refresh()

    def toggle_mode(self):
        grid = self.list.viewMode() == QListWidget.ListMode
        self.list.setViewMode(QListWidget.IconMode if grid else QListWidget.ListMode)
        self.list.setGridSize(QSize(110, 100) if grid else QSize())

    def parent_folder(self):
        self.path = self.path.parent; self.refresh()

    def refresh(self):
        self.title.setText(str(self.path)); self.list.clear()
        try:
            items = sorted(self.path.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold()))
            for path in items[:500]:
                item = QListWidgetItem(self.dock.icon_for({"target": str(path), "name": path.name}), path.name)
                item.setData(Qt.UserRole, str(path)); item.setToolTip(str(path)); self.list.addItem(item)
        except OSError as exc: QMessageBox.warning(self, "Pasta indisponível", str(exc))

    def open_item(self, item):
        path = Path(item.data(Qt.UserRole))
        if path.is_dir(): self.path = path; self.refresh()
        else: self.dock.launch(str(path))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Space: self.preview_selected()
        else: super().keyPressEvent(event)

    def preview_selected(self):
        item = self.list.currentItem()
        if item:
            path = Path(item.data(Qt.UserRole))
            if path.is_file():
                try: QuickView(path, self).exec()
                except (OSError, ImportError) as exc: QMessageBox.warning(self, "Prévia", str(exc))


class WindowPreviews(QDialog):
    def __init__(self, records, dock):
        super().__init__(dock, Qt.Tool | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.records, self.dock, self.thumbnails = records[:5], dock, []
        self.setWindowTitle("Janelas abertas"); self.resize(280 * min(len(self.records), 3), 230 if len(self.records) < 4 else 440)
        from PySide6.QtWidgets import QGridLayout
        layout = QGridLayout(self)
        self.frames = []
        self.dismiss = QTimer(self); self.dismiss.setInterval(150); self.dismiss.timeout.connect(self.check_pointer); self.dismiss.start()
        for index, record in enumerate(self.records):
            container = QWidget(); column = QVBoxLayout(container)
            title = QPushButton(record["title"][:30]); title.setToolTip(record["title"])
            title.clicked.connect(lambda _, r=record: self.activate(r)); column.addWidget(title)
            frame = QPushButton("Prévia ao vivo"); frame.setMinimumSize(230, 130)
            frame.clicked.connect(lambda _, r=record: self.activate(r)); column.addWidget(frame)
            close = QPushButton("Fechar janela"); close.clicked.connect(lambda _, r=record: native.close_window(r)); column.addWidget(close)
            layout.addWidget(container, index // 3, index % 3)
            self.frames.append(frame)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(80, self.register)

    def register(self):
        for frame, record in zip(self.frames, self.records):
            thumb = native.Thumbnail(int(self.winId()), record["hwnd"])
            pos = frame.mapTo(self, QPoint())
            ratio = self.devicePixelRatioF()
            thumb.update(int((pos.x() + 2) * ratio), int((pos.y() + 2) * ratio), int((frame.width() - 4) * ratio), int((frame.height() - 4) * ratio))
            self.thumbnails.append(thumb)
            if thumb.valid: frame.setText("")
            else: frame.setText("Prévia indisponível\nClique para ativar")

    def activate(self, record):
        native.activate(record, toggle=False); self.close()

    def check_pointer(self):
        cursor = QCursor.pos()
        if not self.geometry().contains(cursor) and not self.dock.bar_rect.contains(self.dock.mapFromGlobal(cursor)):
            self.close()

    def closeEvent(self, event):
        for thumb in self.thumbnails: thumb.close()
        self.thumbnails.clear(); super().closeEvent(event)


class WidgetsPanel(QDialog):
    def __init__(self, dock):
        super().__init__(dock, Qt.Tool)
        self.dock = dock; self.setWindowTitle("NT Dock · Widgets"); self.resize(700, 600)
        root = QVBoxLayout(self)
        title = QLabel("Seu painel"); title.setStyleSheet("font-size:25px;font-weight:bold;padding:10px"); root.addWidget(title)
        self.search = QLineEdit(); self.search.setPlaceholderText("Buscar widget…"); self.search.textChanged.connect(self.filter); root.addWidget(self.search)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        body = QWidget()
        from PySide6.QtWidgets import QGridLayout
        grid = QGridLayout(body); self.cards = {}
        for index, (key, (name, glyph)) in enumerate(dock.engine.catalog().items()):
            card = QWidget(); card.setStyleSheet("background:#2c3545;border-radius:14px;")
            column = QVBoxLayout(card); label = QLabel(f"{glyph}  {name}"); column.addWidget(label)
            value = QPushButton(); value.setMinimumHeight(50)
            value.clicked.connect(lambda _, k=key: dock.widget_clicked(k)); column.addWidget(value)
            row = QHBoxLayout()
            pin = QPushButton("Fixar"); pin.clicked.connect(lambda _, k=key: dock.pin_widget(k)); row.addWidget(pin)
            reset = QPushButton("Zerar"); reset.clicked.connect(lambda _, k=key: dock.engine.reset(k)); row.addWidget(reset)
            column.addLayout(row); grid.addWidget(card, index // 3, index % 3); self.cards[key] = (card, value)
        scroll.setWidget(body); root.addWidget(scroll)
        footer = QPushButton("Configurar fontes e aparência"); footer.clicked.connect(dock.settings); root.addWidget(footer)
        self.timer = QTimer(self); self.timer.timeout.connect(self.refresh); self.timer.start(1000); self.refresh()

    def filter(self, text):
        catalog = self.dock.engine.catalog()
        for key, (card, _) in self.cards.items(): card.setVisible(text.casefold() in catalog[key][0].casefold())

    def refresh(self):
        for key, (card, button) in self.cards.items():
            if not card.isHidden(): button.setText(self.dock.engine.value(key))


class HotKeys(QAbstractNativeEventFilter):
    def __init__(self, dock):
        super().__init__(); self.dock = dock; self.ids = []
        if native.IS_WINDOWS:
            for ident, key in [(100 + i, ord(str(i + 1))) for i in range(9)] + [(200, ord("D"))]:
                if native.user.RegisterHotKey(int(dock.winId()), ident, 0x4000 | 1 | 2, key): self.ids.append(ident)
                else: logging.warning("Atalho global em conflito: id %s", ident)

    def nativeEventFilter(self, event_type, message):
        if native.IS_WINDOWS:
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x8011 and msg.wParam == 1 and msg.hWnd == int(self.dock.winId()):
                QTimer.singleShot(0, self.dock.appbar_changed)
            if msg.message == 0x312:
                ident = msg.wParam
                if ident == 200: self.dock.toggle_visibility()
                elif 100 <= ident < 109: self.dock.switch_profile(ident - 100)
                return True, 0
        return False, 0

    def close(self):
        if native.IS_WINDOWS:
            for ident in self.ids: native.user.UnregisterHotKey(int(self.dock.winId()), ident)


class Dock(QWidget):
    def __init__(self, config, *, test_mode=False):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.config, self.test_mode = config, test_mode
        self.setWindowTitle("NT Dock")
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True); self.setAcceptDrops(True)
        self.provider = QFileIconProvider(); self.icons = {}; self.exe_cache = {}
        self.icon_pixmaps = {}
        self.trash_icon = None
        self.reservation_signature = None
        self.native_screen_rect = None
        self.engine = WidgetEngine(config.get("widget_options", {}))
        self.engine.load_custom(config_path().parent / "widgets")
        self.appbar = native.AppBar()
        self.recovery = None if test_mode else native.Recovery(config_path().parent / f"recovery-{os.getpid()}.json")
        self.bottom_corners = BottomCorners(self.recovery) if self.recovery is not None else None
        self.running, self.records_by_profile = [], {}
        self.entries, self.rects, self.scales = [], [], []
        self.base_centers = []; self._last_animation_at = None
        self.hover = -1; self.pointer = None; self.drag_start = None; self.pressed_index = -1
        self.folded = False; self.manual_hidden = False; self.busy = False; self.popup = None
        self.last_interaction = time.monotonic(); self.last_wheel = 0; self.bounces = {}
        self.last_desktop, self.window_cycle = "", {}
        self.window_owners = {}; self.started = time.time(); self.folder_counts = {}; self.folder_futures = {}; self.folder_cutoffs = {}; self.last_folder_check = 0
        self.pet_timer = QTimer(self); self.pet_timer.setInterval(100); self.pet_timer.timeout.connect(self.update)
        if self.config.get("mascot", "none") != "none": self.pet_timer.start()
        self.animation = QTimer(self); self.animation.setTimerType(Qt.PreciseTimer)
        refresh = min(144., max(60., self.chosen_screen().refreshRate()))
        self.animation.setInterval(max(6, int(1000 / refresh))); self.animation.timeout.connect(self.animate)
        self.clock = QTimer(self); self.clock.setInterval(1000); self.clock.timeout.connect(self.tick); self.clock.start()
        self.edge_timer = QTimer(self); self.edge_timer.setInterval(120); self.edge_timer.timeout.connect(self.edge_tick); self.edge_timer.start()
        self.hover_timer = QTimer(self); self.hover_timer.setSingleShot(True); self.hover_timer.setInterval(650); self.hover_timer.timeout.connect(self.preview_hover)
        self.tray = QSystemTrayIcon(badge_icon("NT", "#56B7AF"), self)
        self.tray.setToolTip("NT Dock · clique para mostrar/ocultar")
        self.tray.activated.connect(lambda reason: self.toggle_visibility() if reason == QSystemTrayIcon.Trigger else None)
        self.tray.setContextMenu(self.build_menu())
        if not test_mode and QSystemTrayIcon.isSystemTrayAvailable(): self.tray.show()
        self.rebuild(); self.place(); self.apply_system()
        self.hotkeys = HotKeys(self) if not test_mode else None
        if self.hotkeys: QApplication.instance().installNativeEventFilter(self.hotkeys)
        self.destroyed.connect(lambda: self.engine.close())
        for screen in QApplication.screens(): screen.availableGeometryChanged.connect(self.screen_changed)
        QApplication.instance().screenAdded.connect(self.screen_changed)
        QApplication.instance().screenRemoved.connect(self.screen_changed)
        self._services_closed = False
        self.media = MediaService(); self.engine.media = self.media
        self.desktop_events = DesktopEvents(roots={} if test_mode else None)
        self.island = Island(self, test_mode=test_mode)
        self.topbar = TopBar(self, test_mode=test_mode)
        self._media_enabled = None
        self.sync_panels()
        self.destroyed.connect(self.shutdown_services)

    @property
    def profile(self): return self.config["profiles"][self.config["active"]]

    def screen_changed(self, *_):
        self.place()
        self.sync_panels()
        QTimer.singleShot(200, self.reserve)

    def chosen_screen(self):
        return next((screen for screen in QApplication.screens() if screen.name() == self.config.get("screen")), QApplication.primaryScreen())

    def persist(self):
        if not self.test_mode:
            try: save_config(self.config)
            except OSError as exc: self.notify("Configuração não salva", str(exc))

    def build_menu(self):
        menu = QMenu(self)
        menu.addAction("Mostrar / ocultar dock", self.toggle_visibility)
        profiles = menu.addMenu("Perfis")
        for index, profile in enumerate(self.config["profiles"]):
            action = profiles.addAction(profile["name"], lambda _, i=index: self.switch_profile(i))
            action.setCheckable(True); action.setChecked(index == self.config["active"])
        menu.addAction("Adicionar atalho…", self.add_shortcut)
        menu.addAction("Fixar aplicativo instalado…", self.pick_application)
        menu.addAction("Todos os widgets…", self.widgets_panel)
        menu.addAction("Ajustes…", self.settings)
        menu.addSeparator()
        menu.addAction("Abrir pasta de configuração", lambda: self.launch(str(config_path().parent)))
        if native.IS_WINDOWS:
            menu.addAction("Abrir Lixeira", lambda: QDesktopServices.openUrl(QUrl("shell:RecycleBinFolder")))
            menu.addAction("Restaurar barra e janelas agora", self.restore_windows)
        menu.addSeparator(); menu.addAction("Sair do NT Dock", self.quit)
        return menu

    def notify(self, title, message):
        logging.info("%s: %s", title, message)
        if self.tray.isVisible(): self.tray.showMessage(title, message, QSystemTrayIcon.Information, 5000)
        if hasattr(self, "island"): self.island.notify(title, message)

    def sync_panels(self):
        if not hasattr(self, "island") or self._services_closed: return
        enabled = self.config.get("media_enabled", True) and not self.test_mode
        if enabled != self._media_enabled:
            self.media.start() if enabled else self.media.shutdown()
            self._media_enabled = enabled
        self.topbar.sync(); self.island.sync()

    def shutdown_services(self, *_):
        if getattr(self, "_services_closed", True): return
        self._services_closed = True
        self.topbar.shutdown(); self.island.shutdown()
        self.desktop_events.shutdown(); self.media.shutdown()

    def icon_for(self, item):
        target = item["target"]
        records = self.matching(item)
        cache_key = (target, item.get("icon", ""), records[0]["hwnd"] if records else 0)
        if cache_key in self.icons: return self.icons[cache_key]
        if item.get("icon"):
            icon = QIcon(os.path.expandvars(os.path.expanduser(item["icon"])))
            if not icon.isNull(): self.icons[cache_key] = icon; return icon
        if records:
            handle = native.window_icon(records[0])
            if handle:
                image = QImage.fromHICON(handle)
                if not image.isNull():
                    icon = QIcon(QPixmap.fromImage(image)); self.icons[cache_key] = icon
                    return icon
        if target.startswith(("http://", "https://")):
            brands = {"github.com": ("GH", "#6754A2"), "youtube.com": ("▶", "#EF5555"),
                "python.org": ("Py", "#3E8DCB"), "php.net": ("php", "#858EC7"), "laravel.com": ("L", "#F66056")}
            glyph, color = next((v for k, v in brands.items() if k in target), (item["name"][:2].upper(), self.profile["color"]))
            icon = badge_icon(glyph, color)
        else:
            path = os.path.expandvars(os.path.expanduser(target))
            icon = self.provider.icon(QFileInfo(path))
            if icon.isNull(): icon = badge_icon(item["name"][:2].upper(), self.profile["color"])
        self.icons[cache_key] = icon
        return icon

    def matching(self, item):
        target = item.get("exe_key") or self.exe_key(item["target"])
        return [record for record in self.running if os.path.normcase(record["exe"]) == target]

    def exe_key(self, target):
        if target not in self.exe_cache: self.exe_cache[target] = native.resolved_exe(target)
        return self.exe_cache[target]

    def rebuild(self):
        entries = []
        if self.config.get("show_start", False): entries.append({"kind": "start", "name": "Iniciar", "glyph": "⊞"})
        for index, item in enumerate(self.profile["items"]): entries.append({**item, "kind": "app", "pinned": index})
        pinned = {self.exe_key(i["target"]) for i in self.profile["items"] if "://" not in i["target"]}
        seen = set(pinned)
        running_entries = []
        for record in self.running:
            key = os.path.normcase(record["exe"])
            if key not in seen and len(entries) + len(running_entries) < MAX_ITEMS + 5:
                running_entries.append({"kind": "app", "name": Path(record["exe"]).stem, "target": record["exe"], "exe_key": key, "running_group": True})
                seen.add(key)
        chosen = self.profile.get("widgets", self.config.get("widgets", ["clock", "pomodoro"]))
        for key in chosen:
            name, glyph = self.engine.catalog().get(key, (key, "✦"))
            entries.append({"kind": "widget", "name": name, "key": key, "glyph": glyph})
        entries.extend(running_entries)
        if self.config.get("show_trash", True): entries.append({"kind": "trash", "name": "Lixeira", "glyph": ""})
        if self.config.get("show_settings", True): entries.append({"kind": "settings", "name": "Ajustes", "glyph": "⚙"})
        system_controls = self.config.get("dock_system_controls", "off")
        if system_controls in ("full", "compact"):
            entries.extend((
                {"kind": "system", "key": "tray", "name": "Bandeja do Windows", "glyph": "⌃"},
                {"kind": "system", "key": "quick_settings", "name": "Rede, volume e bateria", "glyph": "≡"},
            ))
        if system_controls != "off":
            entries.append({"kind": "system", "key": "notifications", "name": "Data e hora", "glyph": "◷"})
        entries.append({"kind": "profile", "name": "Ambientes · " + self.profile["name"], "glyph": "⋮"})
        old_targets = [(e["kind"], e.get("target"), e.get("key")) for e in self.entries]
        new_targets = [(e["kind"], e.get("target"), e.get("key")) for e in entries]
        self.entries = entries
        if old_targets != new_targets:
            self.scales = [1.] * len(entries); self.hover = -1; self.pointer = None
        self.compute_layout(); self.update()

    def place(self):
        screen = self.chosen_screen()
        if hasattr(self, "animation"):
            interval = max(6, int(1000 / min(144., max(60., screen.refreshRate()))))
            if self.animation.interval() != interval: self.animation.setInterval(interval)
        # A reserved appbar changes availableGeometry; use full monitor geometry
        # when this dock itself owns the reservation to avoid feedback loops.
        area = screen.geometry() if self.appbar.data is not None else screen.availableGeometry()
        self.area = area
        position = self.config.get("position", "bottom")
        info = native.monitor_info(int(self.winId())) if not self.test_mode and screen.geometry().contains(self.frameGeometry().center()) else None
        if info is not None:
            ratio = screen.devicePixelRatio()
            geometry = screen.geometry()
            left, top, right, bottom = native.rect_values(info.work)
            if self.appbar.data is not None:
                if position == "bottom": bottom += self.appbar.thickness
                elif position == "left": left -= self.appbar.thickness
                else: right += self.appbar.thickness
            area.setCoords(round(geometry.x() + (left - info.monitor.left) / ratio),
                           round(geometry.y() + (top - info.monitor.top) / ratio),
                           round(geometry.x() + (right - info.monitor.left) / ratio) - 1,
                           round(geometry.y() + (bottom - info.monitor.top) / ratio) - 1)
        depth = 170
        if position == "bottom":
            self.setGeometry(area.x() + 8, area.bottom() - depth - 9, max(200, area.width() - 16), depth)
        elif position == "left": self.setGeometry(area.x() + 8, area.y() + 8, depth, max(200, area.height() - 16))
        else: self.setGeometry(area.right() - depth - 7, area.y() + 8, depth, max(200, area.height() - 16))
        self.compute_layout(); self.update()

    def map_rect(self, u, v, length, depth):
        position = self.config.get("position", "bottom")
        if position == "bottom": return QRectF(u, v, length, depth)
        if position == "left": return QRectF(self.width() - v - depth, u, depth, length)
        return QRectF(v, u, depth, length)

    def axis(self, point): return point.x() if self.config.get("position", "bottom") == "bottom" else point.y()

    def compute_layout(self):
        horizontal = self.config.get("position", "bottom") == "bottom"
        length, depth = (self.width(), self.height()) if horizontal else (self.height(), self.width())
        widths = [self.config["icon_size"] if e["kind"] == "app" else (76 if horizontal and e["kind"] == "widget" else 32) for e in self.entries]
        if horizontal:
            for index, entry in enumerate(self.entries):
                if entry["kind"] == "system" and entry["key"] == "notifications":
                    widths[index] = 62
                elif entry["kind"] == "system" and entry["key"] == "quick_settings":
                    widths[index] = 140 if self.config.get("dock_system_controls") == "full" else 72
        gap = 6
        fit = min(1., max(100, length - 36) / max(1, sum(widths) + gap * (len(widths) - 1)))
        base_widths = [width * fit for width in widths]
        base_origin = (length - sum(base_widths) - gap * fit * max(0, len(widths) - 1)) / 2
        self.base_centers = []
        for width in base_widths:
            self.base_centers.append(base_origin + width / 2)
            base_origin += width + gap * fit
        widths = [w * fit * (self.scales[i] if e["kind"] == "app" else 1) for i, (w, e) in enumerate(zip(widths, self.entries))]
        gap *= fit
        if sum(widths) + gap * (len(widths) - 1) > length - 32:
            extra_fit = (length - 32) / (sum(widths) + gap * (len(widths) - 1))
            widths = [w * extra_fit for w in widths]; gap *= extra_fit
        total = sum(widths) + gap * max(0, len(widths) - 1)
        origin = (length - total) / 2
        baseline = depth - 14
        padding = self.config.get("bar_padding", 7)
        self.rects = []
        for width, entry in zip(widths, self.entries):
            height = width if entry["kind"] == "app" else (32 * fit)
            self.rects.append(self.map_rect(origin, baseline - height, width, height))
            origin += width + gap
        shelf = max(self.config["icon_size"], 32) * fit
        self.bar_rect = self.map_rect((length - total) / 2 - 10, baseline - shelf - padding, total + 20, shelf + padding * 2)

    def paintEvent(self, event):
        if self.folded:
            p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen); p.setBrush(QColor(self.profile["color"]))
            horizontal = self.config.get("position", "bottom") == "bottom"
            length, depth = (self.width(), self.height()) if horizontal else (self.height(), self.width())
            p.drawRoundedRect(self.map_rect(length / 2 - 42, depth - 5, 84, 4), 2, 2); p.end(); return
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.SmoothPixmapTransform)
        colors = palette(self.config)
        foreground = QColor(colors["foreground"])
        dark = foreground.lightness() > 128
        roundness = self.config.get("dock_roundness", -1)
        half_edge = min(self.bar_rect.width(), self.bar_rect.height()) / 2
        radius = min(colors["radius"], half_edge) if roundness < 0 else half_edge * roundness / 100
        opacity = self.config.get("dock_opacity", -1)
        alpha = (204 if self.config.get("blur", True) else 255) if opacity < 0 else round(255 * opacity / 100)
        border = self.config.get("dock_border", 1)
        glow = self.config.get("dock_glow", -1)
        if alpha:
            for spread in (8, 5, 2):
                p.setBrush(QColor(0, 0, 0, round(6 * alpha / 255)))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(self.bar_rect.adjusted(-spread, -spread / 2, spread, spread), radius + spread / 2, radius + spread / 2)
        gradient = QLinearGradient(self.bar_rect.topLeft(), self.bar_rect.bottomLeft())
        top, bottom = QColor(colors["top"]), QColor(colors["bottom"])
        top.setAlpha(alpha)
        bottom.setAlpha(alpha)
        gradient.setColorAt(0, top)
        gradient.setColorAt(1, bottom)
        p.setBrush(gradient)
        p.setPen(QPen(QColor(colors["border"]), border) if border else Qt.NoPen)
        p.drawRoundedRect(self.bar_rect, radius, radius)
        if alpha and (glow > 0 or self.config.get("dock_reflection", False)):
            shape = QPainterPath()
            shape.addRoundedRect(self.bar_rect, radius, radius)
            sheen = QLinearGradient(self.bar_rect.topLeft(), QPointF(self.bar_rect.left(), self.bar_rect.center().y()))
            sheen.setColorAt(0, QColor(255, 255, 255, round(alpha * max(0, glow) / 100)))
            sheen.setColorAt(1, Qt.transparent)
            p.fillPath(shape, sheen)
            if self.config.get("dock_reflection", False):
                p.save()
                p.setClipPath(shape)
                strip = QRectF(self.bar_rect)
                strip.setHeight(strip.height() / 2)
                p.fillRect(strip, QColor(255, 255, 255, round(alpha * .12)))
                p.restore()
        if alpha and glow < 0 and border:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(255, 255, 255, 22 if dark else 110), 1))
            p.drawRoundedRect(self.bar_rect.adjusted(1, 1, -1, -1), max(0, radius - 1), max(0, radius - 1))
        for i, (entry, rect) in enumerate(zip(self.entries, self.rects)):
            kind = entry["kind"]
            previous_entry = self.entries[i - 1] if i else None
            if previous_entry and ((kind == "app" and entry.get("running_group") and not previous_entry.get("running_group")) or
                                   (kind == "trash" and previous_entry["kind"] in ("app", "widget"))):
                horizontal = self.config.get("position", "bottom") == "bottom"
                previous = self.rects[i - 1]
                p.setPen(QPen(QColor(255 if dark else 40, 255 if dark else 45, 255 if dark else 55, 42), 1))
                if horizontal:
                    x = (previous.right() + rect.left()) / 2
                    p.drawLine(QPointF(x, self.bar_rect.top() + 15), QPointF(x, self.bar_rect.bottom() - 15))
                else:
                    y = (previous.bottom() + rect.top()) / 2
                    p.drawLine(QPointF(self.bar_rect.left() + 15, y), QPointF(self.bar_rect.right() - 15, y))
            if kind == "app":
                bounce = self.bounces.get(entry["target"], 0)
                elapsed = time.monotonic() - bounce
                feedback = self.config.get("launch_animation", "bounce")
                offset = max(0, math.sin(elapsed * 10)) * 8 if bounce and elapsed < .55 and feedback == "bounce" else 0
                icon_rect = rect.adjusted(2, 2, -2, -2)
                if bounce and elapsed < .55:
                    if feedback == "pulse":
                        inset = math.sin(elapsed * 16) * rect.width() * .035
                        icon_rect.adjust(-inset, -inset, inset, inset)
                    elif feedback == "shake": icon_rect.translate(math.sin(elapsed * 50) * 2, 0)
                if i == self.pressed_index:
                    inset = icon_rect.width() * .025
                    icon_rect.adjust(inset, inset, -inset, -inset)
                position = self.config.get("position", "bottom")
                icon_rect.translate(0, -offset) if position == "bottom" else icon_rect.translate(offset if position == "left" else -offset, 0)
                icon = self.icon_for(entry)
                raster_key = (icon.cacheKey(), self.config["icon_size"], self.config["magnification"], self.devicePixelRatioF())
                if raster_key not in self.icon_pixmaps:
                    if len(self.icon_pixmaps) >= 96: self.icon_pixmaps.clear()
                    pixels = math.ceil(self.config["icon_size"] * self.config["magnification"] * self.devicePixelRatioF())
                    self.icon_pixmaps[raster_key] = icon.pixmap(pixels, pixels)
                pixmap = self.icon_pixmaps[raster_key]
                if not pixmap.isNull():
                    fit = min(icon_rect.width() / pixmap.width(), icon_rect.height() / pixmap.height())
                    width, height = pixmap.width() * fit, pixmap.height() * fit
                    target_rect = QRectF(icon_rect.center().x() - width / 2, icon_rect.center().y() - height / 2, width, height)
                    p.drawPixmap(target_rect, pixmap, QRectF(pixmap.rect()))
                if self.matching(entry):
                    p.setPen(Qt.NoPen); p.setBrush(QColor(self.profile["color"]) if self.config.get("colored_indicators", True) else foreground)
                    horizontal = self.config.get("position", "bottom") == "bottom"
                    center = QPointF(rect.center().x(), self.bar_rect.bottom() - 6 if horizontal else rect.bottom() + 3)
                    if self.config.get("app_indicator", "dot") == "dash":
                        p.drawRoundedRect(QRectF(center.x() - 5, center.y() - 1.5, 10, 3), 1.5, 1.5)
                    else:
                        p.drawEllipse(center, 2, 2)
                count = self.folder_counts.get(entry["target"], 0)
                if count:
                    badge = QRectF(rect.right() - 17, rect.top() - 2, 23, 20)
                    p.setPen(Qt.NoPen); p.setBrush(QColor("#F35C68")); p.drawRoundedRect(badge, 10, 10)
                    p.setPen(Qt.white); p.setFont(QFont("Segoe UI", 8, QFont.Bold)); p.drawText(badge, Qt.AlignCenter, str(count) if count < 100 else "99+")
            elif kind == "system":
                key = entry["key"]
                mode = self.config.get("dock_system_controls")
                horizontal = self.config.get("position", "bottom") == "bottom"
                text = entry["glyph"]
                subtext = ""
                if key == "notifications":
                    now = datetime.now()
                    text = now.strftime("%H:%M")
                    if mode == "full" and horizontal:
                        subtext = now.strftime("%d/%m/%Y")
                elif key == "quick_settings" and horizontal:
                    text = self.topbar.dock_status if mode == "full" else self.topbar.dock_status.split("  ·  ")[0]
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(255, 255, 255, 32 if i == self.hover else 15))
                p.drawRoundedRect(rect, 8, 8)
                p.setPen(foreground)
                p.setFont(QFont("Segoe UI", 8, QFont.DemiBold))
                label = rect.adjusted(3, 0, -3, -rect.height() / 2 if subtext else 0)
                p.drawText(label, Qt.AlignCenter, p.fontMetrics().elidedText(text, Qt.ElideRight, max(0, int(label.width()))))
                if subtext:
                    p.setFont(QFont("Segoe UI", 7))
                    p.drawText(rect.adjusted(0, rect.height() / 2, 0, 0), Qt.AlignCenter, subtext)
            elif kind == "start":
                if i == self.hover:
                    p.setPen(Qt.NoPen); p.setBrush(QColor(255, 255, 255, 25)); p.drawRoundedRect(rect, 12, 12)
                # Windows 11 logo: four equal, crisp blue panes, independent of fonts.
                size = min(rect.width(), rect.height()) * .52
                logo = QRectF(rect.center().x() - size / 2, rect.center().y() - size / 2, size, size)
                gap = size * .075
                pane = (size - gap) / 2
                gradient = QLinearGradient(logo.topLeft(), logo.bottomRight())
                gradient.setColorAt(0, QColor("#00ADEF")); gradient.setColorAt(1, QColor("#0078D4"))
                p.setPen(Qt.NoPen); p.setBrush(gradient)
                for row in range(2):
                    for column in range(2):
                        p.drawRect(QRectF(logo.left() + column * (pane + gap), logo.top() + row * (pane + gap), pane, pane))
            elif kind == "widget":
                color = QColor(self.profile["color"])
                color.setAlpha(70 if self.config.get("widget_style") == "color" else 16)
                p.setPen(QPen(QColor(255, 255, 255, 25), 1)); p.setBrush(color); p.drawRoundedRect(rect, 12, 12)
                p.setPen(foreground); p.setFont(QFont("Segoe UI Symbol", 12))
                p.drawText(QRectF(rect.left() + 3, rect.top(), 22, rect.height()), Qt.AlignCenter, entry["glyph"])
                p.setFont(QFont("Segoe UI", 9, QFont.DemiBold))
                value = self.engine.value(entry["key"])
                text_rect = rect.adjusted(25, 2, -4, -rect.height() / 2 + 1)
                p.drawText(text_rect, Qt.AlignCenter, p.fontMetrics().elidedText(value, Qt.ElideRight, int(text_rect.width())))
                p.setFont(QFont("Segoe UI", 7))
                caption = "Foco" if entry["key"] == "pomodoro" else entry["name"]
                caption_rect = rect.adjusted(25, rect.height() / 2, -4, -2)
                p.drawText(caption_rect, Qt.AlignCenter, p.fontMetrics().elidedText(caption, Qt.ElideRight, int(caption_rect.width())))
                if entry["key"] == "analog": self.draw_clock(p, rect)
            elif kind == "trash" and self.config.get("trash_style", "windows") != "windows":
                center = rect.center()
                if self.config["trash_style"] == "tile":
                    tile = QRectF(center.x() - 14, center.y() - 14, 28, 28)
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(self.profile["color"]))
                    p.drawRoundedRect(tile, 7, 7)
                    ink = QColor("#10151C") if QColor(self.profile["color"]).lightness() > 145 else QColor("#FFFFFF")
                else:
                    ink = foreground
                p.setPen(QPen(ink, 1.6))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(QRectF(center.x() - 5, center.y() - 3, 10, 11), 2, 2)
                p.drawLine(center + QPointF(-7, -5), center + QPointF(7, -5))
                p.drawLine(center + QPointF(-2, -8), center + QPointF(2, -8))
            elif kind == "trash":
                if self.trash_icon is None:
                    self.trash_icon = self.style().standardIcon(QStyle.SP_TrashIcon)
                    handle = native.recycle_icon() if not self.test_mode else 0
                    if handle:
                        try:
                            stock = QImage.fromHICON(handle)
                            if not stock.isNull(): self.trash_icon = QIcon(QPixmap.fromImage(stock))
                        finally: native.release_icon(handle)
                self.trash_icon.paint(p, rect.adjusted(3, 2, -3, -2).toRect())
            elif kind == "profile" and self.config.get("profile_dots", True):
                for owner, point in enumerate(self.profile_points(rect)):
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(self.config["profiles"][owner]["color"]) if owner == self.config["active"] else QColor(255 if dark else 40, 255 if dark else 45, 255 if dark else 55, 90))
                    p.drawEllipse(point, 2.4 if owner == self.config["active"] else 1.8, 2.4 if owner == self.config["active"] else 1.8)
            else:
                if i == self.hover:
                    p.setPen(Qt.NoPen); p.setBrush(QColor(255, 255, 255, 25)); p.drawRoundedRect(rect, 12, 12)
                p.setPen(foreground)
                p.setFont(QFont("Segoe UI Symbol", 13 if kind == "settings" else 17))
                p.drawText(rect, Qt.AlignCenter, entry["glyph"])
        if self.config.get("mascot", "none") != "none": self.draw_mascot(p)
        if 0 <= self.hover < len(self.entries) and self.config.get("position", "bottom") == "bottom":
            entry, rect = self.entries[self.hover], self.rects[self.hover]
            text = entry["name"]
            p.setFont(QFont("Segoe UI", 10)); metrics = p.fontMetrics()
            label = QRectF(rect.center().x() - metrics.horizontalAdvance(text) / 2 - 12, max(0, rect.top() - 38), metrics.horizontalAdvance(text) + 24, 28)
            label.moveLeft(max(2, min(label.left(), self.width() - label.width() - 2)))
            p.setPen(QPen(QColor(255, 255, 255, 40), 1)); p.setBrush(QColor(28, 34, 46, 235)); p.drawRoundedRect(label, 8, 8)
            p.setPen(Qt.white); p.drawText(label, Qt.AlignCenter, text)
        p.end()

    def profile_points(self, rect):
        count = len(self.config["profiles"])
        rows = min(count, 6); columns = math.ceil(count / rows)
        return [QPointF(rect.center().x() + ((i // rows) - (columns - 1) / 2) * 8,
                        rect.center().y() + ((i % rows) - (rows - 1) / 2) * 5) for i in range(count)]

    def draw_mascot(self, painter):
        # Vector character: no borrowed sprites or downloaded assets.
        phase = time.monotonic()
        horizontal = self.config.get("position", "bottom") == "bottom"
        if horizontal:
            x = self.bar_rect.left() + 35 + (math.sin(phase / 6) + 1) * max(0, self.bar_rect.width() - 100) / 2
            y = self.bar_rect.top() - 13 + math.sin(phase * 3) * 1.5
        else: x, y = self.bar_rect.center().x(), self.bar_rect.top() - 15
        painter.save(); painter.translate(x, y)
        if math.cos(phase / 6) < 0: painter.scale(-1, 1)
        color = QColor("#E9B478" if self.config["mascot"] == "cat" else "#B99170")
        painter.setPen(QPen(color, 5, Qt.SolidLine, Qt.RoundCap)); painter.drawLine(QPointF(-12, 3), QPointF(-23, -4 - math.sin(phase * 4) * 6))
        painter.setPen(Qt.NoPen); painter.setBrush(color); painter.drawEllipse(QRectF(-15, -4, 28, 17)); painter.drawEllipse(QRectF(5, -13, 19, 19))
        if self.config["mascot"] == "cat":
            from PySide6.QtGui import QPolygonF
            painter.drawPolygon(QPolygonF([QPointF(5, -7), QPointF(5, -20), QPointF(14, -10)]))
            painter.drawPolygon(QPolygonF([QPointF(16, -10), QPointF(23, -20), QPointF(24, -4)]))
        else:
            painter.setBrush(color.darker(130)); painter.drawEllipse(QRectF(4, -13, 8, 17))
        painter.setBrush(QColor("#283140")); painter.drawEllipse(QPointF(18, -5), 1.5, 1.5); painter.drawEllipse(QPointF(24, -1), 2, 1.5)
        painter.setPen(QPen(color.darker(110), 4, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(QPointF(-8, 8), QPointF(-8 + math.sin(phase * 5) * 3, 15))
        painter.drawLine(QPointF(7, 8), QPointF(7 - math.sin(phase * 5) * 3, 15)); painter.restore()

    def draw_clock(self, painter, rect):
        # Analog face replaces the text in this widget.
        face = QRectF(rect.center().x() - 17, rect.center().y() - 17, 34, 34)
        painter.setBrush(QColor("#EEF2F9")); painter.setPen(Qt.NoPen); painter.drawEllipse(face)
        now = datetime.now(); center = face.center()
        for angle, length, width in (((now.hour % 12 + now.minute / 60) * 30, 9, 2.5), (now.minute * 6, 13, 1.7)):
            rad = math.radians(angle - 90); painter.setPen(QPen(QColor("#243349"), width))
            painter.drawLine(center, QPointF(center.x() + math.cos(rad) * length, center.y() + math.sin(rad) * length))

    def animate(self, dt=None):
        now = time.perf_counter()
        if dt is None:
            dt = now - self._last_animation_at if self.animation.isActive() and self._last_animation_at is not None else 1 / 60
        self._last_animation_at = now
        dt = max(0., min(float(dt), .05))
        blend = -math.expm1(-dt / (.055 if self.pointer is not None else .045))
        previous_bar = QRectF(self.bar_rect)
        for rect in self.rects: previous_bar = previous_bar.united(rect)
        active = False
        for index, (entry, rect) in enumerate(zip(self.entries, self.rects)):
            target = 1.
            motion = self.config.get("motion", "lens")
            if self.pointer is not None and entry["kind"] == "app" and motion != "none":
                distance = abs(self.axis(self.pointer) - self.base_centers[index])
                strength = (1. if index == self.hover else 0.) if motion == "grow" else math.exp(-.5 * (distance / 65) ** 2)
                target += (self.config["magnification"] - 1) * strength
            old = self.scales[index]; self.scales[index] += (target - old) * blend
            if abs(target - self.scales[index]) > .002: active = True
            else: self.scales[index] = target
        self.compute_layout()
        dirty = previous_bar.united(self.bar_rect)
        for rect in self.rects: dirty = dirty.united(rect)
        dirty = dirty.adjusted(-18, -42, 18, 18)
        if self.config.get("position", "bottom") == "bottom":
            dirty.setLeft(0); dirty.setRight(self.width())
        self.update(dirty.toAlignedRect().intersected(self.rect()))
        if any(time.monotonic() - stamp < .7 for stamp in self.bounces.values()): active = True
        if not active:
            self.animation.stop(); self._last_animation_at = None

    def start_animation(self):
        if not self.animation.isActive():
            self._last_animation_at = None
            self.animation.start()

    def hit(self, point):
        return next((i for i, rect in enumerate(self.rects) if rect.contains(point)), -1)

    def mouseMoveEvent(self, event):
        self.last_interaction = time.monotonic()
        if self.folded: self.unfold()
        self.pointer = event.position()
        index = self.hit(self.pointer)
        if index != self.hover:
            self.hover = index; self.hover_timer.start()
            # The painted label already identifies the item; avoid a second tooltip.
            self.setToolTip(self.entries[index]["name"] if index >= 0 and self.config.get("position", "bottom") != "bottom" else "")
        if self.drag_start is not None and event.buttons() & Qt.LeftButton and (event.position().toPoint() - self.drag_start).manhattanLength() > QApplication.startDragDistance():
            if 0 <= self.pressed_index < len(self.entries) and "pinned" in self.entries[self.pressed_index]:
                mime = QMimeData(); mime.setData("application/x-ntdock-index", str(self.entries[self.pressed_index]["pinned"]).encode())
                drag = QDrag(self); drag.setMimeData(mime); drag.exec(Qt.MoveAction)
                self.drag_start = None; self.pressed_index = -1
                return
        self.start_animation()

    def leaveEvent(self, event):
        self.pointer = None; self.hover = -1; self.hover_timer.stop(); self.start_animation()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start = event.position().toPoint(); self.pressed_index = self.hit(event.position())
            self.update()

    def mouseReleaseEvent(self, event):
        index = self.hit(event.position())
        if event.button() == Qt.LeftButton and index == self.pressed_index and index >= 0:
            self.activate_entry(self.entries[index], event.modifiers())
        self.drag_start = None; self.pressed_index = -1
        self.update()

    def wheelEvent(self, event):
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if time.monotonic() - self.last_wheel > .25 and delta:
            step = -1 if delta > 0 else 1
            self.switch_profile((self.config["active"] + step) % len(self.config["profiles"]))
            self.last_wheel = time.monotonic()
        event.accept()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasFormat("application/x-ntdock-index"): event.acceptProposedAction()

    def dragMoveEvent(self, event): event.acceptProposedAction()

    def dropEvent(self, event):
        items = self.profile["items"]
        if event.mimeData().hasFormat("application/x-ntdock-index"):
            try:
                source = int(bytes(event.mimeData().data("application/x-ntdock-index")))
                hit = self.hit(event.position()); target = self.entries[hit].get("pinned", len(items) - 1) if hit >= 0 else len(items) - 1
                if 0 <= source < len(items): items.insert(target, items.pop(source))
            except (ValueError, IndexError): return
        else:
            for url in event.mimeData().urls():
                if len(items) >= MAX_ITEMS:
                    self.notify("Perfil cheio", f"Até {MAX_ITEMS} atalhos por perfil."); break
                target = url.toLocalFile() if url.isLocalFile() else url.toString()
                try: validate_target(target)
                except ValueError: continue
                items.append({"name": Path(target).stem[:60] if url.isLocalFile() else url.host()[:60], "target": target})
        self.persist(); self.rebuild(); event.acceptProposedAction()

    def contextMenuEvent(self, event):
        index = self.hit(event.pos()); menu = self.build_menu()
        if index >= 0:
            entry = self.entries[index]
            if entry["kind"] == "app":
                appmenu = QMenu(self)
                appmenu.addAction("Abrir nova instância", lambda: self.launch(entry["target"]))
                if "://" not in entry["target"]: appmenu.addAction("Mostrar no Explorer", lambda: native.reveal(entry["target"]))
                for record in self.matching(entry):
                    submenu = appmenu.addMenu(record["title"][:60]); submenu.addAction("Ativar", lambda _, r=record: native.activate(r, False)); submenu.addAction("Fechar", lambda _, r=record: native.close_window(r))
                    owners = submenu.addMenu("Atribuir janela ao perfil")
                    owners.addAction("Compartilhar entre perfis", lambda _, r=record: self.assign_window(r, None))
                    for owner, profile in enumerate(self.config["profiles"]): owners.addAction(profile["name"], lambda _, r=record, i=owner: self.assign_window(r, i))
                if "pinned" in entry:
                    appmenu.addAction("Editar atalho…", lambda: self.edit_shortcut(entry["pinned"]))
                    appmenu.addAction("Remover do dock", lambda: self.remove_shortcut(entry["pinned"]))
                else: appmenu.addAction("Fixar neste perfil", lambda: self.pin_app(entry))
                appmenu.addSeparator(); appmenu.addMenu(menu); menu = appmenu
            elif entry["kind"] == "widget":
                widgetmenu = QMenu(self); widgetmenu.addAction("Zerar widget", lambda: self.engine.reset(entry["key"]))
                widgetmenu.addAction("Desafixar", lambda: self.unpin_widget(entry["key"]))
                widgetmenu.addMenu(menu); menu = widgetmenu
        self.busy = True
        try: menu.exec(event.globalPos())
        finally: self.busy = False; menu.deleteLater(); self.last_interaction = time.monotonic()

    def activate_entry(self, entry, modifiers=Qt.NoModifier):
        kind = entry["kind"]
        if kind == "settings": self.settings()
        elif kind == "widgets": self.widgets_panel()
        elif kind == "widget": self.widget_clicked(entry["key"])
        elif kind == "start": native.start_menu()
        elif kind == "system": self.topbar.open_panel(entry["key"])
        elif kind == "trash": QDesktopServices.openUrl(QUrl("shell:RecycleBinFolder"))
        elif kind == "profile":
            if self.config.get("profile_dots", True) and 0 <= self.hover < len(self.rects) and self.pointer is not None:
                points = self.profile_points(self.rects[self.hover])
                owner = min(range(len(points)), key=lambda i: (points[i] - self.pointer).manhattanLength())
                self.switch_profile(owner)
                return
            self.busy = True
            try:
                menu = self.build_menu(); menu.exec(QCursor.pos()); menu.deleteLater()
            finally: self.busy = False
        elif kind == "app":
            target = os.path.expandvars(os.path.expanduser(entry["target"]))
            if modifiers & Qt.ControlModifier and "://" not in target: native.reveal(target); return
            records = self.matching(entry)
            if records and not modifiers & Qt.ShiftModifier:
                cycle = self.window_cycle.get(target, -1) + 1
                self.window_cycle[target] = cycle
                native.activate(records[cycle % len(records)], toggle=len(records) == 1)
            elif Path(target).is_dir() and not modifiers & Qt.ShiftModifier:
                self.config.setdefault("folder_seen", {})[entry["target"]] = time.time()
                self.folder_counts[entry["target"]] = 0; self.persist()
                self.show_popup(FolderStack(target, self))
            else:
                self.launch(target); self.bounces[entry["target"]] = time.monotonic(); self.start_animation()

    def launch(self, target):
        try:
            target = validate_target(target)
            if "://" in target:
                success = QDesktopServices.openUrl(QUrl(target))
                if not success: raise OSError("O navegador não abriu o link.")
            else:
                target = os.path.expandvars(os.path.expanduser(target))
                if not Path(target).exists(): raise FileNotFoundError("Destino não encontrado. Edite o atalho e escolha o caminho deste PC.")
                if native.IS_WINDOWS: os.startfile(target)
                elif not QDesktopServices.openUrl(QUrl.fromLocalFile(target)): raise OSError("Não foi possível abrir o destino.")
        except (ValueError, OSError) as exc: self.notify("Não foi possível abrir", str(exc))

    def show_popup(self, popup):
        if self.popup is not None: self.popup.close()
        self.popup = popup; popup.setAttribute(Qt.WA_DeleteOnClose)
        screen = self.chosen_screen().availableGeometry()
        point = QCursor.pos()
        popup.move(max(screen.left(), min(point.x() - popup.width() // 2, screen.right() - popup.width())), max(screen.top(), min(point.y() - popup.height() - 20, screen.bottom() - popup.height())))
        popup.destroyed.connect(self.popup_closed); popup.show(); popup.raise_()
        if not isinstance(popup, WindowPreviews): popup.activateWindow()

    def popup_closed(self, *_): self.popup = None; self.last_interaction = time.monotonic()

    def preview_hover(self):
        if self.busy or self.popup is not None or self.hover < 0: return
        entry = self.entries[self.hover]
        if entry["kind"] == "app":
            records = self.matching(entry)
            if records: self.show_popup(WindowPreviews(records, self))

    def widgets_panel(self): self.show_popup(WidgetsPanel(self))

    def widget_clicked(self, key):
        if key == "media":
            self.island.set_expanded(True)
            if not self.config.get("island_enabled", False):
                self.config["island_enabled"] = True; self.persist(); self.sync_panels()
            else: self.island.sync()
        elif key == "notes":
            text, ok = QInputDialog.getMultiLineText(self, "Nota rápida", "Texto", str(self.engine.options.get("note", "")))
            if ok:
                self.engine.options["note"] = text[:5000]; self.config["widget_options"] = self.engine.options; self.persist()
        elif key == "calendar":
            from PySide6.QtWidgets import QCalendarWidget
            dialog = QDialog(self, Qt.Tool); dialog.setWindowTitle("Calendário"); layout = QVBoxLayout(dialog); layout.addWidget(QCalendarWidget()); self.show_popup(dialog)
        elif key == "translator":
            if not self.engine.options.get("online"):
                self.notify("Tradução", "Ative os dados online nos ajustes para usar o MyMemory."); return
            text, ok = QInputDialog.getMultiLineText(self, "Traduzir com MyMemory", "O texto será enviado ao MyMemory. Idiomas configurados nos ajustes.")
            if ok and text.strip():
                if len(text.encode("utf-8")) > 500:
                    self.notify("Tradução", "O MyMemory aceita até 500 bytes por consulta. Envie um trecho menor."); return
                from widgets import get_json
                from urllib.parse import urlencode
                query = urlencode({"q": text, "langpair": self.engine.options.get("translate_language", "en|pt")})
                self.engine.request("translation_result", lambda: get_json("https://api.mymemory.translated.net/get?" + query), 0)
                self.notify("Tradução", "Consultando… o resultado aparecerá em uma notificação.")
        elif key == "steam":
            self.engine.value("steam")
            games = self.engine.remote.get("steam", {}).get("response", {}).get("games", [])
            if not games:
                self.notify("Steam", "Configure ID/chave e dados online. A biblioteca também precisa estar visível para a API."); return
            dialog = QDialog(self, Qt.Tool); dialog.setWindowTitle("Biblioteca Steam"); dialog.resize(500, 450)
            layout = QVBoxLayout(dialog); listing = QListWidget(); layout.addWidget(listing)
            for game in sorted(games, key=lambda g: g.get("name", "").casefold()):
                item = QListWidgetItem(f"{game.get('name', 'Jogo')} · {game.get('playtime_forever', 0) / 60:.1f} h")
                item.setData(Qt.UserRole, int(game["appid"])); listing.addItem(item)
            listing.itemDoubleClicked.connect(lambda item: QDesktopServices.openUrl(QUrl(f"steam://rungameid/{item.data(Qt.UserRole)}")))
            layout.addWidget(QLabel("Duplo clique para abrir no Steam instalado.")); self.show_popup(dialog)
        elif key.startswith("custom:") and self.engine.custom.get(key, {}).get("type") == "url": self.launch(self.engine.custom[key]["value"])
        else: self.engine.click(key)
        self.update()

    def pin_widget(self, key):
        chosen = self.profile.setdefault("widgets", list(self.config.get("widgets", [])))
        if key in chosen: return
        if len(chosen) >= 6:
            self.notify("Widgets", "Desafixe um widget para adicionar outro (até seis por perfil)."); return
        chosen.append(key); self.persist(); self.rebuild()

    def unpin_widget(self, key):
        chosen = self.profile.setdefault("widgets", list(self.config.get("widgets", [])))
        if key in chosen: chosen.remove(key)
        self.persist(); self.rebuild()

    def add_shortcut(self):
        if len(self.profile["items"]) >= MAX_ITEMS:
            self.notify("Perfil cheio", f"Até {MAX_ITEMS} atalhos por perfil."); return
        dialog = ShortcutDialog(self)
        self.busy = True
        try:
            if dialog.exec(): self.profile["items"].append(dialog.value); self.persist(); self.rebuild()
        finally: self.busy = False

    def pick_application(self):
        from app_catalog import AppPickerDialog
        if len(self.profile["items"]) >= MAX_ITEMS:
            self.notify("Perfil cheio", f"Até {MAX_ITEMS} atalhos por perfil."); return
        self.busy = True
        try:
            dialog = AppPickerDialog(self, existing_targets=[i["target"] for i in self.profile["items"]])
            if dialog.exec():
                self.profile["items"].append(dialog.value); self.persist(); self.rebuild()
        finally: self.busy = False

    def edit_shortcut(self, index):
        dialog = ShortcutDialog(self, self.profile["items"][index])
        if dialog.exec(): self.profile["items"][index] = dialog.value; self.persist(); self.icons.clear(); self.rebuild()

    def remove_shortcut(self, index):
        del self.profile["items"][index]; self.persist(); self.rebuild()

    def pin_app(self, entry):
        if len(self.profile["items"]) < MAX_ITEMS:
            self.profile["items"].append({"name": entry["name"], "target": entry["target"]}); self.persist(); self.rebuild()

    def settings(self):
        self.busy = True
        if self.popup is not None: self.popup.close()
        try:
            dialog = SettingsDialog(self.config, self.engine, self)
            if dialog.exec():
                self.appbar.remove(); self.restore_windows(); self.reservation_signature = None; self.config = dialog.value
                self.engine.options = self.config.get("widget_options", {})
                self.engine.remote.clear(); self.engine.last.clear(); self.engine.pending.clear(); self.icons.clear(); self.exe_cache.clear()
                self.engine.load_custom(config_path().parent / "widgets")
                if self.config.get("mascot", "none") == "none": self.pet_timer.stop()
                else: self.pet_timer.start()
                self.tray.setContextMenu(self.build_menu()); self.rebuild(); self.apply_system(); self.place()
                self.sync_panels()
        finally: self.busy = False; self.last_interaction = time.monotonic()

    def switch_profile(self, index):
        if not 0 <= index < len(self.config["profiles"]) or index == self.config["active"]: return
        if self.config.get("isolate_profiles") and self.recovery:
            self.isolate_windows(index)
        self.config["active"] = index
        self.running = native.windows(); self.persist(); self.rebuild()
        self.tray.setContextMenu(self.build_menu()); self.unfold()
        self.sync_panels()

    @staticmethod
    def window_key(record): return record["hwnd"], record["pid"], record["created"]

    def assign_window(self, record, owner):
        self.window_owners[self.window_key(record)] = owner
        self.config["isolate_profiles"] = True
        self.persist(); self.isolate_windows(self.config["active"])

    def isolate_windows(self, active):
        if not self.recovery: return
        exe_owners = {}
        for owner, profile in enumerate(self.config["profiles"]):
            for item in profile["items"]:
                if "://" not in item["target"]: exe_owners.setdefault(self.exe_key(item["target"]), set()).add(owner)
        records = {self.window_key(r): r for r in native.windows() + list(self.recovery.records)}
        for key, record in records.items():
            owners = exe_owners.get(os.path.normcase(record.get("exe", "")), set())
            owner = self.window_owners[key] if key in self.window_owners else (next(iter(owners)) if len(owners) == 1 else None)
            if owner is not None and owner != active: self.recovery.hide(record)
            elif record in self.recovery.records: self.recovery.show(record)

    def refresh_folders(self):
        for target, future in list(self.folder_futures.items()):
            if future.done():
                try:
                    value = future.result()
                    if self.config.get("folder_seen", {}).get(target, self.started) == self.folder_cutoffs.get(target): self.folder_counts[target] = value
                except OSError: self.folder_counts[target] = 0
                del self.folder_futures[target]
        if time.monotonic() - self.last_folder_check < 5: return
        self.last_folder_check = time.monotonic()
        for item in self.profile["items"]:
            target = item["target"]
            path = os.path.expandvars(os.path.expanduser(target))
            if not item.get("track_new") and Path(path).name.casefold() not in ("downloads", "transferências", "descargas"): continue
            if target in self.folder_futures: continue
            seen = self.config.get("folder_seen", {}).get(target, self.started)
            self.folder_cutoffs[target] = seen
            def count_new(folder=path, since=seen):
                count = 0
                with os.scandir(folder) as entries:
                    for entry in entries:
                        try:
                            stat = entry.stat()
                            if entry.is_file() and getattr(stat, "st_birthtime", stat.st_ctime) > since: count += 1
                        except OSError: continue
                return count
            self.folder_futures[target] = self.engine.pool.submit(count_new)

    def reserve(self):
        if self.manual_hidden:
            self.appbar.remove(); self.reservation_signature = None
            return
        area = self.chosen_screen().geometry()
        signature = (area.x(), area.y(), area.width(), area.height(), self.chosen_screen().devicePixelRatio(), self.config.get("position"), self.config.get("reserve_space", True), self.config.get("auto_hide"), self.config["icon_size"], self.config.get("bar_padding", 7))
        if signature == self.reservation_signature: return
        self.reservation_signature = signature
        self.appbar.remove()
        if self.config.get("reserve_space", True) and not self.config.get("auto_hide") and not self.test_mode:
            self.native_screen_rect = native.monitor_rect(int(self.winId())) or (area.x(), area.y(), area.width(), area.height())
            thickness = max(self.config["icon_size"], 32) + self.config.get("bar_padding", 7) + 24
            self.appbar.reserve(int(self.winId()), self.native_screen_rect, self.config.get("position", "bottom"), round(thickness * self.chosen_screen().devicePixelRatio()))
        if self.recovery: self.recovery.maintain_bars(self.appbar)
        self.place()

    def appbar_changed(self):
        if self.appbar.reposition(): self.place()

    def apply_system(self):
        if self.recovery:
            self.recovery.restore_bars()
            if self.config.get("replace_taskbar"): self.recovery.hide_bars()
        self.reserve()
        # Explorer/Qt can publish the new work area asynchronously. Reposition
        # after the shell settles; never block the GUI waiting for it.
        if not self.test_mode:
            QTimer.singleShot(250, self.shell_area_changed)
            QTimer.singleShot(1000, self.shell_area_changed)

    def shell_area_changed(self):
        if self.manual_hidden:
            return
        self.appbar_changed()
        if self.recovery: self.recovery.maintain_bars(self.appbar)
        self.place()

    def restore_windows(self):
        if self.bottom_corners: self.bottom_corners.clear()
        if self.recovery: self.recovery.restore()
        self.records_by_profile.clear()
        self.window_owners.clear()

    def toggle_visibility(self):
        self.manual_hidden = not self.manual_hidden
        self.sync_panels()
        if self.manual_hidden:
            if self.bottom_corners: self.bottom_corners.clear()
            self.appbar.remove(); self.reservation_signature = None
            if self.recovery: self.recovery.restore_bars()
            self.hide()
        else:
            if self.recovery and self.config.get("replace_taskbar"): self.recovery.hide_bars()
            self.show(); self.unfold(); self.place(); self.reserve()
            if not self.test_mode:
                QTimer.singleShot(250, self.shell_area_changed)

    def unfold(self):
        self.folded = False; self.last_interaction = time.monotonic(); self.update()

    def edge_tick(self):
        if self.manual_hidden or not self.config.get("auto_hide") or self.busy or self.popup is not None: return
        cursor = QCursor.pos(); position = self.config.get("position", "bottom"); screen = self.chosen_screen().geometry()
        edge = (cursor.y() >= screen.bottom() - 4) if position == "bottom" else ((cursor.x() <= screen.left() + 4) if position == "left" else (cursor.x() >= screen.right() - 4))
        if screen.contains(cursor) and edge: self.unfold()
        elif not self.geometry().contains(cursor) and time.monotonic() - self.last_interaction > .8:
            self.folded = True; self.pointer = None; self.hover = -1; self.update()

    def tick(self):
        try:
            if self.recovery and not self.manual_hidden: self.recovery.maintain_bars(self.appbar)
            focus_done, timer_done = self.engine.sample()
            if focus_done:
                self.notify("Pomodoro", f"Hora de {self.engine.pomodoro.phase.lower()}. Clique no widget para iniciar."); QApplication.beep()
            if timer_done:
                self.engine.timer.reset(); self.engine.timer.remaining = max(1, int(self.engine.options.get("timer_minutes", 5))) * 60
                self.notify("Temporizador", "Tempo encerrado."); QApplication.beep()
            if "translation_result" in self.engine.remote:
                data = self.engine.remote.pop("translation_result")
                text = data.get("responseData", {}).get("translatedText", "Sem resultado")
                self.notify("Tradução", text)
                dialog = QDialog(self, Qt.Tool); dialog.setWindowTitle("Tradução"); dialog.resize(500, 300)
                layout = QVBoxLayout(dialog); textedit = QTextEdit(); textedit.setReadOnly(True); textedit.setPlainText(text); layout.addWidget(textedit); self.show_popup(dialog)
            if "translation_result" in self.engine.errors:
                self.engine.errors.pop("translation_result")
                self.notify("Tradução", "A consulta falhou. Verifique a conexão ou tente mais tarde.")
            self.running = native.windows()
            if not self.test_mode:
                fit_maximized(self.running, self.recovery.corner_records if self.recovery else ())
                if self.bottom_corners:
                    self.bottom_corners.sync(self.running, self.config.get("rounded_windows", False) and not self.manual_hidden)
            if self.config.get("isolate_profiles") and self.recovery:
                self.isolate_windows(self.config["active"]); self.running = native.windows()
            self.refresh_folders()
            if self.config.get("follow_desktop"):
                desktop = native.desktop_id()
                if desktop and desktop != self.last_desktop:
                    self.last_desktop = desktop
                    for index, profile in enumerate(self.config["profiles"]):
                        if profile.get("desktop_id") == desktop: self.switch_profile(index); break
            self.rebuild()
            self.sync_panels()
            if not self.test_mode:
                try: battery = __import__("psutil").sensors_battery()
                except (OSError, AttributeError, NotImplementedError): battery = None
                for event in self.desktop_events.poll(self.config, battery, self.media.snapshot().get("volume")):
                    self.island.notify(event["title"], event["text"], event.get("path"))
        except Exception:
            logging.exception("Falha ao atualizar dock")

    def quit(self):
        self.shutdown_services()
        self.appbar.remove(); self.restore_windows()
        if self.hotkeys: self.hotkeys.close()
        self.engine.close(); self.tray.hide(); QApplication.instance().quit()

    def closeEvent(self, event):
        self.quit(); event.accept()


def main():
    app = QApplication(sys.argv); app.setApplicationName("NT Dock"); app.setOrganizationName("NTHub")
    app.setStyle("Fusion"); app.setStyleSheet(STYLE); app.setQuitOnLastWindowClosed(False)
    directory = config_path().parent; directory.mkdir(parents=True, exist_ok=True)
    examples = Path(__file__).with_name("example-widgets")
    custom_directory = directory / "widgets"
    if not custom_directory.exists() and examples.is_dir():
        import shutil
        shutil.copytree(examples, custom_directory)
    from logging.handlers import RotatingFileHandler
    handler = RotatingFileHandler(directory / "ntdock.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")
    socket = QLocalSocket(); socket.connectToServer("NTDock-" + str(os.getuid() if hasattr(os, "getuid") else os.environ.get("USERNAME", "user")))
    if socket.waitForConnected(250):
        socket.write(b"show"); socket.waitForBytesWritten(250); return 0
    server_name = socket.serverName(); QLocalServer.removeServer(server_name)
    server = QLocalServer()
    if not server.listen(server_name):
        QMessageBox.warning(None, "NT Dock", "Não foi possível criar o canal de instância única."); return 1
    config, warning = load_config()
    dock = Dock(config); dock.show()
    app.aboutToQuit.connect(dock.shutdown_services)
    app.aboutToQuit.connect(dock.restore_windows)
    app.aboutToQuit.connect(dock.appbar.remove)
    def wake():
        connection = server.nextPendingConnection()
        if connection: connection.disconnectFromServer(); connection.deleteLater()
        if dock.manual_hidden: dock.toggle_visibility()
        else: dock.show(); dock.unfold()
        dock.raise_()
    server.newConnection.connect(wake)
    if warning: QTimer.singleShot(500, lambda: dock.notify("Configuração", warning))
    if dock.hotkeys and len(dock.hotkeys.ids) != 10:
        QTimer.singleShot(1500, lambda: dock.notify("Atalhos globais", "Alguns atalhos estão em uso por outro aplicativo. Consulte ntdock.log."))
    return app.exec()


if __name__ == "__main__":
    try: raise SystemExit(main())
    except Exception:
        logging.exception("Falha ao iniciar")
        raise
