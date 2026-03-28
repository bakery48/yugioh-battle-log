"""Entry point for Yu-Gi-Oh! Master Duel battle log application."""

import sys
import os

# Ensure the app directory is on the path when bundled or double-clicked
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk

import subprocess
import database
from main_window import MainWindow
from ime_utils import install_ime_hook, get_status, _LOG_PATH


def _git_hash() -> str:
    # Try git first (works in a cloned repo)
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        pass
    # Fall back to version.txt (present in downloaded zips)
    try:
        vfile = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.txt")
        with open(vfile, encoding="utf-8") as f:
            return f.read().strip()[:8]
    except Exception:
        return "unknown"


def main() -> None:
    git_hash = _git_hash()
    print(f"=== 遊戯王戦績管理  commit={git_hash} ===")
    print(f"    IMEログ: {_LOG_PATH}")

    database.init_db()

    root = tk.Tk()
    install_ime_hook()

    ime_status = get_status()
    base_title  = "遊戯王マスターデュエル 戦績管理"
    root.title(f"{base_title}  [commit:{git_hash}]{ime_status}")
    print(f"    {ime_status}")
    root.geometry("1200x760")
    root.minsize(960, 620)

    # App icon (optional – skip if file is absent)
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    if os.path.isfile(icon_path):
        try:
            root.iconbitmap(icon_path)
        except Exception:
            pass

    MainWindow(root)

    # Refresh the title bar every 2 s so the IME diagnostic counters stay live.
    def _refresh_title() -> None:
        ime_status = get_status()
        root.title(f"{base_title}  [commit:{git_hash}]{ime_status}")
        root.after(2000, _refresh_title)

    root.after(2000, _refresh_title)
    root.mainloop()


if __name__ == "__main__":
    main()
