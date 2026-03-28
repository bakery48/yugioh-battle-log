"""Battle records tab."""

import tkinter as tk
from tkinter import ttk, messagebox

import database as db
from battle_dialog import BattleDialog
from constants import RANKS


class BattleTab:
    def __init__(self, parent: tk.Widget):
        self.frame = ttk.Frame(parent)
        self._battles: list = []
        self._build_ui()
        self.load_battles()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Filter bar ────────────────────────────────────────────────────────
        filter_frame = ttk.LabelFrame(self.frame, text="フィルタ", padding=6)
        filter_frame.pack(fill=tk.X, padx=6, pady=(6, 2))

        ttk.Label(filter_frame, text="期間:").grid(row=0, column=0, padx=(0, 4))
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

        ttk.Separator(filter_frame, orient=tk.VERTICAL).grid(
            row=0, column=5, sticky="ns", padx=8
        )

        ttk.Label(filter_frame, text="ランク:").grid(row=0, column=6, padx=(0, 4))
        rank_inner = ttk.Frame(filter_frame)
        rank_inner.grid(row=0, column=7)
        self.rank_vars: dict = {}
        for rank in RANKS:
            var = tk.BooleanVar()
            self.rank_vars[rank] = var
            ttk.Checkbutton(rank_inner, text=rank, variable=var).pack(
                side=tk.LEFT, padx=2
            )

        ttk.Button(
            filter_frame, text="絞り込み", command=self.load_battles, width=8
        ).grid(row=0, column=8, padx=(12, 2))
        ttk.Button(
            filter_frame, text="リセット", command=self.reset_filters, width=6
        ).grid(row=0, column=9, padx=2)

        # ── Treeview ──────────────────────────────────────────────────────────
        tree_frame = ttk.Frame(self.frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        columns = (
            "date", "rank", "first_second", "result",
            "deck", "opponent_deck", "defeat_reason",
        )
        self.tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", selectmode="browse"
        )

        col_cfg = {
            "date":           ("日付",       90,  tk.CENTER),
            "rank":           ("ランク",     55,  tk.CENTER),
            "first_second":   ("先/後攻",    65,  tk.CENTER),
            "result":         ("結果",       55,  tk.CENTER),
            "deck":           ("使用デッキ", 160, tk.W),
            "opponent_deck":  ("相手デッキ", 160, tk.W),
            "defeat_reason":  ("敗因",       220, tk.W),
        }
        for col, (heading, width, anchor) in col_cfg.items():
            self.tree.heading(col, text=heading, command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=width, anchor=anchor, stretch=(col == "defeat_reason"))

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.LEFT, fill=tk.Y)

        self.tree.tag_configure("win",  background="#e8f5e9")
        self.tree.tag_configure("loss", background="#ffebee")

        self.tree.bind("<Double-1>", lambda _: self.edit_battle())

        # ── Bottom bar ────────────────────────────────────────────────────────
        bottom = ttk.Frame(self.frame)
        bottom.pack(fill=tk.X, padx=6, pady=(0, 6))

        self.count_label = ttk.Label(bottom, text="0 件")
        self.count_label.pack(side=tk.LEFT, padx=4)

        ttk.Button(bottom, text="削除", command=self.delete_battle, width=6).pack(
            side=tk.RIGHT, padx=4
        )
        ttk.Button(bottom, text="編集", command=self.edit_battle, width=6).pack(
            side=tk.RIGHT, padx=4
        )
        ttk.Button(bottom, text="＋ 追加", command=self.add_battle, width=8).pack(
            side=tk.RIGHT, padx=4
        )

        self._sort_col: str = "date"
        self._sort_rev: bool = True

    # ── Data loading ──────────────────────────────────────────────────────────

    def _get_filters(self) -> dict:
        filters: dict = {}
        if self.date_from_var.get().strip():
            filters["date_from"] = self.date_from_var.get().strip()
        if self.date_to_var.get().strip():
            filters["date_to"] = self.date_to_var.get().strip()
        selected = [r for r, v in self.rank_vars.items() if v.get()]
        if selected:
            filters["ranks"] = selected
        return filters

    def load_battles(self) -> None:
        filters = self._get_filters()
        self._battles = db.get_battles(filters or None)

        for iid in self.tree.get_children():
            self.tree.delete(iid)

        for b in self._battles:
            tag = "win" if b["result"] == "勝利" else "loss"
            self.tree.insert(
                "",
                tk.END,
                iid=str(b["id"]),
                values=(
                    b["date"],
                    b["rank"],
                    b["first_second"],
                    b["result"],
                    b["deck_name"] or "（削除済み）",
                    b["opponent_deck"],
                    b["defeat_reason"] or "",
                ),
                tags=(tag,),
            )

        total = len(self._battles)
        wins = sum(1 for b in self._battles if b["result"] == "勝利")
        self.count_label.configure(
            text=f"{total} 件  （{wins}勝 {total - wins}敗）"
        )

    def reset_filters(self) -> None:
        self.date_from_var.set("")
        self.date_to_var.set("")
        for v in self.rank_vars.values():
            v.set(False)
        self.load_battles()

    def _sort_by(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col = col
            self._sort_rev = False

        items = [(self.tree.set(iid, col), iid) for iid in self.tree.get_children()]
        items.sort(reverse=self._sort_rev)
        for idx, (_, iid) in enumerate(items):
            self.tree.move(iid, "", idx)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def _selected_battle(self):
        sel = self.tree.selection()
        if not sel:
            return None
        bid = int(sel[0])
        return next((b for b in self._battles if b["id"] == bid), None)

    def add_battle(self) -> None:
        decks = db.get_all_decks()
        if not decks:
            messagebox.showwarning(
                "デッキ未登録",
                "先に「デッキ管理」タブでデッキを登録してください。",
                parent=self.frame,
            )
            return
        dlg = BattleDialog(self.frame, decks=decks)
        self.frame.wait_window(dlg.top)
        if dlg.result:
            db.add_battle(**dlg.result)
            self.load_battles()

    def edit_battle(self) -> None:
        battle = self._selected_battle()
        if not battle:
            messagebox.showinfo("選択なし", "編集する戦績を選択してください。", parent=self.frame)
            return
        decks = db.get_all_decks()
        dlg = BattleDialog(self.frame, decks=decks, battle=battle)
        self.frame.wait_window(dlg.top)
        if dlg.result:
            db.update_battle(battle["id"], **dlg.result)
            self.load_battles()

    def delete_battle(self) -> None:
        battle = self._selected_battle()
        if not battle:
            messagebox.showinfo("選択なし", "削除する戦績を選択してください。", parent=self.frame)
            return
        if messagebox.askyesno(
            "削除確認",
            f"{battle['date']} の戦績を削除しますか？",
            parent=self.frame,
        ):
            db.delete_battle(battle["id"])
            self.load_battles()
