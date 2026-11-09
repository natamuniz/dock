"""Widgets: local metrics, timers and explicitly enabled online providers."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import calendar
import json
from pathlib import Path
import platform
import os
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psutil

from core import Pomodoro

CATALOG = {
    "clock": ("Relógio", "◷"), "analog": ("Relógio analógico", "◴"),
    "world": ("Relógio mundial", "◎"), "date": ("Data", "▦"),
    "calendar": ("Calendário", "▦"), "pomodoro": ("Pomodoro", "◉"),
    "stopwatch": ("Cronômetro", "◷"), "timer": ("Temporizador", "◷"),
    "day": ("Progresso do dia", "◔"), "week": ("Progresso da semana", "◔"),
    "month": ("Progresso do mês", "◔"), "year": ("Progresso do ano", "◔"),
    "uptime": ("Tempo ligado", "↑"), "cpu": ("Processador", "▤"),
    "frequency": ("Frequência CPU", "∿"), "ram": ("Memória RAM", "▥"),
    "swap": ("Memória virtual", "▥"), "processes": ("Processos", "▤"),
    "upload": ("Upload", "↑"), "download": ("Download", "↓"),
    "network": ("Tráfego total da sessão", "⇅"), "disk_free": ("Espaço livre", "▣"),
    "disk_used": ("Disco utilizado", "▣"), "disk_read": ("Leitura do disco", "↓"),
    "disk_write": ("Gravação no disco", "↑"), "battery": ("Bateria", "▰"),
    "power": ("Energia", "ϟ"), "hydration": ("Hidratação", "◡"),
    "countdown": ("Contagem regressiva", "▦"), "notes": ("Nota rápida", "≡"),
    "focus_count": ("Ciclos de foco na sessão", "◉"), "system": ("Sistema", "▤"),
    "weather": ("Clima agora", "☀"), "forecast": ("Máxima e mínima", "☀"),
    "humidity": ("Umidade", "≋"), "wind": ("Vento", "∿"),
    "sunrise": ("Nascer do sol", "☀"), "sunset": ("Pôr do sol", "◒"),
    "usd": ("Dólar / real", "$"), "eur": ("Euro / real", "€"),
    "btc": ("Bitcoin / real", "₿"), "eth": ("Ethereum / real", "Ξ"),
    "stock": ("Ação • Alpha Vantage", "↗"), "steam": ("Biblioteca Steam", "◈"),
    "translator": ("Tradutor • MyMemory", "文"),
    "claude": ("Claude • arquivo de consumo", "✳"),
    "media": ("Música e vídeo", "♫"),
}


def compact_bytes(number):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(number) < 1024 or unit == "TB":
            return f"{number:.1f} {unit}"
        number /= 1024


def get_json(url):
    request = Request(url, headers={"User-Agent": "NTDock/0.2 (+personal-desktop)"})
    with urlopen(request, timeout=8) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("Resposta excede o limite de 2 MB.")
    return json.loads(raw)


def claude_tokens(path, today=None):
    """Read local Claude Code assistant usage; never uploads transcript content.

    JSONL is a best-effort local format, not an Anthropic account/quota API.
    Repeated streaming records for a message are deduplicated by message ID.
    """
    today = today or datetime.now().date()
    path = Path(os.path.expandvars(os.path.expanduser(str(path))))
    if path.is_file() and path.suffix.lower() == ".json":
        if path.stat().st_size > 1_000_000: raise ValueError("Arquivo de consumo excede 1 MB.")
        return int(json.loads(path.read_text(encoding="utf-8"))["tokens_today"])
    files = list(path.rglob("*.jsonl")) if path.is_dir() else ([path] if path.is_file() else [])
    if not files: raise FileNotFoundError("Configure a pasta de sessões do Claude Code.")
    messages = {}; budget = 100_000_000
    for file in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True):
        if datetime.fromtimestamp(file.stat().st_mtime).date() < today: continue
        with file.open("r", encoding="utf-8", errors="replace") as stream:
            for line_number, line in enumerate(stream):
                budget -= len(line.encode("utf-8"))
                if budget < 0: raise ValueError("Sessões do dia excedem 100 MB; selecione um projeto específico.")
                try:
                    entry = json.loads(line)
                    if entry.get("type") != "assistant": continue
                    timestamp = datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")).astimezone()
                    if timestamp.date() != today: continue
                    message = entry.get("message", {}); usage = message.get("usage", {})
                    ident = message.get("id") or f"{file}:{line_number}"
                    counts = {key: max(0, int(usage.get(key) or 0)) for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}
                    previous = messages.setdefault(ident, {})
                    for key, count in counts.items(): previous[key] = max(previous.get(key, 0), count)
                except (ValueError, TypeError, KeyError, AttributeError): continue
    return sum(sum(usage.values()) for usage in messages.values())


class WidgetEngine:
    def __init__(self, options=None):
        self.options = options or {}
        self.pomodoro = Pomodoro()
        self.timer = Pomodoro()
        self.timer.remaining = 300
        self.stop_started = None
        self.stop_elapsed = 0
        self.cups, self.focuses = 0, 0
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ntdock-data")
        self.metrics_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ntdock-metrics")
        self.metrics_future = None; self.closed = False
        self.remote, self.pending, self.last, self.errors = {}, {}, {}, {}
        self.custom = {}
        self.local = {}
        self.previous_network = psutil.net_io_counters()
        self.session_network = self.previous_network.bytes_sent + self.previous_network.bytes_recv
        self.previous_disk = psutil.disk_io_counters()
        self.last_sample = time.monotonic()
        self.sample()

    def load_custom(self, directory):
        self.custom.clear()
        for path in Path(directory).glob("*.json"):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                key = "custom:" + path.stem
                if value.get("type") in ("text", "countdown", "url") and isinstance(value.get("title"), str):
                    if value["type"] == "url":
                        from core import validate_target
                        validate_target(value.get("value"))
                        if not value["value"].startswith(("http://", "https://")):
                            continue
                    self.custom[key] = value
            except (OSError, ValueError, TypeError, AttributeError):
                continue

    def catalog(self):
        return {**CATALOG, **{key: (v["title"], "✦") for key, v in self.custom.items()}}

    def _collect_local(self, options):
        now = time.monotonic()
        elapsed = max(.01, now - self.last_sample)
        ram, swap = psutil.virtual_memory(), psutil.swap_memory()
        net, disk = psutil.net_io_counters(), psutil.disk_io_counters()
        root = options.get("disk_path") or Path.home().anchor
        try:
            usage = psutil.disk_usage(str(root))
        except OSError:
            usage = psutil.disk_usage(str(Path.home().anchor))
        try:
            battery, freq = psutil.sensors_battery(), psutil.cpu_freq()
        except (AttributeError, NotImplementedError, OSError):
            battery, freq = None, None
        self.local = {
            "cpu": f"{psutil.cpu_percent():.0f}%", "ram": f"{ram.percent:.0f}% · {compact_bytes(ram.used)}",
            "swap": f"{swap.percent:.0f}%", "processes": str(len(psutil.pids())),
            "frequency": f"{freq.current / 1000:.2f} GHz" if freq else "Indisponível",
            "upload": compact_bytes(max(0, net.bytes_sent - self.previous_network.bytes_sent) / elapsed) + "/s",
            "download": compact_bytes(max(0, net.bytes_recv - self.previous_network.bytes_recv) / elapsed) + "/s",
            "network": compact_bytes(max(0, net.bytes_sent + net.bytes_recv - self.session_network)),
            "disk_free": compact_bytes(usage.free), "disk_used": f"{usage.percent:.0f}%",
            "disk_read": compact_bytes(max(0, disk.read_bytes - self.previous_disk.read_bytes) / elapsed) + "/s" if disk and self.previous_disk else "—",
            "disk_write": compact_bytes(max(0, disk.write_bytes - self.previous_disk.write_bytes) / elapsed) + "/s" if disk and self.previous_disk else "—",
            "battery": f"{battery.percent:.0f}%" if battery else "Sem bateria",
            "power": ("Na tomada" if battery.power_plugged else "Na bateria") if battery else "Sem sensor",
            "uptime": f"{(time.time() - psutil.boot_time()) / 3600:.1f} h",
            "system": f"{platform.system()} {platform.release()}",
        }
        self.previous_network, self.previous_disk, self.last_sample = net, disk, now

    def sample(self):
        if not self.closed and (self.metrics_future is None or self.metrics_future.done()):
            # A slow CPU/disk query must not stall hover frames or timers.
            if self.metrics_future is not None:
                try: self.metrics_future.result()
                except Exception: pass
            self.metrics_future = self.metrics_pool.submit(self._collect_local, dict(self.options))
        for key, future in list(self.pending.items()):
            if future.done():
                try:
                    self.remote[key] = future.result()
                    self.errors.pop(key, None)
                except Exception as exc:
                    self.errors[key] = str(exc)[:150]
                del self.pending[key]
        ended = self.pomodoro.tick()
        if ended and self.pomodoro.phase == "Pausa":
            self.focuses += 1
        timer_ended = self.timer.tick()
        return ended, timer_ended

    def request(self, key, function, interval=600, online_required=True):
        if online_required and not self.options.get("online", False):
            return False
        if key not in self.pending and time.monotonic() - self.last.get(key, -1e9) >= interval:
            self.last[key] = time.monotonic()
            self.pending[key] = self.pool.submit(function)
        return True

    def weather_data(self):
        query = urlencode({"latitude": self.options.get("latitude", -22.9068), "longitude": self.options.get("longitude", -43.1729),
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m", "daily": "temperature_2m_max,temperature_2m_min,sunrise,sunset", "timezone": "auto", "forecast_days": 1})
        return get_json("https://api.open-meteo.com/v1/forecast?" + query)

    def value(self, key):
        now = datetime.now()
        if key == "media":
            provider = getattr(self, "media", None)
            state = provider.snapshot() if provider is not None else {}
            return state.get("title") or "Nada tocando"
        if key in self.local:
            return self.local[key]
        if key in ("clock", "analog"):
            return now.strftime("%H:%M")
        if key == "world":
            try:
                return datetime.now(ZoneInfo(self.options.get("timezone", "Europe/London"))).strftime("%H:%M")
            except ZoneInfoNotFoundError:
                return "Fuso inválido"
        if key == "date": return now.strftime("%d/%m/%Y")
        if key == "calendar": return now.strftime("%d/%m") + " · " + ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"][now.weekday()]
        if key in ("pomodoro", "timer"):
            timer = self.pomodoro if key == "pomodoro" else self.timer
            seconds = timer.seconds()
            return f"{seconds // 60:02}:{seconds % 60:02} {'Ⅱ' if timer.deadline is not None else '▷'}"
        if key == "stopwatch":
            seconds = int(self.stop_elapsed + (time.monotonic() - self.stop_started if self.stop_started is not None else 0))
            return f"{seconds // 60:02}:{seconds % 60:02}"
        fraction = (now.hour * 3600 + now.minute * 60 + now.second) / 86400
        if key == "day": return f"{fraction * 100:.0f}%"
        if key == "week": return f"{(now.weekday() + fraction) / 7 * 100:.0f}%"
        if key == "month": return f"{(now.day - 1 + fraction) / calendar.monthrange(now.year, now.month)[1] * 100:.0f}%"
        if key == "year": return f"{(now.timetuple().tm_yday - 1 + fraction) / (366 if calendar.isleap(now.year) else 365) * 100:.0f}%"
        if key == "hydration": return f"{self.cups}/8 copos"
        if key == "focus_count": return str(self.focuses)
        if key == "notes": return str(self.options.get("note", "Clique para anotar"))[:100]
        if key == "countdown":
            try:
                target = datetime.fromisoformat(self.options.get("countdown_date", f"{now.year + 1}-01-01"))
                return f"{max(0, (target.date() - now.date()).days)} dias"
            except ValueError: return "Data inválida"
        if key in ("weather", "forecast", "humidity", "wind", "sunrise", "sunset"):
            if not self.request("weather", self.weather_data): return "Ative dados online"
            data = self.remote.get("weather", {})
            if not data: return self.status("weather")
            current, daily = data.get("current", {}), data.get("daily", {})
            if key == "weather": return f"{current.get('temperature_2m', '—')} °C"
            if key == "humidity": return f"{current.get('relative_humidity_2m', '—')}%"
            if key == "wind": return f"{current.get('wind_speed_10m', '—')} km/h"
            if key == "forecast": return f"{daily.get('temperature_2m_min', ['—'])[0]}° / {daily.get('temperature_2m_max', ['—'])[0]}°"
            return str(daily.get(key, ["—"])[0])[-5:]
        if key in ("usd", "eur"):
            currency = key.upper()
            if not self.request(key, lambda: get_json(f"https://api.frankfurter.dev/v1/latest?from={currency}&to=BRL"), 3600): return "Ative dados online"
            rate = self.remote.get(key, {}).get("rates", {}).get("BRL")
            return f"R$ {rate:.2f}" if rate else self.status(key)
        if key in ("btc", "eth"):
            if not self.request("crypto", lambda: get_json("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=brl"), 300): return "Ative dados online"
            price = self.remote.get("crypto", {}).get("bitcoin" if key == "btc" else "ethereum", {}).get("brl")
            return f"R$ {price:,.0f}" if price else self.status("crypto")
        if key == "stock":
            api = self.options.get("stock_api_key", "")
            if not api: return "Configure a chave"
            query = urlencode({"function": "GLOBAL_QUOTE", "symbol": self.options.get("stock_symbol", "MSFT"), "apikey": api})
            if not self.request(key, lambda: get_json("https://www.alphavantage.co/query?" + query), 3600): return "Ative dados online"
            quote = self.remote.get(key, {}).get("Global Quote", {})
            return quote.get("05. price", self.status(key))
        if key == "steam":
            api, player = self.options.get("steam_api_key", ""), self.options.get("steam_id", "")
            if not api or not player: return "Configure Steam ID/chave"
            query = urlencode({"key": api, "steamid": player, "include_appinfo": "true"})
            if not self.request(key, lambda: get_json("https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?" + query), 3600): return "Ative dados online"
            response = self.remote.get(key, {}).get("response", {})
            return f"{response['game_count']} jogos" if "game_count" in response else self.status(key)
        if key == "translator": return "Clique para traduzir"
        if key == "claude":
            path = self.options.get("claude_usage_file", "")
            if not path: return "Selecione sessões/JSON"
            self.request(key, lambda: claude_tokens(path), 60, online_required=False)
            value = self.remote.get(key)
            return f"{value:,} tokens hoje" if value is not None else self.status(key)
        if key in self.custom:
            custom = self.custom[key]
            if custom["type"] == "countdown":
                try: return f"{max(0, (datetime.fromisoformat(custom['value']).date() - now.date()).days)} dias"
                except (ValueError, KeyError): return "Data inválida"
            return str(custom.get("value", ""))[:100]
        return "Widget não encontrado"

    def status(self, key):
        return "Sem dados • tente depois" if key in self.errors else "Carregando…"

    def click(self, key):
        if key == "pomodoro": self.pomodoro.toggle()
        elif key == "timer": self.timer.toggle()
        elif key == "stopwatch":
            if self.stop_started is None: self.stop_started = time.monotonic()
            else:
                self.stop_elapsed += time.monotonic() - self.stop_started
                self.stop_started = None
        elif key == "hydration": self.cups = (self.cups + 1) % 9

    def reset(self, key):
        if key == "pomodoro": self.pomodoro.reset()
        elif key == "timer":
            self.timer.reset()
            self.timer.remaining = max(1, int(self.options.get("timer_minutes", 5))) * 60
        elif key == "stopwatch": self.stop_elapsed, self.stop_started = 0, None
        elif key == "hydration": self.cups = 0

    def close(self):
        self.closed = True
        self.metrics_pool.shutdown(wait=False, cancel_futures=True)
        self.pool.shutdown(wait=False, cancel_futures=True)
