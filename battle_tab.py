"""Battle records tab."""

import json
import os
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk

import database as db
from battle_dialog import BattleDialog
from constants import RANKS

_FONT      = ("Meiryo", 10)
_FONT_BOLD = ("Meiryo", 10, "bold")

_PREFS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "battle_prefs.json")


def _load_prefs() -> dict:
    try:
        with open(_PREFS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_prefs(prefs: dict) -> None:
    try:
        with open(_PREFS_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class BattleTab:
    def __init__(self, parent: tk.Widget):
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="both", expand=True)
        self._battles: list = []
        prefs = _load_prefs()
        self._last_rank: str      = prefs.get("last_rank", "D1")
        self._last_deck_name: str = prefs.get("last_deck_name", "")
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
        ctk.CTkButton(bottom, text="一括置換", command=self._open_replace_dialog,
                      width=76, font=_FONT).pack(side="right", padx=4)

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
            deck = next((d for d in decks if d["id"] == dlg.result["deck_id"]), None)
            if deck:
                self._last_deck_name = deck["name"]
            _save_prefs({"last_rank": self._last_rank,
                         "last_deck_name": self._last_deck_name})
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

    def _open_replace_dialog(self) -> None:
        dlg = _ReplaceDialog(self.frame)
        self.frame.wait_window(dlg.top)
        if dlg.changed:
            self.load_battles()


# ── 一括置換ダイアログ ────────────────────────────────────────────────────────

class _ReplaceDialog:
    """使用デッキ・相手デッキを戦績全体で一括置換するダイアログ。"""

    def __init__(self, parent: tk.Widget):
        self.changed = False

        self.top = ctk.CTkToplevel(parent)
        self.top.title("デッキ名一括置換")
        self.top.resizable(False, False)
        self.top.grab_set()
        self.top.focus_set()

        self._build_ui()

        self.top.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.top.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.top.winfo_height()) // 2
        self.top.geometry(f"+{max(px, 0)}+{max(py, 0)}")

    def _build_ui(self) -> None:
        outer = ctk.CTkFrame(self.top, fg_color="transparent")
        outer.pack(padx=20, pady=15, fill="both", expand=True)

        # ── 相手デッキ ─────────────────────────────────────────────────────────
        opp_section = ctk.CTkFrame(outer, border_width=1)
        opp_section.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(opp_section, text="相手デッキ", font=_FONT_BOLD).pack(
            anchor="w", padx=8, pady=(6, 4))

        opp_inner = ctk.CTkFrame(opp_section, fg_color="transparent")
        opp_inner.pack(fill="x", padx=10, pady=(0, 10))

        opp_names = db.get_distinct_opponent_decks()

        ctk.CTkLabel(opp_inner, text="置換前:", font=_FONT).grid(
            row=0, column=0, sticky="e", padx=(0, 6), pady=4)
        self._opp_old = ctk.CTkComboBox(opp_inner, values=opp_names,
                                         width=220, font=_FONT,
                                         dropdown_font=_FONT)
        self._opp_old.grid(row=0, column=1, padx=(0, 10))
        if opp_names:
            self._opp_old.set(opp_names[0])

        ctk.CTkLabel(opp_inner, text="置換後:", font=_FONT).grid(
            row=1, column=0, sticky="e", padx=(0, 6), pady=4)
        self._opp_new = ctk.CTkComboBox(opp_inner, values=opp_names,
                                         width=220, font=_FONT,
                                         dropdown_font=_FONT)
        self._opp_new.grid(row=1, column=1, padx=(0, 10))

        ctk.CTkButton(opp_inner, text="置換実行", width=80, font=_FONT,
                      command=self._replace_opp).grid(
            row=0, column=2, rowspan=2, padx=(0, 4))

        # ── 使用デッキ ─────────────────────────────────────────────────────────
        own_section = ctk.CTkFrame(outer, border_width=1)
        own_section.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(own_section, text="使用デッキ", font=_FONT_BOLD).pack(
            anchor="w", padx=8, pady=(6, 4))

        own_inner = ctk.CTkFrame(own_section, fg_color="transparent")
        own_inner.pack(fill="x", padx=10, pady=(0, 10))

        decks = db.get_all_decks()
        deck_names = [d["name"] for d in decks]
        self._decks = decks

        ctk.CTkLabel(own_inner, text="置換前:", font=_FONT).grid(
            row=0, column=0, sticky="e", padx=(0, 6), pady=4)
        self._own_old_var = tk.StringVar(value=deck_names[0] if deck_names else "")
        self._own_old_menu = ctk.CTkOptionMenu(
            own_inner, variable=self._own_old_var,
            values=deck_names or ["（デッキなし）"],
            width=220, font=_FONT, dropdown_font=_FONT)
        self._own_old_menu.grid(row=0, column=1, padx=(0, 10))

        ctk.CTkLabel(own_inner, text="置換後:", font=_FONT).grid(
            row=1, column=0, sticky="e", padx=(0, 6), pady=4)
        self._own_new_var = tk.StringVar(value=deck_names[0] if deck_names else "")
        self._own_new_menu = ctk.CTkOptionMenu(
            own_inner, variable=self._own_new_var,
            values=deck_names or ["（デッキなし）"],
            width=220, font=_FONT, dropdown_font=_FONT)
        self._own_new_menu.grid(row=1, column=1, padx=(0, 10))

        ctk.CTkButton(own_inner, text="置換実行", width=80, font=_FONT,
                      command=self._replace_own).grid(
            row=0, column=2, rowspan=2, padx=(0, 4))

        # ── 閉じる ─────────────────────────────────────────────────────────────
        ctk.CTkButton(outer, text="閉じる", command=self.top.destroy,
                      width=100, font=_FONT).pack(pady=(4, 0))

        self.top.bind("<Escape>", lambda _: self.top.destroy())

    # ── 実行 ──────────────────────────────────────────────────────────────────

    def _replace_opp(self) -> None:
        old = self._opp_old.get().strip()
        new = self._opp_new.get().strip()
        if not old:
            messagebox.showwarning("入力エラー", "置換前のデッキ名を入力してください。",
                                   parent=self.top)
            return
        if not new:
            messagebox.showwarning("入力エラー", "置換後のデッキ名を入力してください。",
                                   parent=self.top)
            return
        if old == new:
            messagebox.showinfo("変更なし", "置換前後が同じです。", parent=self.top)
            return
        n = db.replace_opponent_deck(old, new)
        if n == 0:
            messagebox.showinfo("結果", f"「{old}」に一致する相手デッキがありません。",
                                parent=self.top)
        else:
            messagebox.showinfo("完了", f"{n} 件の相手デッキを「{new}」に置換しました。",
                                parent=self.top)
            self.changed = True
            # ドロップダウンを更新
            updated = db.get_distinct_opponent_decks()
            self._opp_old.configure(values=updated)
            self._opp_new.configure(values=updated)

    def _replace_own(self) -> None:
        old_name = self._own_old_var.get()
        new_name = self._own_new_var.get()
        if old_name == new_name:
            messagebox.showinfo("変更なし", "置換前後が同じです。", parent=self.top)
            return
        old_deck = next((d for d in self._decks if d["name"] == old_name), None)
        new_deck = next((d for d in self._decks if d["name"] == new_name), None)
        if not old_deck or not new_deck:
            messagebox.showwarning("エラー", "デッキが見つかりません。", parent=self.top)
            return
        n = db.replace_battle_deck(old_deck["id"], new_deck["id"])
        if n == 0:
            messagebox.showinfo("結果",
                                f"「{old_name}」を使用した戦績がありません。",
                                parent=self.top)
        else:
            messagebox.showinfo("完了",
                                f"{n} 件の使用デッキを「{new_name}」に置換しました。",
                                parent=self.top)
            self.changed = True
