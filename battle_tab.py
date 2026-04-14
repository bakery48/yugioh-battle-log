"""Battle records tab."""

import json
import os
import tkinter as tk
from tkinter import ttk, messagebox

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
        self.frame = ttk.Frame(parent)
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
        filter_outer = ttk.LabelFrame(self.frame, text="フィルタ", padding=6)
        filter_outer.pack(fill="x", padx=6, pady=(6, 2))

        filter_frame = ttk.Frame(filter_outer)
        filter_frame.pack(fill="x", padx=8, pady=(0, 6))

        ttk.Label(filter_frame, text="期間:").grid(
            row=0, column=0, padx=(0, 4), pady=4)
        self.date_from_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.date_from_var, width=12).grid(
            row=0, column=1, padx=2)
        ttk.Label(filter_frame, text="～").grid(row=0, column=2)
        self.date_to_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.date_to_var, width=12).grid(
            row=0, column=3, padx=2)
        ttk.Label(filter_frame, text="YYYY-MM-DD",
                  foreground="gray").grid(row=0, column=4, padx=6)

        ttk.Separator(filter_frame, orient="vertical").grid(
            row=0, column=5, sticky="ns", padx=8)

        ttk.Label(filter_frame, text="ランク:").grid(
            row=0, column=6, padx=(0, 4))
        rank_inner = ttk.Frame(filter_frame)
        rank_inner.grid(row=0, column=7)
        self.rank_vars: dict = {}
        for rank in RANKS:
            var = tk.BooleanVar()
            self.rank_vars[rank] = var
            ttk.Checkbutton(rank_inner, text=rank, variable=var).pack(
                side="left", padx=2)

        ttk.Button(filter_frame, text="絞り込み",
                   command=self.load_battles).grid(row=0, column=8, padx=(12, 2))
        ttk.Button(filter_frame, text="リセット",
                   command=self.reset_filters).grid(row=0, column=9, padx=2)

        # ── Treeview ──────────────────────────────────────────────────────────
        tree_frame = ttk.Frame(self.frame)
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
        bottom = ttk.Frame(self.frame)
        bottom.pack(fill="x", padx=6, pady=(0, 6))

        self.count_label = ttk.Label(bottom, text="0 件")
        self.count_label.pack(side="left", padx=4)

        ttk.Button(bottom, text="削除",
                   command=self.delete_battle).pack(side="right", padx=4)
        ttk.Button(bottom, text="編集",
                   command=self.edit_battle).pack(side="right", padx=4)
        ttk.Button(bottom, text="＋ 追加",
                   command=self.add_battle).pack(side="right", padx=4)
        ttk.Button(bottom, text="一括置換",
                   command=self._open_replace_dialog).pack(side="right", padx=4)

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

        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)

        for b in self._battles:
            self.tree.insert(
                "", "end", iid=str(b["id"]),
                values=(
                    b["date"], b["rank"], b["first_second"], b["result"],
                    b["deck_name"] or "（削除済み）",
                    b["opponent_deck"], b["defeat_reason"] or "",
                ),
                tags=("win" if b["result"] == "勝利" else "loss",),
            )

        self._update_count_label()

    def _update_count_label(self) -> None:
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
            new_id = db.add_battle(**dlg.result)
            r = dlg.result
            self._last_rank = r["rank"]
            deck = next((d for d in decks if d["id"] == r["deck_id"]), None)
            if deck:
                self._last_deck_name = deck["name"]
            _save_prefs({"last_rank": self._last_rank,
                         "last_deck_name": self._last_deck_name})

            # フィルタ適用中は確実に表示が一致するよう再読み込み
            if self._get_filters():
                self.load_battles()
                return

            # フィルタなし → ツリー先頭に1行だけ挿入（高速）
            deck_name = deck["name"] if deck else "（削除済み）"
            b = {**r, "id": new_id, "deck_name": deck_name}
            self._battles.insert(0, b)
            self.tree.insert(
                "", 0, iid=str(new_id),
                values=(b["date"], b["rank"], b["first_second"], b["result"],
                        deck_name, b["opponent_deck"], b["defeat_reason"] or ""),
                tags=("win" if b["result"] == "勝利" else "loss",),
            )
            self._update_count_label()

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
            r = dlg.result
            deck = next((d for d in decks if d["id"] == r["deck_id"]), None)
            deck_name = deck["name"] if deck else "（削除済み）"
            # self._battles をインプレース更新
            for i, b in enumerate(self._battles):
                if b["id"] == battle["id"]:
                    self._battles[i] = {**r, "id": battle["id"],
                                        "deck_name": deck_name}
                    break
            # ツリー行をインプレース更新（全件再読み込み不要）
            iid = str(battle["id"])
            self.tree.item(iid, values=(
                r["date"], r["rank"], r["first_second"], r["result"],
                deck_name, r["opponent_deck"], r["defeat_reason"] or ""))
            self.tree.item(iid, tags=(
                "win" if r["result"] == "勝利" else "loss",))
            self._update_count_label()

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
            self._battles = [b for b in self._battles if b["id"] != battle["id"]]
            self.tree.delete(str(battle["id"]))
            self._update_count_label()

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

        self.top = tk.Toplevel(parent)
        self.top.withdraw()
        self.top.title("デッキ名一括置換")
        self.top.resizable(False, False)
        self.top.grab_set()
        self.top.focus_set()

        self._build_ui()

        self.top.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.top.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.top.winfo_height()) // 2
        self.top.geometry(f"+{max(px, 0)}+{max(py, 0)}")
        self.top.deiconify()

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.top, padding=(20, 15))
        outer.pack(fill="both", expand=True)

        # ── 相手デッキ ─────────────────────────────────────────────────────────
        opp_section = ttk.LabelFrame(outer, text="相手デッキ", padding=(8, 6))
        opp_section.pack(fill="x", pady=(0, 10))

        opp_names = db.get_distinct_opponent_decks()

        ttk.Label(opp_section, text="置換前:").grid(
            row=0, column=0, sticky="e", padx=(0, 6), pady=4)
        self._opp_old = ttk.Combobox(opp_section, values=opp_names,
                                     width=26, font=_FONT)
        self._opp_old.grid(row=0, column=1, padx=(0, 10))
        if opp_names:
            self._opp_old.set(opp_names[0])

        ttk.Label(opp_section, text="置換後:").grid(
            row=1, column=0, sticky="e", padx=(0, 6), pady=4)
        self._opp_new = ttk.Combobox(opp_section, values=opp_names,
                                     width=26, font=_FONT)
        self._opp_new.grid(row=1, column=1, padx=(0, 10))

        ttk.Button(opp_section, text="置換実行",
                   command=self._replace_opp).grid(
            row=0, column=2, rowspan=2, padx=(0, 4))

        # ── 使用デッキ ─────────────────────────────────────────────────────────
        own_section = ttk.LabelFrame(outer, text="使用デッキ", padding=(8, 6))
        own_section.pack(fill="x", pady=(0, 10))

        decks = db.get_all_decks()
        deck_names = [d["name"] for d in decks]
        self._decks = decks

        ttk.Label(own_section, text="置換前:").grid(
            row=0, column=0, sticky="e", padx=(0, 6), pady=4)
        self._own_old_var = tk.StringVar(value=deck_names[0] if deck_names else "")
        ttk.Combobox(own_section, textvariable=self._own_old_var,
                     values=deck_names or ["（デッキなし）"],
                     width=26, font=_FONT, state="readonly").grid(
            row=0, column=1, padx=(0, 10))

        ttk.Label(own_section, text="置換後:").grid(
            row=1, column=0, sticky="e", padx=(0, 6), pady=4)
        self._own_new_var = tk.StringVar(value=deck_names[0] if deck_names else "")
        ttk.Combobox(own_section, textvariable=self._own_new_var,
                     values=deck_names or ["（デッキなし）"],
                     width=26, font=_FONT, state="readonly").grid(
            row=1, column=1, padx=(0, 10))

        ttk.Button(own_section, text="置換実行",
                   command=self._replace_own).grid(
            row=0, column=2, rowspan=2, padx=(0, 4))

        # ── 閉じる ─────────────────────────────────────────────────────────────
        ttk.Button(outer, text="閉じる", command=self.top.destroy,
                   width=12).pack(pady=(4, 0))

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
            self._opp_old["values"] = updated
            self._opp_new["values"] = updated

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
