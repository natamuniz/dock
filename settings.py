"""Transactional settings editor: changes apply only after Save."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
    QGridLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QScrollArea, QSlider, QSpinBox, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from appearance import DOCK_FINISH, PRESETS, TOPBAR_FONTS, palette
from core import MAX_ITEMS, save_config, validate_config, validate_target
import native


def theme_swatch(values):
    pixmap = QPixmap(120, 38); pixmap.fill(QColor("#6282A0"))
    painter = QPainter(pixmap); painter.setRenderHint(QPainter.Antialiasing)
    gradient = QLinearGradient(0, 12, 0, 34)
    gradient.setColorAt(0, QColor(values["top"])); gradient.setColorAt(1, QColor(values["bottom"]))
    painter.setBrush(gradient); painter.setPen(QColor(values["border"]))
    painter.drawRoundedRect(QRectF(6, 11, 108, 23), 7, 7)
    painter.setPen(Qt.NoPen)
    for index, color in enumerate(("#F5B84B", "#4B9BD8", "#6CC9A7", "#DC799C", "#9D8DDC")):
        painter.setBrush(QColor(color)); painter.drawRoundedRect(QRectF(17 + index * 18, 15, 14, 14), 4, 4)
    painter.end()
    return QIcon(pixmap)


class ShortcutDialog(QDialog):
    def __init__(self, parent=None, item=None):
        super().__init__(parent)
        self.setWindowTitle("Atalho")
        self.setMinimumWidth(520)
        form = QFormLayout(self)
        self.name = QLineEdit((item or {}).get("name", ""))
        self.target = QLineEdit((item or {}).get("target", ""))
        form.addRow("Nome", self.name)
        form.addRow("Destino", self.target)
        self.icon_path = QLineEdit((item or {}).get("icon", ""))
        icon_row = QHBoxLayout(); icon_row.addWidget(self.icon_path)
        icon_button = QPushButton("Escolher ícone"); icon_button.clicked.connect(self.browse_icon); icon_row.addWidget(icon_button)
        form.addRow("Ícone (opcional)", icon_row)
        self.track_new = QCheckBox("Mostrar contagem de arquivos novos nesta pasta")
        self.track_new.setChecked(bool((item or {}).get("track_new", False)))
        form.addRow(self.track_new)
        row = QHBoxLayout()
        for label, folder in (("Escolher aplicativo/arquivo", False), ("Escolher pasta", True)):
            button = QPushButton(label)
            button.clicked.connect(lambda _, f=folder: self.browse(f))
            row.addWidget(button)
        form.addRow(row)
        form.addRow(QLabel("Aceita .exe, .lnk, pastas, documentos e links http/https. Sem comandos de terminal."))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Salvar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.check)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def browse(self, folder):
        path = QFileDialog.getExistingDirectory(self, "Pasta") if folder else QFileDialog.getOpenFileName(self, "Aplicativo ou arquivo")[0]
        if path:
            self.target.setText(path)
            if not self.name.text().strip(): self.name.setText(Path(path).stem)

    def browse_icon(self):
        path = QFileDialog.getOpenFileName(self, "Ícone", "", "Ícones (*.png *.ico *.jpg *.webp *.svg)")[0]
        if path: self.icon_path.setText(path)

    def check(self):
        try:
            target = validate_target(self.target.text())
            name = self.name.text().strip()
            if not 1 <= len(name) <= 60: raise ValueError("Nome: de 1 a 60 caracteres.")
            self.value = {"name": name, "target": target}
            if self.track_new.isChecked(): self.value["track_new"] = True
            if self.icon_path.text().strip():
                icon = validate_target(self.icon_path.text())
                if "://" in icon: raise ValueError("O ícone deve ser um arquivo local.")
                self.value["icon"] = icon
            self.accept()
        except ValueError as exc:
            QMessageBox.warning(self, "Confira o atalho", str(exc))


class SettingsDialog(QDialog):
    def __init__(self, config, engine, parent=None):
        super().__init__(parent)
        self.config = copy.deepcopy(config)
        self.engine = engine
        self.current = -1
        self.setWindowTitle("NT Dock · Ajustes")
        screen = parent.chosen_screen() if parent is not None and hasattr(parent, "chosen_screen") else QApplication.primaryScreen()
        available_height = screen.availableGeometry().height() if screen is not None else 754
        self.resize(960, max(560, min(690, available_height - 64)))
        self.setMinimumSize(820, 560)
        root = QVBoxLayout(self)
        title = QLabel("NT Dock <span style='font-size:14px;font-weight:400;color:#A3B1C2'> / Ajustes</span>")
        title.setStyleSheet("font-size:24px;font-weight:600;padding:8px")
        root.addWidget(title)
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        self.navigation = QListWidget(); self.navigation.setFixedWidth(175)
        self.navigation.setStyleSheet("QListWidget {background:#1B2029;border:0;padding:8px;} QListWidget::item {padding:14px 8px;border-radius:8px;} QListWidget::item:selected {background:#314B60;color:#F4FBFF;}")
        body = QHBoxLayout(); body.setSpacing(14); body.addWidget(self.navigation); body.addWidget(self.tabs, 1)
        root.addLayout(body, 1)
        self.make_profiles()
        self.make_appearance()
        self.make_panels()
        self.make_options()
        self.update_color_previews()
        for index in range(self.tabs.count()): self.navigation.addItem(self.tabs.tabText(index))
        self.navigation.currentRowChanged.connect(self.tabs.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        footer = QHBoxLayout()
        for label, callback in (("Exportar configuração", self.export_config), ("Importar", self.import_config)):
            button = QPushButton(label); button.clicked.connect(callback); footer.addWidget(button)
        footer.addStretch()
        self.startup = QCheckBox("Iniciar com o Windows")
        self.startup.setChecked(native.autostart_enabled())
        self.startup.setEnabled(native.IS_WINDOWS)
        footer.addWidget(self.startup)
        root.addLayout(footer)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Salvar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.check)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.profiles.setCurrentRow(self.config["active"])

    def make_profiles(self):
        tab = QWidget(); layout = QHBoxLayout(tab)
        left = QVBoxLayout()
        self.profiles = QListWidget()
        self.profiles.addItems([p["name"] for p in self.config["profiles"]])
        self.profiles.setMaximumWidth(200)
        self.profiles.currentRowChanged.connect(self.select_profile)
        left.addWidget(self.profiles)
        for title, callback in (("Novo perfil", self.add_profile), ("Excluir perfil", self.remove_profile)):
            button = QPushButton(title); button.clicked.connect(callback); left.addWidget(button)
        layout.addLayout(left)
        right = QVBoxLayout()
        form = QFormLayout()
        self.profile_name = QLineEdit()
        self.color = QPushButton("Cor do perfil")
        self.color.clicked.connect(self.pick_color)
        form.addRow("Nome", self.profile_name); form.addRow("Cor", self.color)
        self.desktop = QLabel()
        bind = QPushButton("Vincular à área de trabalho atual")
        bind.setEnabled(native.IS_WINDOWS)
        bind.clicked.connect(self.bind_desktop)
        unbind = QPushButton("Desvincular")
        unbind.clicked.connect(lambda: self.desktop.setText(""))
        form.addRow(bind, unbind); form.addRow("ID da área", self.desktop)
        right.addLayout(form)
        right.addWidget(QLabel(f"Atalhos · arraste para reordenar · até {MAX_ITEMS} por perfil"))
        self.items = QListWidget(); self.items.setDragDropMode(QAbstractItemView.InternalMove)
        self.items.itemDoubleClicked.connect(lambda _: self.edit_item())
        right.addWidget(self.items)
        actions = QHBoxLayout()
        for title, callback in (("Adicionar", self.add_item), ("Editar", self.edit_item), ("Remover", lambda: self.items.takeItem(self.items.currentRow()))):
            button = QPushButton(title); button.clicked.connect(callback); actions.addWidget(button)
        right.addLayout(actions)
        installed = QPushButton("Escolher entre os aplicativos instalados…")
        installed.clicked.connect(self.add_installed_app); right.addWidget(installed)
        right.addWidget(QLabel("Widgets neste perfil · até seis no dock; catálogo no menu do dock"))
        self.widget_list = QListWidget(); self.widget_list.setMaximumHeight(155)
        for key, (label, glyph) in self.engine.catalog().items():
            item = QListWidgetItem(f"{glyph}  {label}")
            item.setData(Qt.UserRole, key); item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked); self.widget_list.addItem(item)
        right.addWidget(self.widget_list)
        layout.addLayout(right, 1)
        self.tabs.addTab(tab, "Seu dock")

    def make_appearance(self):
        tab = QWidget(); form = QFormLayout(tab); form.setSpacing(14)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.addRow(QLabel("<h2>Aparência</h2>Temas, proporções e movimento do dock."))
        self.theme = QComboBox(); self.theme.addItem("Vidro escuro", "dark"); self.theme.addItem("Vidro claro", "light")
        self.theme.setCurrentIndex(self.theme.findData(self.config.get("theme", "dark")))
        self.preset = QComboBox(); self.preset.addItem("Manter aparência anterior", "")
        self.theme_buttons = QButtonGroup(self); self.theme_buttons.setExclusive(True)
        cards = QGridLayout(); cards.setSpacing(8)
        for index, (key, values) in enumerate(PRESETS.items()):
            self.preset.addItem(values["name"], key)
            button = QToolButton(); button.setText(values["name"]); button.setIcon(theme_swatch(values))
            button.setIconSize(QSize(120, 38)); button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setCheckable(True); button.setMinimumSize(126, 72)
            button.setStyleSheet("QToolButton {background:#292F3A;color:#EDF4FA;border:1px solid #3B4553;border-radius:10px;padding:6px;} QToolButton:hover {border-color:#7094AF;} QToolButton:checked {background:#263F51;border:2px solid #6BB6DE;}")
            button.clicked.connect(lambda _, k=key: self.preset.setCurrentIndex(self.preset.findData(k)))
            self.theme_buttons.addButton(button, index)
            cards.addWidget(button, index // 4, index % 4)
        self.preset.currentIndexChanged.connect(self.select_theme)
        self.preset.setCurrentIndex(max(0, self.preset.findData(self.config.get("appearance_preset", ""))))
        self.select_theme()
        form.addRow(cards)
        form.addRow("Tema", self.preset)
        dock_color_row, self.dock_color = self.color_editor("dock_color", "", "dock")
        form.addRow("Cor do dock", dock_color_row)
        self.dock_preview = QLabel("Prévia do dock"); self.dock_preview.setAlignment(Qt.AlignCenter)
        form.addRow(self.dock_preview)
        self.finish_controls = {}
        for key, (label, minimum, maximum, suffix) in DOCK_FINISH.items():
            control = QSpinBox()
            control.setRange(minimum, maximum)
            control.setSuffix(suffix)
            if minimum == -1:
                control.setSpecialValueText("Do tema")
            control.setValue(self.config.get(key, 1 if key == "dock_border" else minimum))
            control.valueChanged.connect(self.update_color_previews)
            self.finish_controls[key] = control
            form.addRow(label, control)
        self.dock_reflection = QCheckBox("Reflexo na metade superior")
        self.dock_reflection.setChecked(self.config.get("dock_reflection", False))
        self.dock_reflection.toggled.connect(self.update_color_previews)
        form.addRow(self.dock_reflection)
        self.app_indicator = QComboBox()
        self.app_indicator.addItem("Ponto", "dot")
        self.app_indicator.addItem("Traço", "dash")
        self.app_indicator.setCurrentIndex(self.app_indicator.findData(self.config.get("app_indicator", "dot")))
        form.addRow("Sinal de app aberto", self.app_indicator)
        self.trash_style = QComboBox()
        for label, key in (("Windows", "windows"), ("Cartão", "tile"), ("Minimalista", "outline")):
            self.trash_style.addItem(label, key)
        self.trash_style.setCurrentIndex(self.trash_style.findData(self.config.get("trash_style", "windows")))
        form.addRow("Estilo da Lixeira", self.trash_style)
        reset = QPushButton("Restaurar acabamento do tema")
        reset.clicked.connect(self.reset_dock_finish)
        form.addRow(reset)
        self.preset.currentIndexChanged.connect(self.update_color_previews)
        form.addRow("Claro ou escuro", self.theme)
        legacy_label = form.labelForField(self.theme)
        def show_legacy_theme():
            visible = not self.preset.currentData()
            self.theme.setVisible(visible); legacy_label.setVisible(visible)
        self.preset.currentIndexChanged.connect(show_legacy_theme)
        show_legacy_theme()
        self.size = QSlider(Qt.Horizontal); self.size.setRange(32, 64); self.size.setValue(int(self.config["icon_size"]))
        self.size_label = QLabel(); self.size.valueChanged.connect(lambda value: self.size_label.setText(f"{value} px"))
        self.size_label.setText(f"{self.size.value()} px")
        size_row = QHBoxLayout(); size_row.addWidget(self.size); size_row.addWidget(self.size_label)
        form.addRow("Tamanho dos ícones", size_row)
        self.padding = QSlider(Qt.Horizontal); self.padding.setRange(0, 16); self.padding.setValue(self.config.get("bar_padding", 7))
        self.padding_label = QLabel(f"{self.padding.value()} px")
        self.padding.valueChanged.connect(lambda value: self.padding_label.setText(f"{value} px"))
        padding_row = QHBoxLayout(); padding_row.addWidget(self.padding); padding_row.addWidget(self.padding_label)
        form.addRow("Folga da barra", padding_row)
        self.motion = QComboBox()
        for title, key in (("Nenhum", "none"), ("Crescer · só o ícone sob o mouse", "grow"), ("Lente · ícone e vizinhos", "lens")): self.motion.addItem(title, key)
        self.motion.setCurrentIndex(self.motion.findData(self.config.get("motion", "lens")))
        form.addRow("Ao passar o mouse", self.motion)
        self.zoom = QDoubleSpinBox(); self.zoom.setRange(1, 2); self.zoom.setSingleStep(.05); self.zoom.setDecimals(2); self.zoom.setValue(self.config["magnification"])
        form.addRow("Ampliação", self.zoom)
        self.launch_animation = QComboBox()
        for title, key in (("Nenhuma", "none"), ("Pulo", "bounce"), ("Pulso", "pulse"), ("Tremor", "shake")): self.launch_animation.addItem(title, key)
        self.launch_animation.setCurrentIndex(self.launch_animation.findData(self.config.get("launch_animation", "bounce")))
        form.addRow("Ao abrir um aplicativo", self.launch_animation)
        self.widget_style = QComboBox(); self.widget_style.addItem("Vidro", "glass"); self.widget_style.addItem("Cores vivas", "color")
        self.widget_style.setCurrentIndex(self.widget_style.findData(self.config.get("widget_style", "glass")))
        form.addRow("Estilo dos widgets", self.widget_style)
        self.flags = {}
        for key, label, default in (
            ("blur", "Usar fundo translúcido", True),
            ("colored_indicators", "Pontinho dos apps na cor do ambiente", True),
            ("profile_dots", "Mostrar pontinhos dos ambientes no fim do dock", True),
            ("show_trash", "Mostrar Lixeira", True),
            ("show_settings", "Mostrar botão de Ajustes", True),
            ("show_start", "Mostrar botão Iniciar", False),
        ):
            check = QCheckBox(label); check.setChecked(self.config.get(key, default)); self.flags[key] = check; form.addRow(check)
        self.mascot = QComboBox()
        for title, key in (("Sem personagem", "none"), ("Gato", "cat"), ("Cão", "dog")): self.mascot.addItem(title, key)
        self.mascot.setCurrentIndex(self.mascot.findData(self.config.get("mascot", "none")))
        form.addRow("Personagem animado", self.mascot)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame); scroll.setWidget(tab)
        self.tabs.addTab(scroll, "Aparência")

        tab = QWidget(); form = QFormLayout(tab); form.setSpacing(16)
        form.addRow(QLabel("<h2>Posição e Windows</h2>Escolha a borda e como o dock divide a tela."))
        self.position = QComboBox()
        for title, key in (("Embaixo", "bottom"), ("À esquerda", "left"), ("À direita", "right")): self.position.addItem(title, key)
        self.position.setCurrentIndex(self.position.findData(self.config.get("position", "bottom")))
        self.monitor = QComboBox(); self.monitor.addItem("Monitor principal", "")
        from PySide6.QtWidgets import QApplication
        for screen in QApplication.screens(): self.monitor.addItem(screen.name(), screen.name())
        self.monitor.setCurrentIndex(max(0, self.monitor.findData(self.config.get("screen", ""))))
        for title, field in (("Posição", self.position), ("Monitor", self.monitor)):
            form.addRow(title, field)
        labels = {"auto_hide": "Ocultar automaticamente", "replace_taskbar": "Ocultar barra de tarefas enquanto o dock estiver aberto",
            "reserve_space": "Reservar espaço para o dock (desativado no modo auto-ocultar)",
            "rounded_windows": "Arredondar cantos inferiores das janelas maximizadas compatíveis",
            "isolate_profiles": "Ocultar janelas dos outros perfis (somente apps exclusivos de um perfil)",
            "follow_desktop": "Trocar perfil ao mudar de área de trabalho vinculada"}
        for key, label in labels.items():
            check = QCheckBox(label); check.setChecked(self.config.get(key, False)); self.flags[key] = check; form.addRow(check)
        self.dock_system_controls = QComboBox()
        for label, key in (("Desligado", "off"), ("Completo", "full"), ("Compacto", "compact"), ("Mínimo", "minimal")):
            self.dock_system_controls.addItem(label, key)
        self.dock_system_controls.setCurrentIndex(self.dock_system_controls.findData(self.config.get("dock_system_controls", "off")))
        self.dock_system_controls.setToolTip("Completo: bandeja, estado, hora e data. Compacto: bandeja, estado e hora. Mínimo: apenas hora.")
        form.addRow("Controles do Windows no dock", self.dock_system_controls)
        self.flags["replace_taskbar"].setToolTip("Libera a área reservada pela barra do Windows e restaura a configuração original ao sair.")
        self.flags["reserve_space"].setToolTip("As janelas maximizadas param antes do dock. A faixa acompanha o tamanho dos ícones e é liberada ao ocultar o dock.")
        self.flags["reserve_space"].setChecked(self.config.get("reserve_space", True))
        form.addRow(QLabel("Atalhos globais: Ctrl+Alt+1…9: perfis · Ctrl+Alt+D: mostrar/ocultar dock.\nO registro avisa se houver conflito com outro aplicativo."))
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QScrollArea.NoFrame); scroll.setWidget(tab)
        self.tabs.addTab(scroll, "Posição e Windows")

    def select_theme(self, *_):
        key = self.preset.currentData()
        self.theme.setEnabled(not key)
        for index, preset in enumerate(PRESETS):
            self.theme_buttons.button(index).setChecked(preset == key)

    def make_panels(self):
        tab = QWidget(); form = QFormLayout(tab); form.setSpacing(14)
        form.addRow(QLabel("<h2>Ilha e barra superior</h2>Timers, mídia e avisos locais no topo da tela."))
        topbar_color_row, self.topbar_color = self.color_editor("topbar_color", "#1B202B", "topbar")
        form.addRow("Cor da barra superior", topbar_color_row)
        self.topbar_font = QComboBox(); self.topbar_font.addItems(TOPBAR_FONTS)
        self.topbar_font.setCurrentText(self.config.get("topbar_font", "Segoe UI Variable"))
        self.topbar_font_size = QSpinBox(); self.topbar_font_size.setRange(10, 15)
        self.topbar_font_size.setValue(self.config.get("topbar_font_size", 12)); self.topbar_font_size.setSuffix(" px")
        font_row = QHBoxLayout(); font_row.addWidget(self.topbar_font, 1); font_row.addWidget(self.topbar_font_size)
        form.addRow("Fonte", font_row)
        self.topbar_font.currentTextChanged.connect(self.update_color_previews)
        self.topbar_font_size.valueChanged.connect(self.update_color_previews)
        self.topbar_preview = QLabel("Prévia · Ambiente                 Rede · Som                 12:34")
        self.topbar_preview.setMinimumHeight(36); form.addRow(self.topbar_preview)
        fields = (
            ("island_enabled", "Mostrar a Ilha no topo", False),
            ("island_always_visible", "Manter a Ilha visível quando estiver ociosa", True),
            ("topbar_enabled", "Mostrar barra superior", True),
            ("topbar_status", "Mostrar rede, volume e bateria na barra superior", True),
            ("topbar_tray", "Mostrar acesso à bandeja do Windows", True),
            ("media_enabled", "Integrar música e vídeo do Windows", True),
            ("island_downloads", "Avisar quando um download terminar", True),
            ("island_screenshots", "Avisar quando uma captura for salva", True),
            ("island_battery", "Avisar mudanças de energia e bateria fraca", True),
            ("island_volume", "Mostrar alterações de volume", True),
        )
        for key, label, default in fields:
            check = QCheckBox(label); check.setChecked(self.config.get(key, default))
            self.flags[key] = check; form.addRow(check)
        note = QLabel("Passe o mouse na Ilha para expandir e iniciar timers de 5, 15 ou 25 minutos.\n"
                      "Os controles de mídia usam a sessão que o aplicativo fornece ao Windows.\n"
                      "Downloads e capturas usam as pastas deste Windows, sem abrir ou enviar seu conteúdo.\n"
                      "O calendário da Ilha ainda não está conectado. Os botões da barra abrem controles do Windows.")
        note.setWordWrap(True); form.addRow(note)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(tab)
        self.tabs.addTab(scroll, "Ilha e barra superior")

    def color_editor(self, key, default, surface):
        row = QWidget(); layout = QHBoxLayout(row); layout.setContentsMargins(0, 0, 0, 0)
        field = QLineEdit(str(self.config.get(key, default)), row)
        field.setMaxLength(7); field.setPlaceholderText("Usar cor do tema")
        field.setToolTip("Código hexadecimal #RRGGBB. Em branco acompanha o tema.")
        field.setAccessibleName("Cor do dock" if surface == "dock" else "Cor da barra superior")
        layout.addWidget(field, 1)
        choose = QPushButton("Escolher cor…"); layout.addWidget(choose)
        reset = QPushButton("Usar tema"); layout.addWidget(reset)
        choose.clicked.connect(lambda: self.choose_surface_color(field, surface))
        reset.clicked.connect(field.clear)
        field.textChanged.connect(self.update_color_previews)
        return row, field

    def choose_surface_color(self, field, surface):
        color = QColor(field.text())
        if not color.isValid(): color = QColor(palette(self.config, surface)["bottom"])
        selected = QColorDialog.getColor(color, self, "Cor do dock" if surface == "dock" else "Cor da barra superior")
        if selected.isValid(): field.setText(selected.name().upper())

    def update_color_previews(self, *_):
        data = dict(self.config)
        if hasattr(self, "preset"):
            if self.preset.currentData(): data["appearance_preset"] = self.preset.currentData()
            else: data.pop("appearance_preset", None)
        for key in ("dock_color", "topbar_color"):
            if hasattr(self, key): data[key] = getattr(self, key).text().strip()
        if hasattr(self, "dock_preview"):
            values = palette(data)
            opacity = self.finish_controls["dock_opacity"].value()
            alpha = 204 if opacity < 0 else round(255 * opacity / 100)
            top, bottom = QColor(values["top"]), QColor(values["bottom"])
            glow = self.finish_controls["dock_glow"].value()
            if glow > 0 or self.dock_reflection.isChecked():
                top = top.lighter(100 + max(0, glow) + 12 * self.dock_reflection.isChecked())
            def rgba(color):
                return f"rgba({color.red()},{color.green()},{color.blue()},{alpha})"
            roundness = self.finish_controls["dock_roundness"].value()
            radius = values["radius"] if roundness < 0 else round(20 * roundness / 100)
            border = self.finish_controls["dock_border"].value()
            self.dock_preview.setStyleSheet(
                f"background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {rgba(top)},stop:1 {rgba(bottom)});"
                f"color:{values['foreground']};border:{border}px solid {values['border']};"
                f"border-radius:{radius}px;padding:12px;font-weight:600;"
            )
        if hasattr(self, "topbar_preview"):
            values = palette(data, "topbar")
            family = self.topbar_font.currentText(); size = self.topbar_font_size.value()
            self.topbar_preview.setStyleSheet(f"background:{values['bottom']};color:{values['foreground']};border:1px solid {values['border']};border-radius:6px;padding:8px;font-family:'{family}';font-size:{size}px;")

    def reset_dock_finish(self):
        self.dock_color.clear()
        for key, control in self.finish_controls.items():
            control.setValue(1 if key == "dock_border" else control.minimum())
        self.dock_reflection.setChecked(False)
        self.app_indicator.setCurrentIndex(0)

    def make_options(self):
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        tab = QWidget(); form = QFormLayout(tab); self.option_fields = {}
        self.online = QCheckBox("Habilitar consultas online para widgets usados")
        options = self.config.get("widget_options", {})
        self.online.setChecked(bool(options.get("online", False))); form.addRow(self.online)
        fields = [("latitude", "Latitude", "-22.9068"), ("longitude", "Longitude", "-43.1729"), ("timezone", "Fuso mundial (IANA)", "Europe/London"),
            ("disk_path", "Disco/pasta para medir", ""), ("timer_minutes", "Temporizador (minutos)", "5"),
            ("countdown_date", "Contagem (AAAA-MM-DD)", "2027-01-01"), ("note", "Nota rápida", ""),
            ("stock_symbol", "Código da ação (Alpha Vantage)", "MSFT"), ("stock_api_key", "Chave Alpha Vantage", ""),
            ("steam_id", "Steam ID 64", ""), ("steam_api_key", "Chave Steam Web API", ""),
            ("translate_language", "Tradução (origem|destino)", "en|pt"),
            ("claude_usage_file", "Claude Code: pasta de sessões ou JSON", "")]
        for key, label, default in fields:
            field = QLineEdit(str(options.get(key, default)))
            if key.endswith("api_key"): field.setEchoMode(QLineEdit.Password)
            self.option_fields[key] = field; form.addRow(label, field)
        form.addRow(QLabel("Fontes: Open-Meteo · Frankfurter/ECB · CoinGecko · Alpha Vantage · Steam · MyMemory.\nClaude: selecione %USERPROFILE%\\.claude\\projects ou um JSON {\"tokens_today\": 12345}.\nA leitura é local e não consulta a cota da conta.\nAs chaves ficam neste computador e são removidas da exportação.\nWidgets próprios: arquivos JSON na pasta de configurações / widgets. Veja o README."))
        scroll.setWidget(tab); self.tabs.addTab(scroll, "Widgets e fontes")

    def select_profile(self, index):
        if index < 0: return
        self.store_profile()
        self.current = index
        p = self.config["profiles"][index]
        self.profile_name.setText(p["name"]); self.color_value = p["color"]
        self.color.setStyleSheet(f"background:{self.color_value};color:#152029;padding:8px")
        self.desktop.setText(p.get("desktop_id", "")); self.items.clear()
        for item in p["items"]: self.append_item(item)
        chosen = p.get("widgets", self.config.get("widgets", ["clock", "pomodoro"]))
        for i in range(self.widget_list.count()):
            item = self.widget_list.item(i)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in chosen else Qt.Unchecked)

    def store_profile(self):
        if not 0 <= self.current < len(self.config["profiles"]): return
        profile = self.config["profiles"][self.current]
        profile.update(name=self.profile_name.text().strip(), color=self.color_value,
            items=[self.items.item(i).data(Qt.UserRole) for i in range(self.items.count())],
            desktop_id=self.desktop.text(), widgets=[self.widget_list.item(i).data(Qt.UserRole) for i in range(self.widget_list.count()) if self.widget_list.item(i).checkState() == Qt.Checked])
        self.profiles.item(self.current).setText(profile["name"])

    def append_item(self, data):
        item = QListWidgetItem(data["name"]); item.setToolTip(data["target"]); item.setData(Qt.UserRole, data); self.items.addItem(item)

    def add_item(self):
        if self.items.count() >= MAX_ITEMS:
            QMessageBox.information(self, "Perfil cheio", f"Crie outro perfil para mais de {MAX_ITEMS} atalhos."); return
        dialog = ShortcutDialog(self)
        if dialog.exec(): self.append_item(dialog.value)

    def add_installed_app(self):
        from app_catalog import AppPickerDialog
        if self.items.count() >= MAX_ITEMS:
            QMessageBox.information(self, "Perfil cheio", f"Até {MAX_ITEMS} atalhos por perfil."); return
        dialog = AppPickerDialog(self, [self.items.item(i).data(Qt.UserRole)["target"] for i in range(self.items.count())])
        if dialog.exec(): self.append_item(dialog.value)

    def edit_item(self):
        item = self.items.currentItem()
        if item is None: return
        dialog = ShortcutDialog(self, item.data(Qt.UserRole))
        if dialog.exec():
            item.setText(dialog.value["name"]); item.setData(Qt.UserRole, dialog.value); item.setToolTip(dialog.value["target"])

    def pick_color(self):
        from PySide6.QtGui import QColor
        color = QColorDialog.getColor(QColor(self.color_value), self)
        if color.isValid():
            self.color_value = color.name(); self.color.setStyleSheet(f"background:{self.color_value};color:#152029;padding:8px")

    def bind_desktop(self):
        key = native.desktop_id()
        if key: self.desktop.setText(key)
        else: QMessageBox.warning(self, "Área de trabalho", "Não foi possível obter o ID. Clique numa janela do desktop desejado e tente novamente.")

    def add_profile(self):
        if len(self.config["profiles"]) >= 12: return
        self.store_profile()
        name, ok = QInputDialog.getText(self, "Novo perfil", "Nome")
        if ok and name.strip():
            self.config["profiles"].append({"name": name.strip()[:40], "color": "#56C8B7", "items": [], "widgets": ["clock"]})
            self.profiles.addItem(name.strip()); self.profiles.setCurrentRow(self.profiles.count() - 1)

    def remove_profile(self):
        if len(self.config["profiles"]) == 1: return
        index = self.profiles.currentRow()
        self.current = -1
        del self.config["profiles"][index]
        self.profiles.blockSignals(True); self.profiles.takeItem(index); self.profiles.blockSignals(False)
        self.profiles.setCurrentRow(0); self.select_profile(0)

    def collect(self):
        self.store_profile()
        self.config.update(active=max(0, self.current), theme=self.theme.currentData(), position=self.position.currentData(),
            screen=self.monitor.currentData(), icon_size=self.size.value(), magnification=self.zoom.value(), widget_style=self.widget_style.currentData(), mascot=self.mascot.currentData())
        if self.preset.currentData(): self.config["appearance_preset"] = self.preset.currentData()
        else: self.config.pop("appearance_preset", None)
        self.config.update(bar_padding=self.padding.value(), motion=self.motion.currentData(), launch_animation=self.launch_animation.currentData())
        self.config.update(dock_color=self.dock_color.text().strip(), topbar_color=self.topbar_color.text().strip(),
                           topbar_font=self.topbar_font.currentText(), topbar_font_size=self.topbar_font_size.value())
        self.config.update({key: control.value() for key, control in self.finish_controls.items()})
        self.config["dock_system_controls"] = self.dock_system_controls.currentData()
        self.config.update(dock_reflection=self.dock_reflection.isChecked(),
                           app_indicator=self.app_indicator.currentData(), trash_style=self.trash_style.currentData())
        self.config.update({key: check.isChecked() for key, check in self.flags.items()})
        options = {key: field.text().strip() for key, field in self.option_fields.items()}
        options["online"] = self.online.isChecked()
        options["latitude"], options["longitude"] = float(options["latitude"]), float(options["longitude"])
        if not -90 <= options["latitude"] <= 90 or not -180 <= options["longitude"] <= 180: raise ValueError("Coordenadas inválidas.")
        options["timer_minutes"] = int(options["timer_minutes"])
        if not 1 <= options["timer_minutes"] <= 1440: raise ValueError("Temporizador: de 1 a 1440 minutos.")
        self.config["widget_options"] = options
        return validate_config(self.config)

    def check(self):
        try:
            self.value = self.collect()
            # Persist first, so a failed write cannot change the running dock.
            save_config(self.value)
            if self.startup.isChecked() != native.autostart_enabled(): native.set_autostart(self.startup.isChecked())
            self.accept()
        except (ValueError, OSError) as exc: QMessageBox.warning(self, "Não foi possível salvar", str(exc))

    def export_config(self):
        try:
            data = self.collect()
            data["widget_options"] = {k: v for k, v in data.get("widget_options", {}).items() if not k.endswith("api_key")}
            path = QFileDialog.getSaveFileName(self, "Exportar", "NTDock-backup.json", "JSON (*.json)")[0]
            if path: save_config(data, path, backup=False)
        except (ValueError, OSError) as exc: QMessageBox.warning(self, "Exportação", str(exc))

    def import_config(self):
        path = QFileDialog.getOpenFileName(self, "Importar", "", "JSON (*.json)")[0]
        if not path: return
        try:
            if Path(path).stat().st_size > 1000000: raise ValueError("Arquivo excede 1 MB.")
            config = validate_config(json.loads(Path(path).read_text(encoding="utf-8")))
            # Rebuild dialog so every setting is visibly reviewable before Save.
            dialog = SettingsDialog(config, self.engine, self.parentWidget())
            if dialog.exec(): self.value = dialog.value; self.accept()
        except (ValueError, OSError) as exc: QMessageBox.warning(self, "Importação", str(exc))
