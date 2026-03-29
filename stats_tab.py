"""Statistics tab – win rates with flexible filtering."""

import tkinter as tk
from tkinter import ttk
import customtkinter as ctk

import database as db
from constants import RANKS

_FONT      = ctk.CTkFont(family="Meiryo", size=10)
_FONT_BOLD = ctk.CTkFont(family="Meiryo", size=10, weight="bold")
_FONT_SUM  = ctk.CTkFont(family="Meiryo", size=13, weight="bold")

_LIGHT_STATS_ROWS = ["#f0f4ff", "#f9f9f9", "#fffde7"]
_DARK_STATS_ROWS  = ["#1e2040", "#2a2a2a", "#2a2510"]


def _pct(num: int, denom: int) -> str:
    return f"{num / denom * 100:.1f}%" if denom > 0 else "—"


class StatsTab:
    def __init__(self, parent: tk.Widget):
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="both", expand=True)
        self._decks: list = []
        self._tags: list = []
        self._is_dark: bool = False
        self._listbox_colors: dict = {}
        self._build_ui()
        self.refresh_filter_lists()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Filter panel ──────────────────────────────────────────────────────
        filter_outer = ctk.CTkFrame(self.frame, border_width=1)
        filter_outer.pack(fill="x", padx=6, pady=(6, 2))
        ctk.CTkLabel(filter_outer, text="フィルタ", font=_FONT_BOLD).pack(
            anchor="w", padx=8, pady=(4, 2))

        filter_frame = ctk.CTkFrame(filter_outer, fg_color="transparent")
        filter_frame.pack(fill="x", padx=8, pady=(0, 8))

        # Row 0 – date range
        ctk.CTkLabel(filter_frame, text="期間:", font=_FONT).grid(
            row=0, column=0, sticky="e", padx=(0, 4), pady=3)
        self.date_from_var = tk.StringVar()
        ctk.CTkEntry(filter_frame, textvariable=self.date_from_var, width=110,
                     font=_FONT).grid(row=0, column=1, padx=2)
        ctk.CTkLabel(filter_frame, text="～", font=_FONT).grid(row=0, column=2)
        self.date_to_var = tk.StringVar()
        ctk.CTkEntry(filter_frame, textvariable=self.date_to_var, width=110,
                     font=_FONT).grid(row=0, column=3, padx=2)
        ctk.CTkLabel(filter_frame, text="YYYY-MM-DD", text_color="gray",
                     font=_FONT).grid(row=0, column=4, padx=6)

        # Row 1 – ranks
        ctk.CTkLabel(filter_frame, text="ランク:", font=_FONT).grid(
            row=1, column=0, sticky="e", padx=(0, 4), pady=3)
        rank_inner = ctk.CTkFrame(filter_frame, fg_color="transparent")
        rank_inner.grid(row=1, column=1, columnspan=6, sticky="w")
        self.rank_vars: dict = {}
        for rank in RANKS:
            var = tk.BooleanVar()
            self.rank_vars[rank] = var
            ctk.CTkCheckBox(rank_inner, text=rank, variable=var,
                            font=_FONT, width=56).pack(side="left", padx=3)

        # Row 2 – deck & tag multi-select (keep tk.Listbox — no CTk equivalent)
        ctk.CTkLabel(filter_frame, text="使用デッキ:", font=_FONT).grid(
            row=2, column=0, sticky="ne", padx=(0, 4), pady=3)

        deck_frame = ctk.CTkFrame(filter_frame, fg_color="transparent")
        deck_frame.grid(row=2, column=1, columnspan=3, sticky="w", pady=3)
        self.deck_listbox = tk.Listbox(
            deck_frame, selectmode="multiple", height=5, width=26,
            exportselection=False, font=("Meiryo", 10))
        dsb = ttk.Scrollbar(deck_frame, orient="vertical",
                            command=self.deck_listbox.yview)
        self.deck_listbox.configure(yscrollcommand=dsb.set)
        self.deck_listbox.pack(side="left")
        dsb.pack(side="left", fill="y")

        ctk.CTkLabel(filter_frame, text="タグ:", font=_FONT).grid(
            row=2, column=4, sticky="ne", padx=(14, 4), pady=3)
        tag_frame = ctk.CTkFrame(filter_frame, fg_color="transparent")
        tag_frame.grid(row=2, column=5, columnspan=3, sticky="w", pady=3)
        self.tag_listbox = tk.Listbox(
            tag_frame, selectmode="multiple", height=5, width=22,
            exportselection=False, font=("Meiryo", 10))
        tsb = ttk.Scrollbar(tag_frame, orient="vertical",
                            command=self.tag_listbox.yview)
        self.tag_listbox.configure(yscrollcommand=tsb.set)
        self.tag_listbox.pack(side="left")
        tsb.pack(side="left", fill="y")

        ctk.CTkLabel(filter_frame, text="※ Ctrl+クリックで複数選択",
                     text_color="gray", font=_FONT).grid(
            row=3, column=1, columnspan=7, sticky="w")

        # Row 4 – buttons
        btn_row = ctk.CTkFrame(filter_frame, fg_color="transparent")
        btn_row.grid(row=4, column=0, columnspan=8, pady=(6, 2))
        ctk.CTkButton(btn_row, text="集計", command=self.calculate,
                      width=80, font=_FONT).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="リセット", command=self.reset,
                      width=80, font=_FONT).pack(side="left", padx=6)

        # ── Result area ───────────────────────────────────────────────────────
        result_outer = ctk.CTkFrame(self.frame, border_width=1)
        result_outer.pack(fill="both", expand=True, padx=6, pady=6)
        ctk.CTkLabel(result_outer, text="集計結果", font=_FONT_BOLD).pack(
            anchor="w", padx=8, pady=(4, 2))
        self.result_frame = ctk.CTkFrame(result_outer, fg_color="transparent")
        self.result_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._show_placeholder()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _show_placeholder(self) -> None:
        for w in self.result_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.result_frame,
            text="フィルタを設定して「集計」ボタンを押してください。",
            text_color="gray", font=_FONT,
        ).pack(pady=30)

    def _get_filters(self) -> dict:
        filters: dict = {}
        if self.date_from_var.get().strip():
            filters["date_from"] = self.date_from_var.get().strip()
        if self.date_to_var.get().strip():
            filters["date_to"] = self.date_to_var.get().strip()
        selected_ranks = [r for r, v in self.rank_vars.items() if v.get()]
        if selected_ranks:
            filters["ranks"] = selected_ranks
        deck_sel = self.deck_listbox.curselection()
        if deck_sel:
            filters["deck_ids"] = [self._decks[i]["id"] for i in deck_sel]
        tag_sel = self.tag_listbox.curselection()
        if tag_sel:
            filters["tag_ids"] = [self._tags[i]["id"] for i in tag_sel]
        return filters

    # ── Public ────────────────────────────────────────────────────────────────

    def refresh_filter_lists(self) -> None:
        self._decks = db.get_all_decks()
        self._tags = db.get_all_tags()
        self.deck_listbox.delete(0, "end")
        for d in self._decks:
            self.deck_listbox.insert("end", d["name"])
        self.tag_listbox.delete(0, "end")
        for t in self._tags:
            self.tag_listbox.insert("end", t["name"])

    def apply_theme(self, colors: dict, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._listbox_colors = colors
        lb_cfg = dict(bg=colors["listbox_bg"], fg=colors["listbox_fg"],
                      selectbackground=colors["select_bg"],
                      selectforeground=colors["select_fg"])
        self.deck_listbox.configure(**lb_cfg)
        self.tag_listbox.configure(**lb_cfg)

    def reset(self) -> None:
        self.date_from_var.set("")
        self.date_to_var.set("")
        for v in self.rank_vars.values():
            v.set(False)
        self.deck_listbox.selection_clear(0, "end")
        self.tag_listbox.selection_clear(0, "end")
        self._show_placeholder()

    def calculate(self) -> None:
        filters = self._get_filters()
        battles = db.get_battles(filters or None)

        for w in self.result_frame.winfo_children():
            w.destroy()

        if not battles:
            ctk.CTkLabel(
                self.result_frame,
                text="該当する戦績がありません。",
                text_color="gray", font=_FONT,
            ).pack(pady=30)
            return

        total = len(battles)
        wins  = sum(1 for b in battles if b["result"] == "勝利")
        losses = total - wins

        first  = [b for b in battles if b["first_second"] == "先攻"]
        second = [b for b in battles if b["first_second"] == "後攻"]
        first_wins  = sum(1 for b in first  if b["result"] == "勝利")
        second_wins = sum(1 for b in second if b["result"] == "勝利")

        # Summary
        summary = ctk.CTkFrame(self.result_frame, fg_color="transparent")
        summary.pack(pady=(4, 10))
        ctk.CTkLabel(
            summary,
            text=(f"総試合数  {total} 試合　　"
                  f"{wins} 勝 {losses} 敗　　総合勝率 {_pct(wins, total)}"),
            font=_FONT_SUM,
        ).pack()

        ttk.Separator(self.result_frame, orient="horizontal").pack(
            fill="x", padx=20, pady=4)

        # Stats table (tk.Label for per-cell background colors)
        tbl = ctk.CTkFrame(self.result_frame, fg_color="transparent")
        tbl.pack()

        headers    = ["区分", "試合数", "勝利", "敗北", "勝率", "比率（先後攻率）"]
        col_widths = [7, 7, 7, 7, 9, 16]
        bold_tk    = ("Meiryo", 10, "bold")

        for c, (h, w) in enumerate(zip(headers, col_widths)):
            ttk.Label(
                tbl, text=h, font=bold_tk, width=w, anchor="center",
                relief="groove", padding=(4, 3),
            ).grid(row=0, column=c, padx=1, pady=1, sticky="nsew")

        rows = [
            ("先攻",  len(first),  first_wins,  len(first)  - first_wins,
             _pct(first_wins,  len(first)),  _pct(len(first),  total)),
            ("後攻",  len(second), second_wins, len(second) - second_wins,
             _pct(second_wins, len(second)), _pct(len(second), total)),
            ("合計",  total,       wins,         losses,
             _pct(wins, total), "—"),
        ]

        row_colors = _DARK_STATS_ROWS if self._is_dark else _LIGHT_STATS_ROWS
        fg = "#d0d0d0" if self._is_dark else "black"
        for r, (row_data, bg) in enumerate(zip(rows, row_colors), start=1):
            for c, val in enumerate(row_data):
                tk.Label(
                    tbl, text=str(val), width=col_widths[c],
                    anchor="center", background=bg, foreground=fg,
                    relief="groove", padx=4, pady=4,
                ).grid(row=r, column=c, padx=1, pady=1, sticky="nsew")
