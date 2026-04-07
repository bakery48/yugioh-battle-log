"""Matchup analysis tab – win rates vs each opponent deck."""

import tkinter as tk
from tkinter import ttk
import customtkinter as ctk
from collections import defaultdict

import database as db
from constants import RANKS

_FONT      = ("Meiryo", 10)
_FONT_BOLD = ("Meiryo", 10, "bold")

_COL_CFG = [
    # (column_id,  header,       width, anchor, stretch)
    ("deck",       "相手デッキ", 160,   "w",    True),
    ("total_n",    "総合\n試合", 54,    "center", False),
    ("total_wr",   "総合\n勝率", 66,    "center", False),
    ("first_n",    "先攻\n試合", 54,    "center", False),
    ("first_wr",   "先攻\n勝率", 66,    "center", False),
    ("second_n",   "後攻\n試合", 54,    "center", False),
    ("second_wr",  "後攻\n勝率", 66,    "center", False),
]


def _pct(wins: int, total: int) -> str:
    return f"{wins / total * 100:.1f}%" if total > 0 else "—"


def _sort_key(val: str) -> float:
    """勝率文字列をソートキーに変換。'—'（データなし）は末尾へ。"""
    if val == "—":
        return 999.0
    try:
        return float(val.rstrip("%"))
    except ValueError:
        return 999.0


