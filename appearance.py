"""Original Dock palettes, informed by observed desktop dock treatments."""
from __future__ import annotations
import re

DOCK_FINISH = {
    "dock_opacity": ("Opacidade do fundo", -1, 100, " %"),
    "dock_border": ("Espessura do contorno", 0, 4, " px"),
    "dock_glow": ("Brilho superior", -1, 100, " %"),
    "dock_roundness": ("Cantos da barra", -1, 100, " %"),
}

TOPBAR_FONTS = ("Segoe UI Variable", "Segoe UI", "Arial", "Calibri")


def valid_color(value):
    return isinstance(value, str) and (value == "" or re.fullmatch(r"#[0-9a-fA-F]{6}", value) is not None)


def _luminance(color):
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4 for channel in channels]
    return sum(channel * weight for channel, weight in zip(linear, (.2126, .7152, .0722)))


def _tint(color, toward, amount):
    return "#" + "".join(f"{round(int(color[i:i + 2], 16) * (1 - amount) + toward * amount):02X}" for i in (1, 3, 5))


def _custom_palette(values, color):
    values = dict(values)
    luminance = _luminance(color)
    light_text = (1.05 / (luminance + .05)) >= ((luminance + .05) / .05)
    values.update(name="Personalizado", top=color if light_text else _tint(color, 255, .06),
                  bottom=_tint(color, 0, .06) if light_text else color,
                  border=_tint(color, 255 if light_text else 0, .22),
                  foreground="#FFFFFF" if light_text else "#000000")
    return values


PRESETS = {
    "glass": {"name": "Gelo", "top": "#EAF2FA", "bottom": "#C3D5E5", "border": "#F8FCFF", "foreground": "#203348", "radius": 15},
    "midnight": {"name": "Azul petróleo", "top": "#173B48", "bottom": "#102530", "border": "#477B8C", "foreground": "#F1F7FA", "radius": 15},
    "pier": {"name": "Grafite", "top": "#51483F", "bottom": "#282B30", "border": "#AA9B86", "foreground": "#FBF5ED", "radius": 6},
    "lagoon": {"name": "Verde jade", "top": "#299F93", "bottom": "#145951", "border": "#86E2CA", "foreground": "#F0FFF9", "radius": 15},
    "beacon": {"name": "Roxo profundo", "top": "#282638", "bottom": "#191A27", "border": "#BBA5ED", "foreground": "#F9F4FF", "radius": 18},
    "buoy": {"name": "Laranja coral", "top": "#F2A14D", "bottom": "#CA583F", "border": "#FFE0B3", "foreground": "#FFF9F1", "radius": 15},
    "sand": {"name": "Bege dourado", "top": "#F1DFC0", "bottom": "#C5AE8D", "border": "#FFF5DE", "foreground": "#493D30", "radius": 13},
    "raft": {"name": "Lavanda", "top": "#9B9BD8", "bottom": "#666EA9", "border": "#D3D6FF", "foreground": "#F9FAFF", "radius": 18},
}


def palette(config, surface="dock"):
    """Return independent values; old dark/light configurations keep their tone."""
    preset = config.get("appearance_preset")
    if preset in PRESETS:
        values = dict(PRESETS[preset])
    elif config.get("theme", "dark") == "light":
        values = dict(PRESETS["glass"])
    else:
        values = {"name": "Vidro escuro", "top": "#363A43", "bottom": "#1E2129", "border": "#747984", "foreground": "#F7F9FD", "radius": 17}
    color = config.get("topbar_color", "#1B202B") if surface == "topbar" else config.get("dock_color", "")
    if color and valid_color(color): values = _custom_palette(values, color)
    return values
