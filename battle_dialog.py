"""Dialog for adding / editing a battle record."""

import re
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date as dt_date
from typing import Optional

from constants import RANKS, FIRST_SECOND_OPTIONS, RESULT_OPTIONS

_FONT      = ("Meiryo", 10)
_FONT_BOLD = ("Meiryo", 10, "bold")
_FONT_SM   = ("Meiryo", 9)


class BattleDialog:
    """Modal dialog that returns a result dict on save, or None on cancel."""

    def __init__(self, parent: tk.Widget, decks: list,
                 battle: Optional[dict] = None,
                 last_rank: str = "D1",
                 last_deck_name: str = ""):
        self.result: Optional[dict] = None
        self.decks = decks
        self._last_rank = last_rank
        self._last_deck_name = last_deck_name

        self.top = tk.Toplevel(parent)
        self.top.withdraw()
        self.top.title("戦績を追加" if battle is None else "戦績を編集")
        self.top.resizable(False, False)
        self.top.grab_set()
        self.top.focus_set()

        self._build_ui(battle)

        self.top.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.top.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.top.winfo_height()) // 2
        self.top.geometry(f"+{max(px, 0)}+{max(py, 0)}")
        self.top.deiconify()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self, battle: Optional[dict]) -> None:
        frame = ttk.Frame(self.top, padding=(20, 15))
        frame.pack(fill="both", expand=True)

        px, py = 12, 6

        def lbl(row, text):
            ttk.Label(frame, text=text, font=_FONT_BOLD).grid(
                row=row, column=0, sticky="e", padx=(0, px), pady=py)

        # ── Date ──────────────────────────────────────────────────────────────
        lbl(0, "日付 *")
        self.date_var = tk.StringVar(
            value=battle["date"] if battle else dt_date.today().isoformat())
        ttk.Entry(frame, textvariable=self.date_var, width=14,
                  font=_FONT).grid(row=0, column=1, sticky="w", padx=px, pady=py)
        ttk.Label(frame, text="YYYY-MM-DD", foreground="gray",
                  font=_FONT_SM).grid(row=0, column=2, sticky="w")

        # ── Rank ──────────────────────────────────────────────────────────────
        lbl(1, "ランク *")
        self.rank_var = tk.StringVar(
            value=battle["rank"] if battle else self._last_rank)
        ttk.Combobox(frame, textvariable=self.rank_var, values=RANKS,
                     width=8, font=_FONT, state="readonly").grid(
            row=1, column=1, sticky="w", padx=px, pady=py)

        # ── First / Second ────────────────────────────────────────────────────
        lbl(2, "先攻/後攻 *")
        self.fs_var = tk.StringVar(
            value=battle["first_second"] if battle else "先攻")
        fs_frame = ttk.Frame(frame)
        fs_frame.grid(row=2, column=1, columnspan=2, sticky="w", padx=px, pady=py)
        for opt in FIRST_SECOND_OPTIONS:
            ttk.Radiobutton(fs_frame, text=opt, variable=self.fs_var,
                            value=opt).pack(side="left", padx=8)

        # ── Result ────────────────────────────────────────────────────────────
        lbl(3, "結果 *")
        self.result_var = tk.StringVar(
            value=battle["result"] if battle else "勝利")
        result_frame = ttk.Frame(frame)
        result_frame.grid(row=3, column=1, columnspan=2, sticky="w",
                          padx=px, pady=py)
        for opt in RESULT_OPTIONS:
            ttk.Radiobutton(
                result_frame, text=opt, variable=self.result_var,
                value=opt, command=self._on_result_changed,
            ).pack(side="left", padx=8)

        # ── Defeat reason ─────────────────────────────────────────────────────
        lbl(4, "敗因")
        self.defeat_reason_var = tk.StringVar(
            value=battle["defeat_reason"] if battle else "")
        self.defeat_reason_entry = ttk.Entry(
            frame, textvariable=self.defeat_reason_var, width=35, font=_FONT)
        self.defeat_reason_entry.grid(row=4, column=1, columnspan=2,
                                      sticky="w", padx=px, pady=py)

        # ── Deck ──────────────────────────────────────────────────────────────
        lbl(5, "使用デッキ *")
        deck_names = [d["name"] for d in self.decks]
        if battle and battle.get("deck_name"):
            init_deck = battle["deck_name"]
        elif self._last_deck_name and self._last_deck_name in deck_names:
            init_deck = self._last_deck_name
        else:
            init_deck = deck_names[0] if deck_names else ""
        self.deck_var = tk.StringVar(value=init_deck)
        ttk.Combobox(frame, textvariable=self.deck_var, values=deck_names,
                     width=30, font=_FONT, state="readonly").grid(
            row=5, column=1, columnspan=2, sticky="w", padx=px, pady=py)

        # ── Opponent deck ─────────────────────────────────────────────────────
        lbl(6, "相手デッキ *")
        self.opponent_deck_var = tk.StringVar(
            value=battle["opponent_deck"] if battle else "")
        self._opp_combo = ttk.Combobox(
            frame, textvariable=self.opponent_deck_var,
            values=deck_names, width=32, font=_FONT)
        self._opp_combo.grid(row=6, column=1, columnspan=2, sticky="w",
                             padx=px, pady=py)
        if battle and battle.get("opponent_deck"):
            self._opp_combo.set(battle["opponent_deck"])

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=7, column=0, columnspan=3, pady=(12, 0))
        ttk.Button(btn_frame, text="保存", command=self._save,
                   width=10).pack(side="left", padx=8)
        ttk.Button(btn_frame, text="キャンセル", command=self.top.destroy,
                   width=10).pack(side="left", padx=8)

        self._on_result_changed()
        self.top.bind("<Return>", lambda _: self._save())
        self.top.bind("<Escape>", lambda _: self.top.destroy())

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_result_changed(self) -> None:
        if self.result_var.get() == "勝利":
            self.defeat_reason_var.set("")

    def _save(self) -> None:
        date          = self.date_var.get().strip()
        rank          = self.rank_var.get().strip()
        first_second  = self.fs_var.get()
        result        = self.result_var.get()
        defeat_reason = self.defeat_reason_var.get().strip()
        deck_name     = self.deck_var.get().strip()
        opponent_deck = self._opp_combo.get().strip()

        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            messagebox.showerror(
                "入力エラー", "日付は YYYY-MM-DD 形式で入力してください。",
                parent=self.top)
            return
        if not deck_name:
            messagebox.showerror("入力エラー", "使用デッキを選択してください。",
                                 parent=self.top)
            return
        if not opponent_deck:
            messagebox.showerror("入力エラー", "相手デッキを入力してください。",
                                 parent=self.top)
            return

        deck_id = next((d["id"] for d in self.decks if d["name"] == deck_name), None)
        self.result = {
            "date": date,
            "rank": rank,
            "first_second": first_second,
            "result": result,
            "defeat_reason": defeat_reason if result == "敗北" else "",
            "deck_id": deck_id,
            "opponent_deck": opponent_deck,
        }
        self.top.withdraw()
        self.top.destroy()
