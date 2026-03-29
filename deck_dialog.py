"""Dialog for adding / editing a deck."""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional


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

        self.top = tk.Toplevel(parent)
        self.top.title("デッキを追加" if deck is None else "デッキを編集")
        self.top.resizable(False, False)
        self.top.grab_set()
        self.top.focus_set()

        self._build_ui(deck)

        self.top.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width() - self.top.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.top.winfo_height()) // 2
        self.top.geometry(f"+{max(px, 0)}+{max(py, 0)}")

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self, deck: Optional[dict]) -> None:
        pad = {"padx": 12, "pady": 6}

        frame = ttk.Frame(self.top, padding=15)
        frame.pack()

        # ── Deck name ─────────────────────────────────────────────────────────
        ttk.Label(frame, text="デッキ名 *").grid(row=0, column=0, sticky=tk.E, **pad)
        self.name_var = tk.StringVar(value=deck["name"] if deck else "")
        name_entry = ttk.Entry(frame, textvariable=self.name_var, width=32)
        name_entry.grid(row=0, column=1, sticky=tk.W, **pad)
        name_entry.focus_set()

        # ── Tags ──────────────────────────────────────────────────────────────
        ttk.Label(frame, text="タグ").grid(row=1, column=0, sticky=tk.NE, **pad)
        tags_frame = ttk.Frame(frame)
        tags_frame.grid(row=1, column=1, sticky=tk.W, **pad)
        selected_ids = {t["id"] for t in deck["tags"]} if deck else set()
        self.tag_vars: dict = {}
        if self.tags:
            cols = 3
            for i, tag in enumerate(self.tags):
                var = tk.BooleanVar(value=tag["id"] in selected_ids)
                self.tag_vars[tag["id"]] = var
                ttk.Checkbutton(tags_frame, text=tag["name"], variable=var).grid(
                    row=i // cols, column=i % cols, sticky=tk.W, padx=6, pady=2)
        else:
            ttk.Label(tags_frame, text="タグが登録されていません",
                      foreground="gray").pack()

        # ── Weakness (弱み) ───────────────────────────────────────────────────
        ttk.Label(frame, text="弱み").grid(row=2, column=0, sticky=tk.NE, **pad)
        self._weakness_outer = ttk.Frame(frame)
        self._weakness_outer.grid(row=2, column=1, sticky=tk.W, **pad)
        self._wtag_vars: dict = {}
        self._wtag_check_frame = ttk.Frame(self._weakness_outer)
        self._wtag_check_frame.pack(anchor=tk.W)
        selected_wnames = {t["name"] for t in deck["weakness_tags"]} if deck else set()
        for wt in self.weakness_tags:
            self._add_weakness_checkbox(wt["name"], wt["name"] in selected_wnames)
        wadd = ttk.Frame(self._weakness_outer)
        wadd.pack(anchor=tk.W, pady=(6, 0))
        ttk.Label(wadd, text="新規追加:").pack(side=tk.LEFT, padx=(0, 4))
        self._wtag_entry_var = tk.StringVar()
        we = ttk.Entry(wadd, textvariable=self._wtag_entry_var, width=18)
        we.pack(side=tk.LEFT)
        ttk.Button(wadd, text="追加", command=self._add_wtag, width=5).pack(
            side=tk.LEFT, padx=(4, 0))
        we.bind("<Return>", lambda _: self._add_wtag())

        # ── Strength (強み) ───────────────────────────────────────────────────
        ttk.Label(frame, text="強み").grid(row=3, column=0, sticky=tk.NE, **pad)
        self._strength_outer = ttk.Frame(frame)
        self._strength_outer.grid(row=3, column=1, sticky=tk.W, **pad)
        self._stag_vars: dict = {}
        self._stag_check_frame = ttk.Frame(self._strength_outer)
        self._stag_check_frame.pack(anchor=tk.W)
        selected_snames = {t["name"] for t in deck["strength_tags"]} if deck else set()
        for st in self.strength_tags:
            self._add_strength_checkbox(st["name"], st["name"] in selected_snames)
        sadd = ttk.Frame(self._strength_outer)
        sadd.pack(anchor=tk.W, pady=(6, 0))
        ttk.Label(sadd, text="新規追加:").pack(side=tk.LEFT, padx=(0, 4))
        self._stag_entry_var = tk.StringVar()
        se = ttk.Entry(sadd, textvariable=self._stag_entry_var, width=18)
        se.pack(side=tk.LEFT)
        ttk.Button(sadd, text="追加", command=self._add_stag, width=5).pack(
            side=tk.LEFT, padx=(4, 0))
        se.bind("<Return>", lambda _: self._add_stag())

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btn_frame, text="保存", command=self._save, width=10).pack(
            side=tk.LEFT, padx=8)
        ttk.Button(btn_frame, text="キャンセル", command=self.top.destroy,
                   width=10).pack(side=tk.LEFT, padx=8)

        self.top.bind("<Return>", lambda _: self._save())
        self.top.bind("<Escape>", lambda _: self.top.destroy())

    # ── Tag helpers ───────────────────────────────────────────────────────────

    def _add_weakness_checkbox(self, name: str, checked: bool = True) -> None:
        if name in self._wtag_vars:
            if checked:
                self._wtag_vars[name].set(True)
            return
        var = tk.BooleanVar(value=checked)
        self._wtag_vars[name] = var
        ttk.Checkbutton(self._wtag_check_frame, text=name, variable=var).pack(anchor=tk.W)

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
        ttk.Checkbutton(self._stag_check_frame, text=name, variable=var).pack(anchor=tk.W)

    def _add_stag(self) -> None:
        name = self._stag_entry_var.get().strip()
        if name:
            self._add_strength_checkbox(name, checked=True)
            self._stag_entry_var.set("")

    # ── Save ──────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("入力エラー", "デッキ名を入力してください。", parent=self.top)
            return
        self.result = {
            "name": name,
            "tag_ids": [tid for tid, var in self.tag_vars.items() if var.get()],
            "weakness_tag_names": [n for n, v in self._wtag_vars.items() if v.get()],
            "strength_tag_names": [n for n, v in self._stag_vars.items() if v.get()],
        }
        self.top.destroy()
