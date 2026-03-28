"""Main application window with tabbed layout."""

import tkinter as tk
from tkinter import ttk

from battle_tab import BattleTab
from deck_tab import DeckTab
from stats_tab import StatsTab
from chart_tab import ChartTab
from ime_utils import suppress_ime_popup


class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self._setup_style()
        self._build_ui()
        suppress_ime_popup(root)  # Covers all Entry widgets in the main window

    # ── Style ─────────────────────────────────────────────────────────────────

    def _setup_style(self) -> None:
        style = ttk.Style()
        # "vista" looks native on Windows; fall back gracefully on other OS
        for theme in ("vista", "winnative", "clam", "default"):
            if theme in style.theme_names():
                style.theme_use(theme)
                break

        font = ("Yu Gothic UI", 10)
        bold = ("Yu Gothic UI", 10, "bold")
        style.configure(".", font=font)
        style.configure("Treeview", rowheight=26, font=font)
        style.configure("Treeview.Heading", font=bold)
        style.configure("TNotebook.Tab", padding=[14, 6], font=font)
        style.configure("TLabelframe.Label", font=bold)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.battle_tab = BattleTab(self.notebook)
        self.deck_tab = DeckTab(
            self.notebook, on_deck_changed=self._on_deck_changed
        )
        self.stats_tab = StatsTab(self.notebook)
        self.chart_tab = ChartTab(self.notebook)

        self.notebook.add(self.battle_tab.frame,  text="  戦績一覧  ")
        self.notebook.add(self.deck_tab.frame,    text="  デッキ管理  ")
        self.notebook.add(self.stats_tab.frame,   text="  統計  ")
        self.notebook.add(self.chart_tab.frame,   text="  デッキ分布  ")

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_tab_changed(self, event: tk.Event) -> None:
        selected = self.notebook.select()
        tab_text = self.notebook.tab(selected, "text").strip()
        if tab_text == "統計":
            self.stats_tab.refresh_filter_lists()
        elif tab_text == "戦績一覧":
            # Re-query in case decks changed names
            self.battle_tab.load_battles()

    def _on_deck_changed(self) -> None:
        """Called by DeckTab whenever decks are added / edited / deleted."""
        self.stats_tab.refresh_filter_lists()
