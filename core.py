"""Configuration and timing logic; independent of Qt and Windows."""
from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import time
from urllib.parse import urlsplit

from appearance import DOCK_FINISH, PRESETS, TOPBAR_FONTS, valid_color


MAX_ITEMS = 12


def default_config():
    home = str(Path.home())
    def link(name, target):
        return {"name": name, "target": target}
    return {
        "version": 1, "active": 0, "icon_size": 36, "magnification": 1.45,
        "appearance_preset": "midnight", "bar_padding": 7,
        "dock_color": "", "topbar_color": "#1B202B", "topbar_font": "Segoe UI Variable", "topbar_font_size": 12,
        "motion": "lens", "launch_animation": "bounce",
        "profile_dots": True, "colored_indicators": True,
        "show_trash": True, "show_settings": True, "show_start": False,
        "rounded_windows": False,
        "island_enabled": False, "island_always_visible": True,
        "island_downloads": True, "island_screenshots": True, "island_battery": True, "island_volume": True,
        "topbar_enabled": True, "topbar_status": True, "topbar_tray": True, "media_enabled": True,
        "screen": "", "theme": "dark", "position": "bottom",
        "auto_hide": False, "replace_taskbar": False, "reserve_space": True,
        "blur": True, "isolate_profiles": False, "follow_desktop": False,
        "widget_style": "glass", "mascot": "none", "widgets": ["clock", "pomodoro"],
        "widget_options": {}, "profiles": [
            {"name": "Desenvolvimento", "color": "#56C8B7", "items": [
                link("Projetos", home), link("GitHub", "https://github.com"),
                link("Documentação Python", "https://docs.python.org/3/"),
                link("Documentação PHP", "https://www.php.net/manual/pt_BR/"),
                link("Meu portfólio", "https://natamunizdev.com.br")]},
            {"name": "Trabalho", "color": "#70A7FF", "items": [
                link("Documentos", str(Path.home() / "Documents")),
                link("Downloads", str(Path.home() / "Downloads"))]},
            {"name": "Estudo", "color": "#F7C56B", "items": [
                link("Python", "https://docs.python.org/3/"),
                link("Laravel", "https://laravel.com/docs")]},
            {"name": "Lazer", "color": "#BB9AF7", "items": [
                link("YouTube", "https://www.youtube.com")]}]}


