"""Dialog for adding / editing a deck."""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional

_FONT      = ("Meiryo", 10)
_FONT_BOLD = ("Meiryo", 10, "bold")


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
        self.top.withdraw()
        self.top.title("デッキを追加" if deck is None else "デッキを編集")
        self.top.resizable(False, False)
        self.top.grab_set()
        self.top.focus_set()

        self._build_ui(deck)

        self.top.update_idletasks()
        px = parent.winfo_rootx() + (parent.winfo_width()  - self.top.winfo_width())  // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.top.winfo_height()) // 2
        self.top.geometry(f"+{max(px, 0)}+{max(py, 0)}")
        self.top.deiconify()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self, deck: Optional[dict]) -> None:
        px, py = 12, 6

        # ── Deck name (outside canvas to avoid canvas keyboard routing issues) ─
        name_row = ttk.Frame(self.top)
        name_row.pack(fill="x", padx=16, pady=(12, 4))
        ttk.Label(name_row, text="デッキ名 *", font=_FONT_BOLD).pack(
            side="left", padx=(0, px))
        self.name_var = tk.StringVar(value=deck["name"] if deck else "")
        name_entry = ttk.Entry(name_row, textvariable=self.name_var,
                               width=30, font=_FONT)
        name_entry.pack(side="left")
        name_entry.bind("<Return>", lambda _: self._save())

        # ── Scrollable section (tags / weakness / strength) ───────────────────
        outer = ttk.Frame(self.top)
        outer.pack(fill="both", expand=True, padx=4, pady=0)

        self._canvas = tk.Canvas(outer, width=480, height=420,
                                 highlightthickness=0)
        vscroll = ttk.Scrollbar(outer, orient="vertical",
                                command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vscroll.set)
        vscroll.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        frame = ttk.Frame(self._canvas)
        _win = self._canvas.create_window((0, 0), window=frame, anchor="nw")

        frame.bind("<Configure>",
                   lambda e: self._canvas.configure(
                       scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfig(_win, width=e.width))

        # bind_all: チェックボックス等の子ウィジェット上でもスクロールが効くよう
        # ダイアログ全体にホイールを捕捉する（モーダルなので安全）
        def _scroll(e):
            self._canvas.yview_scroll(int(-e.delta / 120), "units")
        self._canvas.bind_all("<MouseWheel>", _scroll)
        # ダイアログを閉じたら bind_all を解除
        self.top.bind("<Destroy>",
                      lambda e: self._canvas.unbind_all("<MouseWheel>")
                      if e.widget is self.top else None)

        frame.columnconfigure(1, weight=1)

        def lbl(row, text, anchor="e"):
            ttk.Label(frame, text=text, font=_FONT_BOLD).grid(
                row=row, column=0, sticky=anchor, padx=(0, px), pady=py)

        # ── Tags ──────────────────────────────────────────────────────────────
        lbl(0, "タグ", anchor="ne")
        tags_frame = ttk.Frame(frame)
        tags_frame.grid(row=0, column=1, sticky="w", padx=px, pady=py)
        selected_ids = {t["id"] for t in deck["tags"]} if deck else set()
        self.tag_vars: dict = {}
        if self.tags:
            cols = 3
            for i, tag in enumerate(self.tags):
                var = tk.BooleanVar(value=tag["id"] in selected_ids)
                self.tag_vars[tag["id"]] = var
                ttk.Checkbutton(tags_frame, text=tag["name"],
                                variable=var).grid(
                    row=i // cols, column=i % cols, sticky="w", padx=6, pady=2)
        else:
            ttk.Label(tags_frame, text="タグが登録されていません",
                      foreground="gray").pack()

        # ── Weakness (弱み) ───────────────────────────────────────────────────
        lbl(1, "弱み", anchor="ne")
        self._weakness_outer = ttk.Frame(frame)
        self._weakness_outer.grid(row=1, column=1, sticky="w", padx=px, pady=py)
        self._wtag_vars: dict = {}
        self._wtag_check_frame = ttk.Frame(self._weakness_outer)
        self._wtag_check_frame.pack(anchor="w")
        selected_wnames = {t["name"] for t in deck["weakness_tags"]} if deck else set()
        for wt in self.weakness_tags:
            self._add_weakness_checkbox(wt["name"], wt["name"] in selected_wnames)
        wadd = ttk.Frame(self._weakness_outer)
        wadd.pack(anchor="w", pady=(6, 0))
        ttk.Label(wadd, text="新規追加:").pack(side="left", padx=(0, 4))
        self._wtag_entry_var = tk.StringVar()
        we = ttk.Entry(wadd, textvariable=self._wtag_entry_var, width=20,
                       font=_FONT)
        we.pack(side="left")
        ttk.Button(wadd, text="追加", command=self._add_wtag,
                   width=6).pack(side="left", padx=(4, 0))
        we.bind("<Return>", lambda _: self._add_wtag())

        # ── Strength (強み) ───────────────────────────────────────────────────
        lbl(2, "強み", anchor="ne")
        self._strength_outer = ttk.Frame(frame)
        self._strength_outer.grid(row=2, column=1, sticky="w", padx=px, pady=py)
        self._stag_vars: dict = {}
        self._stag_check_frame = ttk.Frame(self._strength_outer)
        self._stag_check_frame.pack(anchor="w")
        selected_snames = {t["name"] for t in deck["strength_tags"]} if deck else set()
        for st in self.strength_tags:
            self._add_strength_checkbox(st["name"], st["name"] in selected_snames)
        sadd = ttk.Frame(self._strength_outer)
        sadd.pack(anchor="w", pady=(6, 0))
        ttk.Label(sadd, text="新規追加:").pack(side="left", padx=(0, 4))
        self._stag_entry_var = tk.StringVar()
        se = ttk.Entry(sadd, textvariable=self._stag_entry_var, width=20,
                       font=_FONT)
        se.pack(side="left")
        ttk.Button(sadd, text="追加", command=self._add_stag,
                   width=6).pack(side="left", padx=(4, 0))
        se.bind("<Return>", lambda _: self._add_stag())

        # ── Buttons (outside canvas) ──────────────────────────────────────────
        btn_frame = ttk.Frame(self.top)
        btn_frame.pack(pady=(8, 12))
        ttk.Button(btn_frame, text="保存", command=self._save,
                   width=10).pack(side="left", padx=8)
        ttk.Button(btn_frame, text="キャンセル", command=self.top.destroy,
                   width=10).pack(side="left", padx=8)

        self.top.bind("<Escape>", lambda _: self.top.destroy())
        self.top.after(0, name_entry.focus_set)

    # ── Tag helpers ───────────────────────────────────────────────────────────

    def _add_weakness_checkbox(self, name: str, checked: bool = True) -> None:
        if name in self._wtag_vars:
            if checked:
                self._wtag_vars[name].set(True)
            return
        var = tk.BooleanVar(value=checked)
        self._wtag_vars[name] = var
        ttk.Checkbutton(self._wtag_check_frame, text=name,
                        variable=var).pack(anchor="w")

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
        ttk.Checkbutton(self._stag_check_frame, text=name,
                        variable=var).pack(anchor="w")

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
        self.top.withdraw()
        self.top.destroy()
