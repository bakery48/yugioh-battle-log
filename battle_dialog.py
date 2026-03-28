"""Dialog for adding / editing a battle record."""

import re
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date as dt_date
from typing import Optional

from constants import RANKS, FIRST_SECOND_OPTIONS, RESULT_OPTIONS
from ime_utils import suppress_ime_popup


class BattleDialog:
    """Modal dialog that returns a result dict on save, or None on cancel."""

    def __init__(self, parent: tk.Widget, decks: list, battle: Optional[dict] = None):
        self.result: Optional[dict] = None
        self.decks = decks

        self.top = tk.Toplevel(parent)
        self.top.title("戦績を追加" if battle is None else "戦績を編集")
        self.top.resizable(False, False)
        self.top.grab_set()
        self.top.focus_set()

        self._build_ui(battle)

        # Center dialog over parent
        self.top.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.top.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.top.winfo_height()) // 2
        self.top.geometry(f"+{max(px, 0)}+{max(py, 0)}")

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self, battle: Optional[dict]) -> None:
        pad = {"padx": 12, "pady": 6}

        frame = ttk.Frame(self.top, padding=15)
        frame.pack()

        # ── Date ──────────────────────────────────────────────────────────────
        ttk.Label(frame, text="日付 *").grid(row=0, column=0, sticky=tk.E, **pad)
        self.date_var = tk.StringVar(
            value=battle["date"] if battle else dt_date.today().isoformat()
        )
        _date_entry = ttk.Entry(frame, textvariable=self.date_var, width=14)
        _date_entry.grid(row=0, column=1, sticky=tk.W, **pad)
        suppress_ime_popup(_date_entry)
        ttk.Label(frame, text="YYYY-MM-DD", foreground="gray").grid(
            row=0, column=2, sticky=tk.W
        )

        # ── Rank ──────────────────────────────────────────────────────────────
        ttk.Label(frame, text="ランク *").grid(row=1, column=0, sticky=tk.E, **pad)
        self.rank_var = tk.StringVar(value=battle["rank"] if battle else "D1")
        ttk.Combobox(
            frame, textvariable=self.rank_var, values=RANKS, state="readonly", width=8
        ).grid(row=1, column=1, sticky=tk.W, **pad)

        # ── First / Second ────────────────────────────────────────────────────
        ttk.Label(frame, text="先攻/後攻 *").grid(row=2, column=0, sticky=tk.E, **pad)
        self.fs_var = tk.StringVar(
            value=battle["first_second"] if battle else "先攻"
        )
        fs_frame = ttk.Frame(frame)
        fs_frame.grid(row=2, column=1, columnspan=2, sticky=tk.W, **pad)
        for opt in FIRST_SECOND_OPTIONS:
            ttk.Radiobutton(fs_frame, text=opt, variable=self.fs_var, value=opt).pack(
                side=tk.LEFT, padx=8
            )

        # ── Result ────────────────────────────────────────────────────────────
        ttk.Label(frame, text="結果 *").grid(row=3, column=0, sticky=tk.E, **pad)
        self.result_var = tk.StringVar(
            value=battle["result"] if battle else "勝利"
        )
        result_frame = ttk.Frame(frame)
        result_frame.grid(row=3, column=1, columnspan=2, sticky=tk.W, **pad)
        for opt in RESULT_OPTIONS:
            ttk.Radiobutton(
                result_frame,
                text=opt,
                variable=self.result_var,
                value=opt,
                command=self._on_result_changed,
            ).pack(side=tk.LEFT, padx=8)

        # ── Defeat reason ─────────────────────────────────────────────────────
        ttk.Label(frame, text="敗因").grid(row=4, column=0, sticky=tk.E, **pad)
        self.defeat_reason_var = tk.StringVar(
            value=battle["defeat_reason"] if battle else ""
        )
        self.defeat_reason_entry = ttk.Entry(
            frame, textvariable=self.defeat_reason_var, width=35
        )
        self.defeat_reason_entry.grid(row=4, column=1, columnspan=2, sticky=tk.W, **pad)
        suppress_ime_popup(self.defeat_reason_entry)

        # ── Deck ──────────────────────────────────────────────────────────────
        ttk.Label(frame, text="使用デッキ *").grid(row=5, column=0, sticky=tk.E, **pad)
        deck_names = [d["name"] for d in self.decks]
        self.deck_var = tk.StringVar()
        if battle and battle.get("deck_name"):
            self.deck_var.set(battle["deck_name"])
        elif deck_names:
            self.deck_var.set(deck_names[0])
        ttk.Combobox(
            frame, textvariable=self.deck_var, values=deck_names, state="readonly", width=30
        ).grid(row=5, column=1, columnspan=2, sticky=tk.W, **pad)

        # ── Opponent deck ─────────────────────────────────────────────────────
        ttk.Label(frame, text="相手デッキ *").grid(row=6, column=0, sticky=tk.E, **pad)
        self.opponent_deck_var = tk.StringVar(
            value=battle["opponent_deck"] if battle else ""
        )
        _opp_entry = ttk.Entry(frame, textvariable=self.opponent_deck_var, width=35)
        _opp_entry.grid(row=6, column=1, columnspan=2, sticky=tk.W, **pad)
        suppress_ime_popup(_opp_entry)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=7, column=0, columnspan=3, pady=(12, 0))
        ttk.Button(btn_frame, text="保存", command=self._save, width=10).pack(
            side=tk.LEFT, padx=8
        )
        ttk.Button(
            btn_frame, text="キャンセル", command=self.top.destroy, width=10
        ).pack(side=tk.LEFT, padx=8)

        self._on_result_changed()

        # Bind Enter key
        self.top.bind("<Return>", lambda _: self._save())
        self.top.bind("<Escape>", lambda _: self.top.destroy())

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_result_changed(self) -> None:
        if self.result_var.get() == "勝利":
            self.defeat_reason_entry.configure(state="disabled")
            self.defeat_reason_var.set("")
        else:
            self.defeat_reason_entry.configure(state="normal")

    def _save(self) -> None:
        date = self.date_var.get().strip()
        rank = self.rank_var.get().strip()
        first_second = self.fs_var.get()
        result = self.result_var.get()
        defeat_reason = self.defeat_reason_var.get().strip()
        deck_name = self.deck_var.get().strip()
        opponent_deck = self.opponent_deck_var.get().strip()

        # ── Validation ────────────────────────────────────────────────────────
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            messagebox.showerror(
                "入力エラー", "日付は YYYY-MM-DD 形式で入力してください。", parent=self.top
            )
            return
        if not deck_name:
            messagebox.showerror("入力エラー", "使用デッキを選択してください。", parent=self.top)
            return
        if not opponent_deck:
            messagebox.showerror("入力エラー", "相手デッキを入力してください。", parent=self.top)
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
