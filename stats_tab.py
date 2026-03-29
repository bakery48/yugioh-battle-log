"""Statistics tab – win rates with flexible filtering."""

import tkinter as tk
from tkinter import ttk

import database as db
from constants import RANKS


def _pct(num: int, denom: int) -> str:
    return f"{num / denom * 100:.1f}%" if denom > 0 else "—"


_LIGHT_STATS_ROWS = ["#f0f4ff", "#f9f9f9", "#fffde7"]
_DARK_STATS_ROWS  = ["#1e2040", "#2a2a2a", "#2a2510"]


class StatsTab:
    def __init__(self, parent: tk.Widget):
        self.frame = ttk.Frame(parent)
        self._decks: list = []
        self._tags: list = []
        self._colors: dict = {}   # set by apply_theme before calculate() is called
        self._build_ui()
        self.refresh_filter_lists()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Filter panel ──────────────────────────────────────────────────────
        filter_frame = ttk.LabelFrame(self.frame, text="フィルタ", padding=8)
        filter_frame.pack(fill=tk.X, padx=6, pady=(6, 2))

        # Row 0 – date range
        ttk.Label(filter_frame, text="期間:").grid(row=0, column=0, sticky=tk.E, padx=(0, 4), pady=3)
        self.date_from_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.date_from_var, width=12).grid(
            row=0, column=1, padx=2
        )
        ttk.Label(filter_frame, text="～").grid(row=0, column=2)
        self.date_to_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.date_to_var, width=12).grid(
            row=0, column=3, padx=2
        )
        ttk.Label(filter_frame, text="YYYY-MM-DD", foreground="gray").grid(
            row=0, column=4, padx=6
        )

        # Row 1 – ranks
        ttk.Label(filter_frame, text="ランク:").grid(row=1, column=0, sticky=tk.E, padx=(0, 4), pady=3)
        rank_inner = ttk.Frame(filter_frame)
        rank_inner.grid(row=1, column=1, columnspan=6, sticky=tk.W)
        self.rank_vars: dict = {}
        for rank in RANKS:
            var = tk.BooleanVar()
            self.rank_vars[rank] = var
            ttk.Checkbutton(rank_inner, text=rank, variable=var).pack(
                side=tk.LEFT, padx=3
            )

        # Row 2 – deck & tag multi-select
        ttk.Label(filter_frame, text="使用デッキ:").grid(
            row=2, column=0, sticky=tk.NE, padx=(0, 4), pady=3
        )

        deck_frame = ttk.Frame(filter_frame)
        deck_frame.grid(row=2, column=1, columnspan=3, sticky=tk.W, pady=3)
        self.deck_listbox = tk.Listbox(
            deck_frame, selectmode=tk.MULTIPLE, height=5, width=26, exportselection=False
        )
        dsb = ttk.Scrollbar(deck_frame, orient=tk.VERTICAL, command=self.deck_listbox.yview)
        self.deck_listbox.configure(yscrollcommand=dsb.set)
        self.deck_listbox.pack(side=tk.LEFT)
        dsb.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Label(filter_frame, text="タグ:").grid(
            row=2, column=4, sticky=tk.NE, padx=(14, 4), pady=3
        )
        tag_frame = ttk.Frame(filter_frame)
        tag_frame.grid(row=2, column=5, columnspan=3, sticky=tk.W, pady=3)
        self.tag_listbox = tk.Listbox(
            tag_frame, selectmode=tk.MULTIPLE, height=5, width=22, exportselection=False
        )
        tsb = ttk.Scrollbar(tag_frame, orient=tk.VERTICAL, command=self.tag_listbox.yview)
        self.tag_listbox.configure(yscrollcommand=tsb.set)
        self.tag_listbox.pack(side=tk.LEFT)
        tsb.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Label(filter_frame, text="※ Ctrl+クリックで複数選択", foreground="gray").grid(
            row=3, column=1, columnspan=7, sticky=tk.W
        )

        # Row 4 – buttons
        btn_row = ttk.Frame(filter_frame)
        btn_row.grid(row=4, column=0, columnspan=8, pady=(6, 2))
        ttk.Button(btn_row, text="集計", command=self.calculate, width=8).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(btn_row, text="リセット", command=self.reset, width=8).pack(
            side=tk.LEFT, padx=6
        )

        # ── Result area ───────────────────────────────────────────────────────
        self.result_frame = ttk.LabelFrame(self.frame, text="集計結果", padding=12)
        self.result_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self._show_placeholder()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _show_placeholder(self) -> None:
        for w in self.result_frame.winfo_children():
            w.destroy()
        ttk.Label(
            self.result_frame,
            text="フィルタを設定して「集計」ボタンを押してください。",
            foreground="gray",
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

        self.deck_listbox.delete(0, tk.END)
        for d in self._decks:
            self.deck_listbox.insert(tk.END, d["name"])

        self.tag_listbox.delete(0, tk.END)
        for t in self._tags:
            self.tag_listbox.insert(tk.END, t["name"])

    def apply_theme(self, colors: dict) -> None:
        self._colors = colors
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
        self.deck_listbox.selection_clear(0, tk.END)
        self.tag_listbox.selection_clear(0, tk.END)
        self._show_placeholder()

    def calculate(self) -> None:
        filters = self._get_filters()
        battles = db.get_battles(filters or None)

        for w in self.result_frame.winfo_children():
            w.destroy()

        if not battles:
            ttk.Label(
                self.result_frame,
                text="該当する戦績がありません。",
                foreground="gray",
            ).pack(pady=30)
            return

        total = len(battles)
        wins = sum(1 for b in battles if b["result"] == "勝利")
        losses = total - wins

        first = [b for b in battles if b["first_second"] == "先攻"]
        second = [b for b in battles if b["first_second"] == "後攻"]
        first_wins = sum(1 for b in first if b["result"] == "勝利")
        second_wins = sum(1 for b in second if b["result"] == "勝利")

        # ── Summary line ──────────────────────────────────────────────────────
        summary = ttk.Frame(self.result_frame)
        summary.pack(pady=(4, 10))
        ttk.Label(
            summary,
            text=f"総試合数  {total} 試合　　{wins} 勝 {losses} 敗　　総合勝率 {_pct(wins, total)}",
            font=("Meiryo", 13, "bold"),
        ).pack()

        ttk.Separator(self.result_frame, orient=tk.HORIZONTAL).pack(
            fill=tk.X, padx=20, pady=4
        )

        # ── Stats table ───────────────────────────────────────────────────────
        tbl = ttk.Frame(self.result_frame)
        tbl.pack()

        headers = ["区分", "試合数", "勝利", "敗北", "勝率", "比率（先後攻率）"]
        col_widths = [7, 7, 7, 7, 9, 16]
        bold = ("Meiryo", 10, "bold")

        for c, (h, w) in enumerate(zip(headers, col_widths)):
            ttk.Label(
                tbl, text=h, font=bold, width=w, anchor=tk.CENTER,
                relief="groove", padding=(4, 3),
            ).grid(row=0, column=c, padx=1, pady=1, sticky="nsew")

        rows = [
            (
                "先攻",
                len(first),
                first_wins,
                len(first) - first_wins,
                _pct(first_wins, len(first)),
                _pct(len(first), total),
            ),
            (
                "後攻",
                len(second),
                second_wins,
                len(second) - second_wins,
                _pct(second_wins, len(second)),
                _pct(len(second), total),
            ),
            (
                "合計",
                total,
                wins,
                losses,
                _pct(wins, total),
                "—",
            ),
        ]

        row_colors = (self._colors.get("stats_rows") or _LIGHT_STATS_ROWS)
        fg = self._colors.get("stats_fg", "black")
        for r, (row_data, bg) in enumerate(zip(rows, row_colors), start=1):
            for c, val in enumerate(row_data):
                tk.Label(
                    tbl,
                    text=str(val),
                    width=col_widths[c],
                    anchor=tk.CENTER,
                    background=bg,
                    foreground=fg,
                    relief="groove",
                    padx=4,
                    pady=4,
                ).grid(row=r, column=c, padx=1, pady=1, sticky="nsew")
