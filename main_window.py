"""Main application window with tabbed layout."""

import tkinter as tk
from tkinter import ttk

from battle_tab import BattleTab
from deck_tab import DeckTab
from stats_tab import StatsTab, _DARK_STATS_ROWS, _LIGHT_STATS_ROWS
from chart_tab import ChartTab
from color_monitor_tab import ColorMonitorTab

_LIGHT = {
    "listbox_bg": "SystemWindow",
    "listbox_fg": "SystemWindowText",
    "select_bg":  "#0078d4",
    "select_fg":  "white",
    "tree_win":   "#e8f5e9",
    "tree_loss":  "#ffebee",
    "stats_rows": _LIGHT_STATS_ROWS,
    "stats_fg":   "black",
}

_DARK = {
    "listbox_bg": "#3c3f41",
    "listbox_fg": "#d0d0d0",
    "select_bg":  "#4b6eaf",
    "select_fg":  "white",
    "tree_win":   "#1a3320",
    "tree_loss":  "#3a1a1a",
    "stats_rows": _DARK_STATS_ROWS,
    "stats_fg":   "#d0d0d0",
}


class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self._mode = "light"
        self._setup_style()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Style ─────────────────────────────────────────────────────────────────

    def _setup_style(self) -> None:
        style = ttk.Style()
        if self._mode == "dark":
            style.theme_use("clam")
            bg, fg, field = "#2b2b2b", "#d0d0d0", "#3c3f41"
            sel_bg = "#4b6eaf"
            style.configure(".",
                            background=bg, foreground=fg,
                            fieldbackground=field,
                            troughcolor=bg, bordercolor="#555",
                            darkcolor=bg, lightcolor=bg)
            style.configure("TFrame",       background=bg)
            style.configure("TLabelframe",  background=bg)
            style.configure("TLabelframe.Label", background=bg, foreground=fg,
                            font=("Yu Gothic UI", 10, "bold"))
            style.configure("TLabel",       background=bg, foreground=fg)
            style.configure("TCheckbutton", background=bg, foreground=fg)
            style.configure("TRadiobutton", background=bg, foreground=fg)
            style.configure("TEntry",       fieldbackground=field, foreground=fg,
                            font=("Yu Gothic UI", 10))
            style.configure("TCombobox",    fieldbackground=field, foreground=fg)
            style.configure("TButton",      background="#4a4a4a", foreground=fg)
            style.map("TButton",
                      background=[("active", "#5a5a5a"), ("pressed", "#3a3a3a")])
            style.configure("TScrollbar",   background="#4a4a4a", troughcolor=bg)
            style.configure("TSeparator",   background="#555")
            style.configure("Treeview",
                            background=field, foreground=fg,
                            fieldbackground=field,
                            rowheight=26, font=("Yu Gothic UI", 10))
            style.configure("Treeview.Heading",
                            background="#353535", foreground="#cccccc",
                            font=("Yu Gothic UI", 10, "bold"))
            style.map("Treeview",
                      background=[("selected", sel_bg)],
                      foreground=[("selected", "white")])
            style.configure("TNotebook",     background=bg)
            style.configure("TNotebook.Tab",
                            background="#3c3f41", foreground="#aaaaaa",
                            padding=[14, 6], font=("Yu Gothic UI", 10))
            style.map("TNotebook.Tab",
                      background=[("selected", bg)],
                      foreground=[("selected", fg)])
        else:
            for theme in ("vista", "winnative", "clam", "default"):
                if theme in style.theme_names():
                    style.theme_use(theme)
                    break
            font = ("Yu Gothic UI", 10)
            bold = ("Yu Gothic UI", 10, "bold")
            style.configure(".",                   font=font)
            style.configure("TEntry",              font=font)
            style.configure("Treeview",            rowheight=26, font=font)
            style.configure("Treeview.Heading",    font=bold)
            style.configure("TNotebook.Tab",       padding=[14, 6], font=font)
            style.configure("TLabelframe.Label",   font=bold)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Thin toolbar above the notebook for the theme toggle
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill=tk.X, padx=4, pady=(4, 0))
        self._theme_btn = ttk.Button(toolbar, text="🌙 ダーク",
                                     command=self._toggle_theme, width=10)
        self._theme_btn.pack(side=tk.RIGHT)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.battle_tab        = BattleTab(self.notebook)
        self.deck_tab          = DeckTab(self.notebook,
                                         on_deck_changed=self._on_deck_changed)
        self.stats_tab         = StatsTab(self.notebook)
        self.chart_tab         = ChartTab(self.notebook)
        self.color_monitor_tab = ColorMonitorTab(self.notebook)

        self.notebook.add(self.battle_tab.frame,        text="  戦績一覧  ")
        self.notebook.add(self.deck_tab.frame,          text="  デッキ管理  ")
        self.notebook.add(self.stats_tab.frame,         text="  統計  ")
        self.notebook.add(self.chart_tab.frame,         text="  デッキ分布  ")
        self.notebook.add(self.color_monitor_tab.frame, text="  色変化監視  ")

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Apply initial (light) theme colors to tabs with non-ttk widgets
        self._broadcast_theme(_LIGHT)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _toggle_theme(self) -> None:
        self._mode = "dark" if self._mode == "light" else "light"
        self._theme_btn.configure(
            text="☀ ライト" if self._mode == "dark" else "🌙 ダーク")
        self._setup_style()
        self._broadcast_theme(_DARK if self._mode == "dark" else _LIGHT)

    def _broadcast_theme(self, colors: dict) -> None:
        self.battle_tab.apply_theme(colors)
        self.deck_tab.apply_theme(colors)
        self.stats_tab.apply_theme(colors)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_tab_changed(self, event: tk.Event) -> None:
        selected = self.notebook.select()
        tab_text = self.notebook.tab(selected, "text").strip()
        if tab_text == "統計":
            self.stats_tab.refresh_filter_lists()
        elif tab_text == "戦績一覧":
            self.battle_tab.load_battles()

    def _on_deck_changed(self) -> None:
        self.stats_tab.refresh_filter_lists()

    def _on_close(self) -> None:
        self.color_monitor_tab.save_settings()
        self.root.destroy()
