"""Entry point for Yu-Gi-Oh! Master Duel battle log application."""

import sys
import os

# Ensure the app directory is on the path when bundled or double-clicked
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk

import database
from main_window import MainWindow
from ime_utils import install_ime_hook


def main() -> None:
    database.init_db()

    root = tk.Tk()
    # Install thread-local hook to suppress IME candidate popup globally
    install_ime_hook()
    root.title("遊戯王マスターデュエル 戦績管理")
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
    root.mainloop()


if __name__ == "__main__":
    main()
