"""Installed application shortcuts and a non-blocking picker for the current profile.

Only the two Start Menu trees are scanned. Shortcuts are read, never executed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import sys

from PySide6.QtCore import QFileInfo, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QFileDialog, QFileIconProvider, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
    QVBoxLayout,
)

from core import validate_target


_EXCLUDED = re.compile(
    r"(?:^|[\s_.()\-])(?:uninstall(?:er)?|desinstalar|desinstalador|update(?:r)?|"
    r"atualizador|atualizar|help|ajuda|readme|manual|documentation|documentação)(?:$|[\s_.()\-])",
    re.IGNORECASE,
)


def _path_key(path):
    return os.path.normcase(os.path.abspath(os.path.expandvars(os.path.expanduser(str(path))))).casefold()


def _start_menu_roots():
    roots = []
    for variable in ("APPDATA", "PROGRAMDATA"):
        base = os.environ.get(variable)
        if base:
            roots.append(Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return roots


def _shortcut_paths(roots):
    examined = 0
    for root in roots:
        pending = [(Path(root), 0)]
        while pending and examined < 5000:
            directory, depth = pending.pop()
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        examined += 1
                        if examined > 5000:
                            return
                        # Junctions can lead outside the selected Start Menu tree.
                        if entry.is_symlink() or getattr(entry.stat(follow_symlinks=False), "st_file_attributes", 0) & 0x400:
                            continue
                        if entry.is_dir(follow_symlinks=False) and depth < 6:
                            pending.append((Path(entry.path), depth + 1))
                        elif entry.is_file(follow_symlinks=False) and entry.name.casefold().endswith(".lnk"):
                            yield Path(entry.path)
            except OSError:
                continue


def installed_apps(roots=None, *, resolver=None, include_system=True):
    """Return ``{name, target}`` entries; ``target`` remains the original .lnk.

    Keeping the shortcut preserves its arguments and working directory. A missing
    resolved local executable is excluded; unresolved/UWP shortcuts remain usable.
    ``roots`` and ``resolver`` allow deterministic inventory tests without COM.
    """
    roots = _start_menu_roots() if roots is None else roots
    uninitialize = None
    if resolver is None and sys.platform == "win32":
        try:
            import comtypes
            from comtypes.client import CreateObject
            comtypes.CoInitialize()
            uninitialize = comtypes.CoUninitialize
            shell = CreateObject("WScript.Shell", dynamic=True)
            resolver = lambda path: shell.CreateShortcut(str(path)).TargetPath
        except Exception:
            # An unreadable shortcut is not evidence that its application is gone.
            resolver = None
    records, seen_names, seen_targets = [], set(), set()
    try:
        for path in sorted(_shortcut_paths(roots), key=lambda p: (len(p.stem), str(p).casefold())):
            name = path.stem.strip()
            if not name or _EXCLUDED.search(name):
                continue
            target_key = _path_key(path)
            if resolver is not None:
                try:
                    resolved = resolver(path)
                    if isinstance(resolved, str) and resolved.strip():
                        destination = Path(os.path.expandvars(os.path.expanduser(resolved.strip())))
                        if destination.is_absolute():
                            if not destination.is_file() or destination.suffix.casefold() != ".exe":
                                continue
                            target_key = _path_key(destination)
                except Exception:
                    pass
            name_key = name.casefold()
            if name_key in seen_names or target_key in seen_targets:
                continue
            seen_names.add(name_key); seen_targets.add(target_key)
            records.append({"name": name[:60], "target": str(path.absolute())})
        if include_system:
            windows = os.environ.get("WINDIR")
            if windows:
                for name, relative in (("Explorador de Arquivos", "explorer.exe"), ("Bloco de Notas", "System32/notepad.exe"), ("Calculadora", "System32/calc.exe")):
                    path = Path(windows) / relative
                    key = _path_key(path)
                    if path.is_file() and key not in seen_targets and name.casefold() not in seen_names:
                        records.append({"name": name, "target": str(path)})
                        seen_targets.add(key); seen_names.add(name.casefold())
        return sorted(records, key=lambda item: item["name"].casefold())
    finally:
        if uninitialize is not None:
            uninitialize()


class AppPickerDialog(QDialog):
    """Choose one installed application; accepted dialogs expose ``value``."""
    def __init__(self, parent=None, existing_targets=()):
        super().__init__(parent)
        self.value = None
        self._closed = False
        self._existing = {_path_key(target) for target in existing_targets}
        self._records = []
        self._loaded = 0
        self._provider = QFileIconProvider()
        self.setWindowTitle("Adicionar aplicativo · NT Dock")
        self.resize(580, 540)
        self.setMinimumSize(430, 380)
        layout = QVBoxLayout(self); layout.setSpacing(12)
        title = QLabel("Seus aplicativos")
        title.setStyleSheet("font-size:23px;font-weight:600;padding-top:8px")
        layout.addWidget(title)
        description = QLabel("Escolha um app para fixar no ambiente atual. Você também pode arrastar um atalho para o dock.")
        description.setWordWrap(True); layout.addWidget(description)
        self.search = QLineEdit(); self.search.setPlaceholderText("Buscar aplicativo…")
        self.search.setClearButtonEnabled(True); layout.addWidget(self.search)
        self.list = QListWidget(); self.list.setIconSize(QSize(32, 32)); self.list.setSpacing(3)
        layout.addWidget(self.list, 1)
        self.status = QLabel("Buscando aplicativos do menu Iniciar…"); layout.addWidget(self.status)
        footer = QHBoxLayout()
        browse = QPushButton("Escolher arquivo…"); browse.clicked.connect(self.browse)
        footer.addWidget(browse); footer.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.add_button = buttons.button(QDialogButtonBox.Ok); self.add_button.setText("Fixar aplicativo")
        self.add_button.setEnabled(False)
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.choose); buttons.rejected.connect(self.reject)
        footer.addWidget(buttons); layout.addLayout(footer)
        self.search.textChanged.connect(self.filter)
        self.list.itemSelectionChanged.connect(self.selection_changed)
        self.list.itemDoubleClicked.connect(lambda _: self.choose())
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ntdock-apps")
        self._future = self._pool.submit(installed_apps)
        self._timer = QTimer(self); self._timer.setInterval(30); self._timer.timeout.connect(self.populate)
        self._timer.start()
        self.finished.connect(self._shutdown)

    def populate(self):
        if self._closed or not self._future.done():
            return
        if not self._records and self._loaded == 0:
            try:
                self._records = self._future.result()
            except Exception:
                self.status.setText("Não foi possível ler o menu Iniciar. Use Escolher arquivo…")
                self._timer.stop(); return
        end = min(self._loaded + 12, len(self._records))
        for record in self._records[self._loaded:end]:
            pinned = _path_key(record["target"]) in self._existing
            item = QListWidgetItem(self._provider.icon(QFileInfo(record["target"])), record["name"] + ("  ·  Já fixado" if pinned else ""))
            item.setData(Qt.UserRole, record); item.setToolTip(record["target"])
            if pinned:
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            self.list.addItem(item)
        self._loaded = end
        self.filter(self.search.text())
        if end == len(self._records):
            self._timer.stop()
            if self._records:
                self.filter(self.search.text())
            else:
                self.status.setText("Nenhum atalho encontrado. Use Escolher arquivo…")

    def filter(self, text):
        text = text.strip().casefold(); visible = 0
        for index in range(self.list.count()):
            item = self.list.item(index)
            match = text in item.data(Qt.UserRole)["name"].casefold()
            item.setHidden(not match); visible += int(match)
        self.status.setText(f"{visible} aplicativo(s)" + (" · carregando…" if self._timer.isActive() else ""))
        self.selection_changed()

    def selection_changed(self):
        item = self.list.currentItem()
        self.add_button.setEnabled(bool(item and not item.isHidden() and item.flags() & Qt.ItemIsEnabled))

    def choose(self):
        item = self.list.currentItem()
        if item is None or item.isHidden() or not item.flags() & Qt.ItemIsEnabled:
            return
        self.value = dict(item.data(Qt.UserRole)); self.accept()

    def browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Escolher aplicativo", "", "Aplicativos e atalhos (*.exe *.lnk)")
        if not path:
            return
        try:
            target = validate_target(path)
            if Path(target).suffix.casefold() not in (".exe", ".lnk") or not Path(target).is_file():
                raise ValueError("Selecione um aplicativo .exe ou um atalho .lnk existente.")
            if _path_key(target) in self._existing:
                raise ValueError("Este aplicativo já está fixado no ambiente atual.")
            self.value = {"name": Path(target).stem[:60], "target": target}
            self.accept()
        except ValueError as exc:
            QMessageBox.warning(self, "Confira o aplicativo", str(exc))

    def _shutdown(self, *_):
        if not self._closed:
            self._closed = True; self._timer.stop()
            self._pool.shutdown(wait=False, cancel_futures=True)
