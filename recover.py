"""Explicit emergency recovery; never terminates any application."""
import json
from core import config_path, load_config, save_config
import native


def main():
    native.enable_physical_coordinates()
    native.set_taskbars(True)
    restored = 0
    for path in config_path().parent.glob("recovery-*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            from window_effects import restore_corners
            restore_corners(data.get("corners", []))
            native.restore_taskbar_snapshot(data)
            for record in data.get("windows", []):
                if native.alive(record):
                    native.user.ShowWindowAsync(record["hwnd"], 7 if record.get("minimized") else 8)
                    restored += 1
        except (OSError, ValueError, KeyError):
            continue
    config, _ = load_config()
    config.update(replace_taskbar=False, isolate_profiles=False, auto_hide=False, rounded_windows=False)
    save_config(config)
    print(f"Barra de tarefas restaurada. Janelas restauradas: {restored}.")
    print("Feche e reabra o Dock para carregar as opcoes de recuperacao.")


if __name__ == "__main__": main()
