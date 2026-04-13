"""Dialog for adding / editing a battle record."""

import re
import tkinter as tk
from tkinter import messagebox
from datetime import date as dt_date
from typing import Optional
import customtkinter as ctk

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
        self.top.title("戦績を追加" if battle is None else "戦績を編集")
        self.top.resizable(False, False)
        self.top.grab_set()
        self.top.focus_set()

        self._build_ui(battle)

        self.top.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.top.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.top.winfo_height()) // 2
        self.top.geometry(f"+{max(px, 0)}+{max(py, 0)}")

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self, battle: Optional[dict]) -> None:
        frame = ctk.CTkFrame(self.top, fg_color="transparent")
        frame.pack(padx=20, pady=15)

        px, py = 12, 6

        def lbl(row, text):
            ctk.CTkLabel(frame, text=text, font=_FONT_BOLD).grid(
                row=row, column=0, sticky="e", padx=(0, px), pady=py)

        # ── Date ──────────────────────────────────────────────────────────────
        lbl(0, "日付 *")
        self.date_var = tk.StringVar(
            value=battle["date"] if battle else dt_date.today().isoformat())
        ctk.CTkEntry(frame, textvariable=self.date_var, width=120,
                     font=_FONT).grid(row=0, column=1, sticky="w", padx=px, pady=py)
        ctk.CTkLabel(frame, text="YYYY-MM-DD", text_color="gray",
                     font=_FONT_SM).grid(row=0, column=2, sticky="w")

        # ── Rank ──────────────────────────────────────────────────────────────
        lbl(1, "ランク *")
        self.rank_var = tk.StringVar(value=battle["rank"] if battle else self._last_rank)
        ctk.CTkOptionMenu(frame, variable=self.rank_var, values=RANKS,
                          width=90, font=_FONT,
                          dropdown_font=_FONT).grid(
            row=1, column=1, sticky="w", padx=px, pady=py)

        # ── First / Second ────────────────────────────────────────────────────
        lbl(2, "先攻/後攻 *")
        self.fs_var = tk.StringVar(
            value=battle["first_second"] if battle else "先攻")
        fs_frame = ctk.CTkFrame(frame, fg_color="transparent")
        fs_frame.grid(row=2, column=1, columnspan=2, sticky="w", padx=px, pady=py)
        for opt in FIRST_SECOND_OPTIONS:
            ctk.CTkRadioButton(fs_frame, text=opt, variable=self.fs_var,
                               value=opt, font=_FONT).pack(side="left", padx=8)

        # ── Result ────────────────────────────────────────────────────────────
        lbl(3, "結果 *")
        self.result_var = tk.StringVar(
            value=battle["result"] if battle else "勝利")
        result_frame = ctk.CTkFrame(frame, fg_color="transparent")
        result_frame.grid(row=3, column=1, columnspan=2, sticky="w",
                          padx=px, pady=py)
        for opt in RESULT_OPTIONS:
            ctk.CTkRadioButton(
                result_frame, text=opt, variable=self.result_var,
                value=opt, font=_FONT,
                command=self._on_result_changed,
            ).pack(side="left", padx=8)

        # ── Defeat reason ─────────────────────────────────────────────────────
        lbl(4, "敗因")
        self.defeat_reason_var = tk.StringVar(
            value=battle["defeat_reason"] if battle else "")
        self.defeat_reason_entry = ctk.CTkEntry(
            frame, textvariable=self.defeat_reason_var, width=300, font=_FONT,
            placeholder_text="敗北時のみ入力")
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
        ctk.CTkOptionMenu(frame, variable=self.deck_var, values=deck_names,
                          width=260, font=_FONT,
                          dropdown_font=_FONT).grid(
            row=5, column=1, columnspan=2, sticky="w", padx=px, pady=py)

        # ── Opponent deck ─────────────────────────────────────────────────────
        lbl(6, "相手デッキ *")
        self.opponent_deck_var = tk.StringVar(
            value=battle["opponent_deck"] if battle else "")
        self._opp_combo = ctk.CTkComboBox(
            frame, variable=self.opponent_deck_var,
            values=deck_names, width=280, font=_FONT,
            dropdown_font=_FONT)
        self._opp_combo.grid(row=6, column=1, columnspan=2, sticky="w",
                             padx=px, pady=py)
        if battle and battle.get("opponent_deck"):
            self._opp_combo.set(battle["opponent_deck"])

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.grid(row=7, column=0, columnspan=3, pady=(12, 0))
        ctk.CTkButton(btn_frame, text="保存", command=self._save,
                      width=100, font=_FONT).pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="キャンセル", command=self.top.destroy,
                      width=100, font=_FONT).pack(side="left", padx=8)

        self._on_result_changed()
        self.top.bind("<Return>", lambda _: self._save())
        self.top.bind("<Escape>", lambda _: self.top.destroy())

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_result_changed(self) -> None:
        # CTkEntry の disabled/normal 切り替えはフォーカスを失うことがある。
        # 代わりに常に enabled のまま、勝利選択時はテキストをクリアするだけにする。
        if self.result_var.get() == "勝利":
            self.defeat_reason_var.set("")

    def _save(self) -> None:
        date         = self.date_var.get().strip()
        rank         = self.rank_var.get().strip()
        first_second = self.fs_var.get()
        result       = self.result_var.get()
        defeat_reason = self.defeat_reason_var.get().strip()
        deck_name    = self.deck_var.get().strip()
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
        self.top.destroy()