class MatchupTab:
    def __init__(self, parent: tk.Widget):
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="both", expand=True)
        self._rows: list = []          # 表示中の行データ (dict)
        self._sort_col: str = "first_wr"
        self._sort_rev: bool = False   # 苦手順 = 昇順
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Filter ────────────────────────────────────────────────────────────
        f_outer = ctk.CTkFrame(self.frame, border_width=1)
        f_outer.pack(fill="x", padx=6, pady=(6, 2))
        ctk.CTkLabel(f_outer, text="フィルタ", font=_FONT_BOLD).pack(
            anchor="w", padx=8, pady=(4, 2))

        ff = ctk.CTkFrame(f_outer, fg_color="transparent")
        ff.pack(fill="x", padx=8, pady=(0, 8))

        # 期間
        ctk.CTkLabel(ff, text="期間:", font=_FONT).grid(
            row=0, column=0, sticky="e", padx=(0, 4), pady=3)
        self.date_from_var = tk.StringVar()
        ctk.CTkEntry(ff, textvariable=self.date_from_var, width=110,
                     font=_FONT).grid(row=0, column=1, padx=2)
        ctk.CTkLabel(ff, text="～", font=_FONT).grid(row=0, column=2)
        self.date_to_var = tk.StringVar()
        ctk.CTkEntry(ff, textvariable=self.date_to_var, width=110,
                     font=_FONT).grid(row=0, column=3, padx=2)
        ctk.CTkLabel(ff, text="YYYY-MM-DD", text_color="gray",
                     font=_FONT).grid(row=0, column=4, padx=6)

        # ランク
        ctk.CTkLabel(ff, text="ランク:", font=_FONT).grid(
            row=1, column=0, sticky="e", padx=(0, 4), pady=3)
        rank_inner = ctk.CTkFrame(ff, fg_color="transparent")
        rank_inner.grid(row=1, column=1, columnspan=6, sticky="w")
        self.rank_vars: dict = {}
        for rank in RANKS:
            var = tk.BooleanVar()
            self.rank_vars[rank] = var
            ctk.CTkCheckBox(rank_inner, text=rank, variable=var,
                            font=_FONT, width=56).pack(side="left", padx=3)

        # 最小対戦数
        ctk.CTkLabel(ff, text="最小対戦数:", font=_FONT).grid(
            row=2, column=0, sticky="e", padx=(0, 4), pady=3)
        self.min_n_var = tk.StringVar(value="1")
        ctk.CTkEntry(ff, textvariable=self.min_n_var, width=50,
                     font=_FONT).grid(row=2, column=1, sticky="w")
        ctk.CTkLabel(ff, text="戦以上を表示", text_color="gray",
                     font=_FONT).grid(row=2, column=2, columnspan=2,
                                       sticky="w", padx=2)

        # ボタン
        btn_row = ctk.CTkFrame(ff, fg_color="transparent")
        btn_row.grid(row=3, column=0, columnspan=7, pady=(6, 0))
        ctk.CTkButton(btn_row, text="集計", command=self.calculate,
                      width=80, font=_FONT).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="リセット", command=self.reset,
                      width=80, font=_FONT).pack(side="left", padx=6)

        # ── Table ─────────────────────────────────────────────────────────────
        sort_hint = ctk.CTkFrame(self.frame, fg_color="transparent")
        sort_hint.pack(fill="x", padx=8, pady=(4, 0))
        ctk.CTkLabel(sort_hint,
                     text="列ヘッダをクリックでソート  ／  デフォルト: 先攻勝率（低い順）",
                     text_color="gray", font=("Meiryo", 9)).pack(anchor="w")

        tree_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        cols = [c[0] for c in _COL_CFG]
        self.tree = ttk.Treeview(tree_frame, columns=cols,
                                  show="headings", selectmode="browse")
        for col_id, header, width, anchor, stretch in _COL_CFG:
            self.tree.heading(col_id, text=header,
                              command=lambda c=col_id: self._sort_by(c))
            self.tree.column(col_id, width=width, anchor=anchor,
                             stretch=stretch, minwidth=width)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")

        self.count_label = ctk.CTkLabel(self.frame, text="", font=_FONT)
        self.count_label.pack(anchor="w", padx=10, pady=(0, 4))

    # ── Logic ─────────────────────────────────────────────────────────────────

    def _get_filters(self) -> dict:
        filters: dict = {}
        if self.date_from_var.get().strip():
            filters["date_from"] = self.date_from_var.get().strip()
        if self.date_to_var.get().strip():
            filters["date_to"] = self.date_to_var.get().strip()
        sel = [r for r, v in self.rank_vars.items() if v.get()]
        if sel:
            filters["ranks"] = sel
        return filters

    def _rebuild_tree(self) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)

        # ソートキー決定
        col = self._sort_col
        if col in ("first_wr", "second_wr", "total_wr"):
            key_fn = lambda r: (_sort_key(r[col]), r["deck"])
        elif col == "deck":
            from database import _ja_key
            key_fn = lambda r: _ja_key(r[col])
        else:
            key_fn = lambda r: (r[col], r["deck"])

        rows = sorted(self._rows, key=key_fn, reverse=self._sort_rev)

        for r in rows:
            self.tree.insert("", "end", values=(
                r["deck"],
                r["total_n"],
                r["total_wr"],
                r["first_n"],
                r["first_wr"],
                r["second_n"],
                r["second_wr"],
            ))

        total_battles = sum(r["total_n"] for r in self._rows)
        self.count_label.configure(
            text=f"{len(self._rows)} デッキ  /  総 {total_battles} 戦")

    def calculate(self) -> None:
        filters = self._get_filters()
        battles = db.get_battles(filters or None)

        try:
            min_n = max(1, int(self.min_n_var.get()))
        except ValueError:
            min_n = 1

        # 相手デッキ × 先後攻 で集計
        stats: dict = defaultdict(lambda: {"f_n": 0, "f_w": 0,
                                            "s_n": 0, "s_w": 0})
        for b in battles:
            key = b["opponent_deck"] or "（不明）"
            is_win = b["result"] == "勝利"
            if b["first_second"] == "先攻":
                stats[key]["f_n"] += 1
                stats[key]["f_w"] += int(is_win)
            else:
                stats[key]["s_n"] += 1
                stats[key]["s_w"] += int(is_win)

        self._rows = []
        for deck, s in stats.items():
            total_n = s["f_n"] + s["s_n"]
            if total_n < min_n:
                continue
            total_w = s["f_w"] + s["s_w"]
            self._rows.append({
                "deck":      deck,
                "total_n":   total_n,
                "total_wr":  _pct(total_w, total_n),
                "first_n":   s["f_n"],
                "first_wr":  _pct(s["f_w"], s["f_n"]),
                "second_n":  s["s_n"],
                "second_wr": _pct(s["s_w"], s["s_n"]),
            })

        self._rebuild_tree()

    def reset(self) -> None:
        self.date_from_var.set("")
        self.date_to_var.set("")
        for v in self.rank_vars.values():
            v.set(False)
        self.min_n_var.set("1")
        self._rows = []
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.count_label.configure(text="")

    def _sort_by(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            # 勝率列は昇順（苦手順）をデフォルト、それ以外は降順
            self._sort_rev = col not in ("first_wr", "second_wr", "total_wr",
                                          "deck")
        self._rebuild_tree()

    def apply_theme(self, colors: dict) -> None:
        pass   # Treeview の行タグは使わないためここでは何もしない
