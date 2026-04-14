"""Main application window with tabbed layout."""

import os
import tkinter as tk
from tkinter import ttk

from battle_tab import BattleTab
from deck_tab import DeckTab
from stats_tab import StatsTab
from chart_tab import ChartTab
from matchup_tab import MatchupTab
from color_monitor_tab import ColorMonitorTab

_TREE_LIGHT = {
    "tree_win":   "#e8f5e9",
    "tree_loss":  "#ffebee",
    "listbox_bg": "SystemWindow",
    "listbox_fg": "SystemWindowText",
    "select_bg":  "#0078d4",
    "select_fg":  "white",
}
_TREE_DARK = {
    "tree_win":   "#1a3320",
    "tree_loss":  "#3a1a1a",
    "listbox_bg": "#3c3f41",
    "listbox_fg": "#d0d0d0",
    "select_bg":  "#4b6eaf",
    "select_fg":  "white",
}

_FONT      = ("Meiryo", 10)
_FONT_BOLD = ("Meiryo", 10, "bold")


class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self._is_dark = False
        self._build_ui()
        self._apply_ttk_style(is_dark=False)
        self._broadcast_theme(is_dark=False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill="x", padx=4, pady=(4, 0))

        self._theme_btn = ttk.Button(
            toolbar, text="🌙 ダーク", command=self._toggle_theme, width=10)
        self._theme_btn.pack(side="right")

        self.tabview = ttk.Notebook(self.root)
        self.tabview.pack(fill="both", expand=True, padx=4, pady=4)
        self.tabview.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self._tab_frames: dict = {}
        for name in ("戦績一覧", "デッキ管理", "統計", "相手別勝率", "デッキ分布", "色変化監視"):
            frame = ttk.Frame(self.tabview)
            self.tabview.add(frame, text=name)
            self._tab_frames[name] = frame

        self.battle_tab        = BattleTab(self._tab_frames["戦績一覧"])
        self.deck_tab          = DeckTab(self._tab_frames["デッキ管理"],
                                         on_deck_changed=self._on_deck_changed)
        self.stats_tab         = StatsTab(self._tab_frames["統計"])
        self.matchup_tab       = MatchupTab(self._tab_frames["相手別勝率"])
        # ChartTab and ColorMonitorTab are heavy to initialize; build lazily on first visit
        self.chart_tab         = ChartTab(self._tab_frames["デッキ分布"])
        self.color_monitor_tab = None   # created on first visit

    # ── TTK style ─────────────────────────────────────────────────────────────

    def _apply_ttk_style(self, is_dark: bool) -> None:
        style = ttk.Style()
        if is_dark:
            style.theme_use("clam")
            bg, fg, field = "#2b2b2b", "#d0d0d0", "#3c3f41"
            sel_bg = "#4b6eaf"
            style.configure(".",
                            background=bg, foreground=fg,
                            fieldbackground=field, troughcolor=bg,
                            bordercolor="#555", darkcolor=bg, lightcolor=bg,
                            font=_FONT)
            style.configure("TFrame",       background=bg)
            style.configure("TLabelframe",  background=bg)
            style.configure("TLabelframe.Label", background=bg, foreground=fg,
                            font=_FONT_BOLD)
            style.configure("TLabel",       background=bg, foreground=fg, font=_FONT)
            style.configure("TCheckbutton", background=bg, foreground=fg, font=_FONT)
            style.configure("TRadiobutton", background=bg, foreground=fg, font=_FONT)
            style.configure("TCombobox",    fieldbackground=field, foreground=fg,
                            selectbackground=sel_bg, selectforeground="white",
                            insertcolor=fg, arrowcolor=fg, font=_FONT)
            style.map("TCombobox",
                      fieldbackground=[("readonly", field), ("disabled", bg)],
                      foreground=[("readonly", fg), ("disabled", "#888")],
                      selectbackground=[("readonly", field)],
                      selectforeground=[("readonly", fg)],
                      arrowcolor=[("disabled", "#888")])
            style.configure("TEntry",       fieldbackground=field, foreground=fg,
                            selectbackground=sel_bg, selectforeground="white",
                            insertcolor=fg, font=_FONT)
            style.configure("TButton",      background="#4a4a4a", foreground=fg,
                            font=_FONT)
            style.map("TButton",
                      background=[("active", "#5a5a5a"), ("pressed", "#3a3a3a")])
            style.configure("TScrollbar",   background="#4a4a4a", troughcolor=bg)
            style.configure("TSeparator",   background="#555")
            style.configure("TScale",       background=bg, troughcolor=field,
                            sliderlength=15)
            style.configure("Treeview",
                            background=field, foreground=fg,
                            fieldbackground=field, rowheight=26, font=_FONT)
            style.configure("Treeview.Heading",
                            background="#353535", foreground="#cccccc",
                            font=_FONT_BOLD)
            style.map("Treeview",
                      background=[("selected", sel_bg)],
                      foreground=[("selected", "white")])
            style.configure("TPanedwindow", background=bg)
            style.configure("TNotebook",    background=bg, tabmargins=[2, 5, 2, 0])
            style.configure("TNotebook.Tab", background=field, foreground=fg,
                            padding=[8, 4], font=_FONT)
            style.map("TNotebook.Tab",
                      background=[("selected", sel_bg), ("active", "#4a4a4a")],
                      foreground=[("selected", "white"), ("active", fg)])
        else:
            for theme in ("vista", "winnative", "clam", "default"):
                if theme in style.theme_names():
                    style.theme_use(theme)
                    break
            style.configure(".",                 font=_FONT)
            style.configure("TEntry",            font=_FONT)
            style.configure("Treeview",          rowheight=26, font=_FONT)
            style.configure("Treeview.Heading",  font=_FONT_BOLD)
            style.configure("TLabelframe.Label", font=_FONT_BOLD)
            style.configure("TNotebook.Tab",     font=_FONT)

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _toggle_theme(self) -> None:
        self._is_dark = not self._is_dark
        self._theme_btn.configure(text="☀ ライト" if self._is_dark else "🌙 ダーク")
        self._apply_ttk_style(self._is_dark)
        self._broadcast_theme(self._is_dark)

    def _broadcast_theme(self, is_dark: bool) -> None:
        colors = _TREE_DARK if is_dark else _TREE_LIGHT
        self.battle_tab.apply_theme(colors)
        self.deck_tab.apply_theme(colors)
        self.stats_tab.apply_theme(colors, is_dark)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_tab_changed(self, event=None) -> None:
        try:
            tab_name = self.tabview.tab(self.tabview.select(), "text")
        except Exception:
            return
        if tab_name == "デッキ分布":
            self.chart_tab.build_if_needed()
        elif tab_name == "色変化監視":
            if self.color_monitor_tab is None:
                self.color_monitor_tab = ColorMonitorTab(
                    self._tab_frames["色変化監視"])
        elif tab_name == "統計":
            self.stats_tab.refresh_filter_lists()
        elif tab_name == "戦績一覧":
            self.battle_tab.load_battles()

    def _on_deck_changed(self) -> None:
        self.stats_tab.refresh_filter_lists()

    def _on_close(self) -> None:
        if self.color_monitor_tab is not None:
            self.color_monitor_tab.save_settings()
        os._exit(0)
