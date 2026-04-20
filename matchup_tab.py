"""Matchup analysis tab – win rates vs each opponent deck, or by own deck."""

import tkinter as tk
from tkinter import ttk
from collections import defaultdict

import database as db
from constants import RANKS

_FONT      = ("Meiryo", 10)
_FONT_BOLD = ("Meiryo", 10, "bold")

_COL_CFG = [
    # (column_id,   header,       width, anchor)
    ("deck",        "相手デッキ", 160,   "w"),
    ("total_n",     "総合試合",    60,   "center"),
    ("total_wr",    "総合勝率",    72,   "center"),
    ("first_n",     "先攻試合",    60,   "center"),
    ("first_wr",    "先攻勝率",    72,   "center"),
    ("second_n",    "後攻試合",    60,   "center"),
    ("second_wr",   "後攻勝率",    72,   "center"),
    ("second_adv",  "後攻有利%",   72,   "center"),
]

_WR_COLS = {"first_wr", "second_wr", "total_wr", "second_adv"}


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
        self.frame = ttk.Frame(parent)
        self.frame.pack(fill="both", expand=True)
        self._rows: list = []
        self._sort_col: str = "first_wr"
        self._sort_rev: bool = False   # 苦手順 = 昇順
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Filter ────────────────────────────────────────────────────────────
        f_outer = ttk.LabelFrame(self.frame, text="フィルタ", padding=6)
        f_outer.pack(fill="x", padx=6, pady=(6, 2))

        ff = ttk.Frame(f_outer)
        ff.pack(fill="x", padx=8, pady=(0, 8))

        # 期間
        ttk.Label(ff, text="期間:").grid(
            row=0, column=0, sticky="e", padx=(0, 4), pady=3)
        self.date_from_var = tk.StringVar()
        ttk.Entry(ff, textvariable=self.date_from_var, width=12).grid(
            row=0, column=1, padx=2)
        ttk.Label(ff, text="～").grid(row=0, column=2)
        self.date_to_var = tk.StringVar()
        ttk.Entry(ff, textvariable=self.date_to_var, width=12).grid(
            row=0, column=3, padx=2)
        ttk.Label(ff, text="YYYY-MM-DD", foreground="gray").grid(
            row=0, column=4, padx=6)

        # ランク
        ttk.Label(ff, text="ランク:").grid(
            row=1, column=0, sticky="e", padx=(0, 4), pady=3)
        rank_inner = ttk.Frame(ff)
        rank_inner.grid(row=1, column=1, columnspan=6, sticky="w")
        self.rank_vars: dict = {}
        for rank in RANKS:
            var = tk.BooleanVar()
            self.rank_vars[rank] = var
            ttk.Checkbutton(rank_inner, text=rank, variable=var).pack(
                side="left", padx=3)

        # 相手デッキ絞り込み
        ttk.Label(ff, text="相手デッキ:").grid(
            row=2, column=0, sticky="e", padx=(0, 4), pady=3)
        self.opp_deck_var = tk.StringVar()
        self.opp_deck_combo = ttk.Combobox(
            ff, textvariable=self.opp_deck_var, width=26, state="readonly")
        self.opp_deck_combo.grid(row=2, column=1, columnspan=3, sticky="w", padx=2)
        ttk.Button(ff, text="クリア",
                   command=lambda: self.opp_deck_var.set(""),
                   width=5).grid(row=2, column=4, padx=(4, 0))

        # 最小対戦数
        ttk.Label(ff, text="最小対戦数:").grid(
            row=3, column=0, sticky="e", padx=(0, 4), pady=3)
        self.min_n_var = tk.StringVar(value="1")
        ttk.Entry(ff, textvariable=self.min_n_var, width=6).grid(
            row=3, column=1, sticky="w")
        ttk.Label(ff, text="戦以上を表示", foreground="gray").grid(
            row=3, column=2, columnspan=2, sticky="w", padx=2)

        # 分析軸
        ttk.Label(ff, text="分析軸:").grid(
            row=4, column=0, sticky="e", padx=(0, 4), pady=3)
        self._axis_var = tk.StringVar(value="opponent")
        axis_inner = ttk.Frame(ff)
        axis_inner.grid(row=4, column=1, columnspan=6, sticky="w")
        ttk.Radiobutton(axis_inner, text="相手デッキ別",
                        variable=self._axis_var, value="opponent").pack(
            side="left", padx=(0, 16))
        ttk.Radiobutton(axis_inner, text="自デッキ別",
                        variable=self._axis_var, value="own").pack(side="left")

        # ボタン
        btn_row = ttk.Frame(ff)
        btn_row.grid(row=5, column=0, columnspan=7, pady=(6, 0))
        ttk.Button(btn_row, text="集計", command=self.calculate).pack(
            side="left", padx=6)
        ttk.Button(btn_row, text="リセット", command=self.reset).pack(
            side="left", padx=6)

        # ── Table ─────────────────────────────────────────────────────────────
        sort_hint = ttk.Frame(self.frame)
        sort_hint.pack(fill="x", padx=8, pady=(4, 0))
        ttk.Label(sort_hint,
                  text="列ヘッダをクリックでソート  ／  デフォルト: 先攻勝率（低い順）"
                       "  ／  後攻有利%: 後攻プレイヤーが勝つ確率（50%超＝後攻有利）",
                  foreground="gray").pack(anchor="w")

        tree_frame = ttk.Frame(self.frame)
        tree_frame.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        cols = [c[0] for c in _COL_CFG]
        self.tree = ttk.Treeview(tree_frame, columns=cols,
                                  show="headings", selectmode="browse")
        for col_id, header, width, anchor in _COL_CFG:
            self.tree.heading(col_id, text=header,
                              command=lambda c=col_id: self._sort_by(c))
            self.tree.column(col_id, width=width, anchor=anchor,
                             stretch=True, minwidth=30)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")

        self.count_label = ttk.Label(self.frame, text="")
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
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)

        col = self._sort_col
        if col in _WR_COLS:
            key_fn = lambda r: (_sort_key(r[col]), r["deck"])
        elif col == "deck":
            from database import _ja_key
            key_fn = lambda r: _ja_key(r[col])
        else:
            key_fn = lambda r: (r[col], r["deck"])

        for r in sorted(self._rows, key=key_fn, reverse=self._sort_rev):
            self.tree.insert("", "end", values=(
                r["deck"],
                r["total_n"],
                r["total_wr"],
                r["first_n"],
                r["first_wr"],
                r["second_n"],
                r["second_wr"],
                r["second_adv"],
            ))

        total_battles = sum(r["total_n"] for r in self._rows)
        self.count_label.configure(
            text=f"{len(self._rows)} デッキ  /  総 {total_battles} 戦")

    def refresh_opp_deck_list(self) -> None:
        current = self.opp_deck_var.get()
        values = db.get_distinct_opponent_decks()
        self.opp_deck_combo["values"] = values
        if current and current not in values:
            self.opp_deck_var.set("")

    def calculate(self) -> None:
        self.refresh_opp_deck_list()
        filters = self._get_filters()
        battles = db.get_battles(filters or None)

        opp_filter = self.opp_deck_var.get().strip()
        if opp_filter:
            battles = [b for b in battles if b["opponent_deck"] == opp_filter]

        try:
            min_n = max(1, int(self.min_n_var.get()))
        except ValueError:
            min_n = 1

        mode = self._axis_var.get()  # "opponent" or "own"

        stats: dict = defaultdict(lambda: {"f_n": 0, "f_w": 0,
                                            "s_n": 0, "s_w": 0})
        for b in battles:
            key = (b["opponent_deck"] or "（不明）") if mode == "opponent" \
                  else (b["deck_name"] or "（削除済み）")
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
            # 後攻有利% = 後攻プレイヤーが勝った割合
            # = (自分後攻勝利 + 自分先攻敗北) / 総試合
            second_adv = _pct(s["s_w"] + (s["f_n"] - s["f_w"]), total_n)
            self._rows.append({
                "deck":       deck,
                "total_n":    total_n,
                "total_wr":   _pct(total_w, total_n),
                "first_n":    s["f_n"],
                "first_wr":   _pct(s["f_w"], s["f_n"]),
                "second_n":   s["s_n"],
                "second_wr":  _pct(s["s_w"], s["s_n"]),
                "second_adv": second_adv,
            })

        # デッキ列ヘッダを軸と絞り込みに合わせて更新
        if mode == "opponent":
            heading = "相手デッキ"
        elif opp_filter:
            heading = f"自デッキ (vs {opp_filter})"
        else:
            heading = "自デッキ"
        self.tree.heading("deck", text=heading)

        self._rebuild_tree()

    def reset(self) -> None:
        self.date_from_var.set("")
        self.date_to_var.set("")
        for v in self.rank_vars.values():
            v.set(False)
        self.opp_deck_var.set("")
        self.min_n_var.set("1")
        self._axis_var.set("opponent")
        self._rows = []
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)
        self.tree.heading("deck", text="相手デッキ")
        self.count_label.configure(text="")

    def _sort_by(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            # 勝率列は昇順（苦手順）をデフォルト、それ以外は降順
            self._sort_rev = col not in _WR_COLS | {"deck"}
        self._rebuild_tree()

    def apply_theme(self, colors: dict) -> None:
        pass
