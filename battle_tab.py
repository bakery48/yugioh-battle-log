"""Battle records tab."""

import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk

import database as db
from battle_dialog import BattleDialog
from constants import RANKS

_FONT      = ("Meiryo", 10)
_FONT_BOLD = ("Meiryo", 10, "bold")


class BattleTab:
    def __init__(self, parent: tk.Widget):
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="both", expand=True)
        self._battles: list = []
        self._last_rank: str = "D1"
        self._last_deck_name: str = ""
        self._build_ui()
        self.load_battles()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Filter bar ────────────────────────────────────────────────────────
        filter_outer = ctk.CTkFrame(self.frame, border_width=1)
        filter_outer.pack(fill="x", padx=6, pady=(6, 2))
        ctk.CTkLabel(filter_outer, text="フィルタ", font=_FONT_BOLD).pack(
            anchor="w", padx=8, pady=(4, 2))

        filter_frame = ctk.CTkFrame(filter_outer, fg_color="transparent")
        filter_frame.pack(fill="x", padx=8, pady=(0, 6))

        ctk.CTkLabel(filter_frame, text="期間:", font=_FONT).grid(
            row=0, column=0, padx=(0, 4), pady=4)
        self.date_from_var = tk.StringVar()
        ctk.CTkEntry(filter_frame, textvariable=self.date_from_var, width=110,
                     font=_FONT).grid(row=0, column=1, padx=2)
        ctk.CTkLabel(filter_frame, text="～", font=_FONT).grid(row=0, column=2)
        self.date_to_var = tk.StringVar()
        ctk.CTkEntry(filter_frame, textvariable=self.date_to_var, width=110,
                     font=_FONT).grid(row=0, column=3, padx=2)
        ctk.CTkLabel(filter_frame, text="YYYY-MM-DD",
                     text_color="gray", font=_FONT).grid(row=0, column=4, padx=6)

        ctk.CTkFrame(filter_frame, width=1, fg_color="gray").grid(
            row=0, column=5, sticky="ns", padx=8)

        ctk.CTkLabel(filter_frame, text="ランク:", font=_FONT).grid(
            row=0, column=6, padx=(0, 4))
        rank_inner = ctk.CTkFrame(filter_frame, fg_color="transparent")
        rank_inner.grid(row=0, column=7)
        self.rank_vars: dict = {}
        for rank in RANKS:
            var = tk.BooleanVar()
            self.rank_vars[rank] = var
            ctk.CTkCheckBox(rank_inner, text=rank, variable=var,
                            font=_FONT, width=56).pack(side="left", padx=2)

        ctk.CTkButton(filter_frame, text="絞り込み", command=self.load_battles,
                      width=80, font=_FONT).grid(row=0, column=8, padx=(12, 2))
        ctk.CTkButton(filter_frame, text="リセット", command=self.reset_filters,
                      width=64, font=_FONT).grid(row=0, column=9, padx=2)

        # ── Treeview ──────────────────────────────────────────────────────────
        tree_frame = ctk.CTkFrame(self.frame, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True, padx=6, pady=4)

        columns = (
            "date", "rank", "first_second", "result",
            "deck", "opponent_deck", "defeat_reason",
        )
        self.tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", selectmode="browse"
        )

        col_cfg = {
            "date":          ("日付",       90,  "center"),
            "rank":          ("ランク",     55,  "center"),
            "first_second":  ("先/後攻",    65,  "center"),
            "result":        ("結果",       55,  "center"),
            "deck":          ("使用デッキ", 160, "w"),
            "opponent_deck": ("相手デッキ", 160, "w"),
            "defeat_reason": ("敗因",       220, "w"),
        }
        for col, (heading, width, anchor) in col_cfg.items():
            self.tree.heading(col, text=heading,
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=width, anchor=anchor,
                             stretch=(col == "defeat_reason"))

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")

        self.tree.tag_configure("win",  background="#e8f5e9")
        self.tree.tag_configure("loss", background="#ffebee")
        self.tree.bind("<Double-1>", lambda _: self.edit_battle())

        # ── Bottom bar ────────────────────────────────────────────────────────
        bottom = ctk.CTkFrame(self.frame, fg_color="transparent")
        bottom.pack(fill="x", padx=6, pady=(0, 6))

        self.count_label = ctk.CTkLabel(bottom, text="0 件", font=_FONT)
        self.count_label.pack(side="left", padx=4)

        ctk.CTkButton(bottom, text="削除", command=self.delete_battle,
                      width=60, font=_FONT).pack(side="right", padx=4)
        ctk.CTkButton(bottom, text="編集", command=self.edit_battle,
                      width=60, font=_FONT).pack(side="right", padx=4)
        ctk.CTkButton(bottom, text="＋ 追加", command=self.add_battle,
                      width=80, font=_FONT).pack(side="right", padx=4)

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
                "", "end", iid=str(b["id"]),
                values=(
                    b["date"], b["rank"], b["first_second"], b["result"],
                    b["deck_name"] or "（削除済み）",
                    b["opponent_deck"], b["defeat_reason"] or "",
                ),
                tags=(tag,),
            )

        total = len(self._battles)
        wins = sum(1 for b in self._battles if b["result"] == "勝利")
        self.count_label.configure(text=f"{total} 件  （{wins}勝 {total - wins}敗）")

    def apply_theme(self, colors: dict) -> None:
        self.tree.tag_configure("win",  background=colors["tree_win"])
        self.tree.tag_configure("loss", background=colors["tree_loss"])

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
        dlg = BattleDialog(self.frame, decks=decks,
                           last_rank=self._last_rank,
                           last_deck_name=self._last_deck_name)
        self.frame.wait_window(dlg.top)
        if dlg.result:
            db.add_battle(**dlg.result)
            self._last_rank = dlg.result["rank"]
            # deck_id → name for next default
            deck = next((d for d in decks if d["id"] == dlg.result["deck_id"]), None)
            if deck:
                self._last_deck_name = deck["name"]
            self.load_battles()

    def edit_battle(self) -> None:
        battle = self._selected_battle()
        if not battle:
            messagebox.showinfo("選択なし", "編集する戦績を選択してください。",
                                parent=self.frame)
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
            messagebox.showinfo("選択なし", "削除する戦績を選択してください。",
                                parent=self.frame)
            return
        if messagebox.askyesno(
            "削除確認",
            f"{battle['date']} の戦績を削除しますか？",
            parent=self.frame,
        ):
            db.delete_battle(battle["id"])
            self.load_battles()
