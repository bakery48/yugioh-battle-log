"""Entry point for Yu-Gi-Oh! Master Duel battle log application."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
import subprocess
import database
from main_window import MainWindow
from ime_utils import fix_entry_ime_font


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        pass
    try:
        vfile = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.txt")
        with open(vfile, encoding="utf-8") as f:
            return f.read().strip()[:8]
    except Exception:
        return "unknown"


def main() -> None:
    git_hash = _git_hash()
    print(f"=== 遊戯王戦績管理  commit={git_hash} ===")

    database.init_db()

    root = tk.Tk()
    root.title(f"遊戯王マスターデュエル 戦績管理  [commit:{git_hash}]")
    root.geometry("1200x760")
    root.minsize(960, 620)

    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
    if os.path.isfile(icon_path):
        try:
            root.iconbitmap(icon_path)
        except Exception:
            pass

    for _cls in ("TEntry", "Entry"):
        root.bind_class(_cls, "<FocusIn>",
                        lambda e: fix_entry_ime_font(e.widget),
                        add="+")

    MainWindow(root)
    root.mainloop()
    os._exit(0)


if __name__ == "__main__":
    main()
