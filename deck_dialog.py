"""Dialog for adding / editing a deck."""

import tkinter as tk
from tkinter import messagebox
from typing import Optional
import customtkinter as ctk

_FONT      = ctk.CTkFont(family="Meiryo", size=10)
_FONT_BOLD = ctk.CTkFont(family="Meiryo", size=10, weight="bold")


class DeckDialog:
    """Modal dialog that returns a result dict on save, or None on cancel."""

    def __init__(self, parent: tk.Widget, tags: list,
                 weakness_tags: Optional[list] = None,
                 strength_tags: Optional[list] = None,
                 deck: Optional[dict] = None):
        self.result: Optional[dict] = None
        self.tags = tags
        self.weakness_tags = weakness_tags or []
        self.strength_tags = strength_tags or []

        self.top = ctk.CTkToplevel(parent)
        self.top.title("デッキを追加" if deck is None else "デッキを編集")
        self.top.resizable(False, False)
        self.top.grab_set()
        self.top.focus_set()

        self._build_ui(deck)

        self.top.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.top.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.top.winfo_height()) // 2
        self.top.geometry(f"+{max(px, 0)}+{max(py, 0)}")

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self, deck: Optional[dict]) -> None:
        px, py = 12, 6

        # Scrollable container so dialog doesn't overflow on small screens
        scroll = ctk.CTkScrollableFrame(self.top, width=480, height=500)
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        frame = ctk.CTkFrame(scroll, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=12, pady=10)

        def lbl(row, text, anchor="e"):
            ctk.CTkLabel(frame, text=text, font=_FONT_BOLD).grid(
                row=row, column=0, sticky=anchor, padx=(0, px), pady=py)

        # ── Deck name ─────────────────────────────────────────────────────────
        lbl(0, "デッキ名 *")
        self.name_var = tk.StringVar(value=deck["name"] if deck else "")
        name_entry = ctk.CTkEntry(frame, textvariable=self.name_var, width=280,
                                  font=_FONT)
        name_entry.grid(row=0, column=1, sticky="w", padx=px, pady=py)
        name_entry.focus_set()

        # ── Tags ──────────────────────────────────────────────────────────────
        lbl(1, "タグ", anchor="ne")
        tags_frame = ctk.CTkFrame(frame, fg_color="transparent")
        tags_frame.grid(row=1, column=1, sticky="w", padx=px, pady=py)
        selected_ids = {t["id"] for t in deck["tags"]} if deck else set()
        self.tag_vars: dict = {}
        if self.tags:
            cols = 3
            for i, tag in enumerate(self.tags):
                var = tk.BooleanVar(value=tag["id"] in selected_ids)
                self.tag_vars[tag["id"]] = var
                ctk.CTkCheckBox(tags_frame, text=tag["name"], variable=var,
                                font=_FONT).grid(
                    row=i // cols, column=i % cols, sticky="w", padx=6, pady=2)
        else:
            ctk.CTkLabel(tags_frame, text="タグが登録されていません",
                         text_color="gray", font=_FONT).pack()

        # ── Weakness (弱み) ───────────────────────────────────────────────────
        lbl(2, "弱み", anchor="ne")
        self._weakness_outer = ctk.CTkFrame(frame, fg_color="transparent")
        self._weakness_outer.grid(row=2, column=1, sticky="w", padx=px, pady=py)
        self._wtag_vars: dict = {}
        self._wtag_check_frame = ctk.CTkFrame(self._weakness_outer,
                                               fg_color="transparent")
        self._wtag_check_frame.pack(anchor="w")
        selected_wnames = {t["name"] for t in deck["weakness_tags"]} if deck else set()
        for wt in self.weakness_tags:
            self._add_weakness_checkbox(wt["name"], wt["name"] in selected_wnames)
        wadd = ctk.CTkFrame(self._weakness_outer, fg_color="transparent")
        wadd.pack(anchor="w", pady=(6, 0))
        ctk.CTkLabel(wadd, text="新規追加:", font=_FONT).pack(side="left",
                                                               padx=(0, 4))
        self._wtag_entry_var = tk.StringVar()
        we = ctk.CTkEntry(wadd, textvariable=self._wtag_entry_var, width=160,
                          font=_FONT)
        we.pack(side="left")
        ctk.CTkButton(wadd, text="追加", command=self._add_wtag, width=50,
                      font=_FONT).pack(side="left", padx=(4, 0))
        we.bind("<Return>", lambda _: self._add_wtag())

        # ── Strength (強み) ───────────────────────────────────────────────────
        lbl(3, "強み", anchor="ne")
        self._strength_outer = ctk.CTkFrame(frame, fg_color="transparent")
        self._strength_outer.grid(row=3, column=1, sticky="w", padx=px, pady=py)
        self._stag_vars: dict = {}
        self._stag_check_frame = ctk.CTkFrame(self._strength_outer,
                                               fg_color="transparent")
        self._stag_check_frame.pack(anchor="w")
        selected_snames = {t["name"] for t in deck["strength_tags"]} if deck else set()
        for st in self.strength_tags:
            self._add_strength_checkbox(st["name"], st["name"] in selected_snames)
        sadd = ctk.CTkFrame(self._strength_outer, fg_color="transparent")
        sadd.pack(anchor="w", pady=(6, 0))
        ctk.CTkLabel(sadd, text="新規追加:", font=_FONT).pack(side="left",
                                                               padx=(0, 4))
        self._stag_entry_var = tk.StringVar()
        se = ctk.CTkEntry(sadd, textvariable=self._stag_entry_var, width=160,
                          font=_FONT)
        se.pack(side="left")
        ctk.CTkButton(sadd, text="追加", command=self._add_stag, width=50,
                      font=_FONT).pack(side="left", padx=(4, 0))
        se.bind("<Return>", lambda _: self._add_stag())

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.grid(row=4, column=0, columnspan=2, pady=(12, 0))
        ctk.CTkButton(btn_frame, text="保存", command=self._save,
                      width=100, font=_FONT).pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="キャンセル", command=self.top.destroy,
                      width=100, font=_FONT).pack(side="left", padx=8)

        self.top.bind("<Escape>", lambda _: self.top.destroy())

    # ── Tag helpers ───────────────────────────────────────────────────────────

    def _add_weakness_checkbox(self, name: str, checked: bool = True) -> None:
        if name in self._wtag_vars:
            if checked:
                self._wtag_vars[name].set(True)
            return
        var = tk.BooleanVar(value=checked)
        self._wtag_vars[name] = var
        ctk.CTkCheckBox(self._wtag_check_frame, text=name, variable=var,
                        font=_FONT).pack(anchor="w")

    def _add_wtag(self) -> None:
        name = self._wtag_entry_var.get().strip()
        if name:
            self._add_weakness_checkbox(name, checked=True)
            self._wtag_entry_var.set("")

    def _add_strength_checkbox(self, name: str, checked: bool = True) -> None:
        if name in self._stag_vars:
            if checked:
                self._stag_vars[name].set(True)
            return
        var = tk.BooleanVar(value=checked)
        self._stag_vars[name] = var
        ctk.CTkCheckBox(self._stag_check_frame, text=name, variable=var,
                        font=_FONT).pack(anchor="w")

    def _add_stag(self) -> None:
        name = self._stag_entry_var.get().strip()
        if name:
            self._add_strength_checkbox(name, checked=True)
            self._stag_entry_var.set("")

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("入力エラー", "デッキ名を入力してください。",
                                 parent=self.top)
            return
        self.result = {
            "name": name,
            "tag_ids": [tid for tid, var in self.tag_vars.items() if var.get()],
            "weakness_tag_names": [n for n, v in self._wtag_vars.items() if v.get()],
            "strength_tag_names": [n for n, v in self._stag_vars.items() if v.get()],
        }
        self.top.destroy()