def validate_target(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise ValueError("Informe um caminho ou um endereço http/https válido.")
    target = value.strip()
    if "\x00" in target or "\n" in target or "\r" in target:
        raise ValueError("O destino contém caracteres inválidos.")
    if "://" in target:
        parsed = urlsplit(target)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("Links devem começar com http:// ou https://.")
    elif not Path(os.path.expandvars(os.path.expanduser(target))).is_absolute():
        raise ValueError("Selecione um caminho completo de arquivo ou pasta.")
    return target


def validate_config(value):
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("Arquivo de configuração incompatível (versão esperada: 1).")
    profiles = value.get("profiles")
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= 12:
        raise ValueError("Use de 1 a 12 perfis.")
    result = copy.deepcopy(value)
    for profile in profiles:
        if not isinstance(profile, dict):
            raise ValueError("Perfil inválido.")
        name, color, items = profile.get("name"), profile.get("color"), profile.get("items")
        if not isinstance(name, str) or not name.strip() or len(name) > 40:
            raise ValueError("O nome do perfil deve ter de 1 a 40 caracteres.")
        if not isinstance(color, str) or len(color) != 7 or not color.startswith("#"):
            raise ValueError("Cor de perfil inválida.")
        try:
            int(color[1:], 16)
        except ValueError as exc:
            raise ValueError("Cor de perfil inválida.") from exc
        if not isinstance(items, list) or len(items) > MAX_ITEMS:
            raise ValueError(f"Cada perfil aceita até {MAX_ITEMS} atalhos.")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                raise ValueError("Atalho inválido.")
            if not 1 <= len(item["name"].strip()) <= 60:
                raise ValueError("O nome do atalho deve ter de 1 a 60 caracteres.")
            validate_target(item.get("target"))
            if "track_new" in item and type(item["track_new"]) is not bool:
                raise ValueError("A contagem de arquivos deve ser ligada ou desligada.")
            if item.get("icon"):
                validate_target(item["icon"])
                if "://" in item["icon"]: raise ValueError("O ícone deve ser um arquivo local.")
    for key, low, high in [("icon_size", 32, 64), ("magnification", 1, 2)]:
        number = value.get(key)
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not low <= number <= high:
            raise ValueError(f"Valor inválido para {key}.")
    active = value.get("active")
    if type(active) is not int or not 0 <= active < len(profiles):
        raise ValueError("Perfil ativo inválido.")
    if not isinstance(value.get("screen", ""), str):
        raise ValueError("Monitor inválido.")
    for key in ("auto_hide", "replace_taskbar", "reserve_space", "blur", "isolate_profiles", "follow_desktop",
                "profile_dots", "colored_indicators", "show_trash", "show_settings", "show_start", "rounded_windows",
                "island_enabled", "island_always_visible", "island_downloads", "island_screenshots",
                "island_battery", "island_volume", "topbar_enabled", "topbar_status", "topbar_tray", "media_enabled"):
        if key in value and type(value[key]) is not bool:
            raise ValueError(f"Valor inválido para {key}.")
    for key, choices in (("theme", ("dark", "light")), ("position", ("bottom", "left", "right")), ("widget_style", ("glass", "color"))):
        if key in value and value[key] not in choices:
            raise ValueError(f"Valor inválido para {key}.")
    for key, choices in (("appearance_preset", PRESETS), ("motion", ("none", "grow", "lens")),
                         ("launch_animation", ("none", "bounce", "pulse", "shake"))):
        if key in value and (not isinstance(value[key], str) or value[key] not in choices):
            raise ValueError(f"Valor inválido para {key}.")
    if "bar_padding" in value and (type(value["bar_padding"]) is not int or not 0 <= value["bar_padding"] <= 16):
        raise ValueError("Folga da barra: de 0 a 16 pixels.")
    for key, (_, minimum, maximum, _) in DOCK_FINISH.items():
        if key in value and (type(value[key]) is not int or not minimum <= value[key] <= maximum):
            raise ValueError(f"Valor inválido para {key}.")
    if "dock_reflection" in value and type(value["dock_reflection"]) is not bool:
        raise ValueError("Reflexo inválido.")
    for key, choices in (("app_indicator", ("dot", "dash")), ("trash_style", ("windows", "tile", "outline")),
                         ("dock_system_controls", ("off", "full", "compact", "minimal"))):
        if key in value and value[key] not in choices:
            raise ValueError(f"Valor inválido para {key}.")
    for key in ("dock_color", "topbar_color"):
        if key in value and not valid_color(value[key]): raise ValueError("Cor inválida. Use #RRGGBB ou deixe em branco para usar o tema.")
    if "topbar_font" in value and value["topbar_font"] not in TOPBAR_FONTS:
        raise ValueError("Fonte da barra superior inválida.")
    if "topbar_font_size" in value and (type(value["topbar_font_size"]) is not int or not 10 <= value["topbar_font_size"] <= 15):
        raise ValueError("Fonte da barra superior: de 10 a 15 pixels.")
    if value.get("mascot", "none") not in ("none", "cat", "dog"):
        raise ValueError("Personagem inválido.")
    seen = value.get("folder_seen", {})
    if not isinstance(seen, dict) or len(seen) > 200 or any(not isinstance(k, str) or type(v) not in (int, float) or not math.isfinite(v) for k, v in seen.items()):
        raise ValueError("Histórico de pastas inválido.")
    widgets = value.get("widgets", [])
    if not isinstance(widgets, list) or len(widgets) > 6 or any(not isinstance(w, str) or len(w) > 80 for w in widgets):
        raise ValueError("Use até seis widgets no dock; os demais ficam no painel.")
    options = value.get("widget_options", {})
    if not isinstance(options, dict) or len(json.dumps(options)) > 50000:
        raise ValueError("Opções de widgets inválidas.")
    for key, option in options.items():
        if not isinstance(key, str) or not isinstance(option, (str, int, float, bool)):
            raise ValueError("Opção de widget inválida.")
    if "online" in options and type(options["online"]) is not bool:
        raise ValueError("A opção de dados online deve ser booleana.")
    for key, low, high in (("latitude", -90, 90), ("longitude", -180, 180), ("timer_minutes", 1, 1440)):
        if key in options:
            try: number = float(options[key])
            except (ValueError, TypeError) as exc: raise ValueError(f"Valor inválido: {key}.") from exc
            if isinstance(options[key], bool) or not math.isfinite(number) or not low <= number <= high:
                raise ValueError(f"Valor inválido: {key}.")
            result["widget_options"][key] = int(number) if key == "timer_minutes" else number
    for profile in profiles:
        if "widgets" in profile and (not isinstance(profile["widgets"], list) or len(profile["widgets"]) > 6 or any(not isinstance(w, str) for w in profile["widgets"])):
            raise ValueError("Widgets do perfil inválidos.")
        if "desktop_id" in profile and not isinstance(profile["desktop_id"], str):
            raise ValueError("Vínculo de área de trabalho inválido.")
    return result


def config_path():
    base = Path(os.environ.get("APPDATA", str(Path.home() / ".config")))
    return base / "NTDock" / "config.json"


def save_config(config, path=None, backup=True):
    data = validate_config(config)
    path = Path(path or config_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".ntdock-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        if backup and path.exists():
            shutil.copy2(path, path.with_suffix(".json.bak"))
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_config(path=None):
    path = Path(path or config_path())
    if not path.exists():
        return default_config(), None
    try:
        return validate_config(json.loads(path.read_text(encoding="utf-8"))), None
    except (OSError, ValueError, TypeError) as exc:
        backup = path.with_suffix(".json.bak")
        try:
            recovered = validate_config(json.loads(backup.read_text(encoding="utf-8")))
            preserved = path.with_name(f"config-invalida-{time.time_ns()}.json")
            shutil.copy2(path, preserved)
            save_config(recovered, path, backup=False)
            return recovered, f"Configuração recuperada do backup: {exc}"
        except (OSError, ValueError, TypeError):
            # Preserve invalid data before a later save can replace it.
            preserved = path.with_name(f"config-invalida-{time.time_ns()}.json")
            try:
                shutil.copy2(path, preserved)
            except OSError as preserve_error:
                raise OSError("Não foi possível preservar a configuração inválida.") from preserve_error
            return default_config(), f"Configuração inválida preservada em {preserved}. Usando os padrões."


class Pomodoro:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.phase = "Foco"
        self.remaining = 25 * 60
        self.deadline = None

    def seconds(self):
        if self.deadline is None:
            return self.remaining
        return max(0, math.ceil(self.deadline - self.clock()))

    def toggle(self):
        if self.deadline is None:
            self.deadline = self.clock() + self.remaining
        else:
            self.remaining = self.seconds()
            self.deadline = None

    def reset(self):
        self.phase, self.remaining, self.deadline = "Foco", 1500, None

    def tick(self):
        if self.deadline is not None and self.seconds() == 0:
            self.phase = "Pausa" if self.phase == "Foco" else "Foco"
            self.remaining = 300 if self.phase == "Pausa" else 1500
            self.deadline = None
            return True
        return False
