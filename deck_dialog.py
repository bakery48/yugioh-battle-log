"""Dialog for adding / editing a deck."""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional



class DeckDialog:
    """Modal dialog that returns a result dict on save, or None on cancel."""

    def __init__(self, parent: tk.Widget, tags: list, deck: Optional[dict] = None):
        self.result: Optional[dict] = None
        self.tags = tags

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
                ttk.Checkbutton(
                    tags_frame, text=tag["name"], variable=var
                ).grid(row=i // cols, column=i % cols, sticky=tk.W, padx=6, pady=2)
        else:
            ttk.Label(
                tags_frame, text="タグが登録されていません", foreground="gray"
            ).pack()

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btn_frame, text="保存", command=self._save, width=10).pack(
            side=tk.LEFT, padx=8
        )
        ttk.Button(
            btn_frame, text="キャンセル", command=self.top.destroy, width=10
        ).pack(side=tk.LEFT, padx=8)

        self.top.bind("<Return>", lambda _: self._save())
        self.top.bind("<Escape>", lambda _: self.top.destroy())

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _save(self) -> None:
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("入力エラー", "デッキ名を入力してください。", parent=self.top)
            return

        tag_ids = [tid for tid, var in self.tag_vars.items() if var.get()]
        self.result = {"name": name, "tag_ids": tag_ids}
        self.top.destroy()
