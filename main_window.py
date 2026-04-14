"""Main application window with tabbed layout."""

import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

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
    def __init__(self, root: ctk.CTk):
        self.root = root
        self._build_ui()
        self._apply_ttk_style(is_dark=False)
        self._broadcast_theme(is_dark=False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        toolbar = ctk.CTkFrame(self.root, height=36, fg_color="transparent")
        toolbar.pack(fill="x", padx=4, pady=(4, 0))

        self._theme_btn = ctk.CTkButton(
            toolbar, text="🌙 ダーク", command=self._toggle_theme,
            width=90, font=ctk.CTkFont(family="Meiryo", size=10),
        )
        self._theme_btn.pack(side="right")

        self.tabview = ctk.CTkTabview(self.root, command=self._on_tab_changed)
        self.tabview.pack(fill="both", expand=True, padx=4, pady=4)
        # Set tab button font via the internal segmented button
        try:
            self.tabview._segmented_button.configure(
                font=ctk.CTkFont(family="Meiryo", size=10)
            )
        except Exception:
            pass

        for name in ("戦績一覧", "デッキ管理", "統計", "相手別勝率", "デッキ分布", "色変化監視"):
            self.tabview.add(name)

        self.battle_tab        = BattleTab(self.tabview.tab("戦績一覧"))
        self.deck_tab          = DeckTab(self.tabview.tab("デッキ管理"),
                                         on_deck_changed=self._on_deck_changed)
        self.stats_tab         = StatsTab(self.tabview.tab("統計"))
        self.matchup_tab       = MatchupTab(self.tabview.tab("相手別勝率"))
        self.chart_tab         = ChartTab(self.tabview.tab("デッキ分布"))
        self.color_monitor_tab = ColorMonitorTab(self.tabview.tab("色変化監視"))

    # ── TTK style (for Treeview / Listbox / PanedWindow) ──────────────────────

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

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _toggle_theme(self) -> None:
        is_dark = ctk.get_appearance_mode().lower() != "dark"
        ctk.set_appearance_mode("dark" if is_dark else "light")
        self._theme_btn.configure(text="☀ ライト" if is_dark else "🌙 ダーク")
        self._apply_ttk_style(is_dark)
        self._broadcast_theme(is_dark)

    def _broadcast_theme(self, is_dark: bool) -> None:
        colors = _TREE_DARK if is_dark else _TREE_LIGHT
        self.battle_tab.apply_theme(colors)
        self.deck_tab.apply_theme(colors)
        self.stats_tab.apply_theme(colors, is_dark)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_tab_changed(self) -> None:
        tab_name = self.tabview.get()
        if tab_name == "統計":
            self.stats_tab.refresh_filter_lists()
        elif tab_name == "戦績一覧":
            self.battle_tab.load_battles()

    def _on_deck_changed(self) -> None:
        self.stats_tab.refresh_filter_lists()

    def _on_close(self) -> None:
        self.color_monitor_tab.save_settings()
        self.root.withdraw()  # 即座にウィンドウを隠す（体感速度向上）
        self.root.quit()      # mainloop を終了 → main.py で os._exit(0)
