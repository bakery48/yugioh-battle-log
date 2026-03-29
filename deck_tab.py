"""Deck management tab."""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Callable, Optional
import customtkinter as ctk

import database as db
from deck_dialog import DeckDialog

_FONT      = ctk.CTkFont(family="Meiryo", size=10)
_FONT_BOLD = ctk.CTkFont(family="Meiryo", size=10, weight="bold")


class DeckTab:
    def __init__(self, parent: tk.Widget,
                 on_deck_changed: Optional[Callable] = None):
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="both", expand=True)
        self.on_deck_changed = on_deck_changed
        self._tags: list = []
        self._decks: list = []
        self._build_ui()
        self.load_tags()
        self.load_decks()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        paned = ttk.PanedWindow(self.frame, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=6, pady=6)

        # ── Left: Tags ────────────────────────────────────────────────────────
        tags_outer = ttk.LabelFrame(paned, text="タグ管理", padding=6)
        paned.add(tags_outer, weight=1)

        list_frame = ttk.Frame(tags_outer)
        list_frame.pack(fill="both", expand=True)

        self.tags_listbox = tk.Listbox(
            list_frame, selectmode="single", activestyle="dotbox"
        )
        sb = ttk.Scrollbar(list_frame, orient="vertical",
                           command=self.tags_listbox.yview)
        self.tags_listbox.configure(yscrollcommand=sb.set)
        self.tags_listbox.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")

        btn_bar = ttk.Frame(tags_outer)
        btn_bar.pack(fill="x", pady=(6, 0))
        ttk.Button(btn_bar, text="＋ 追加",   command=self.add_tag,    width=7).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="名前変更",   command=self.rename_tag, width=7).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="削除",       command=self.delete_tag, width=5).pack(side="left", padx=2)

        # ── Right: Decks ──────────────────────────────────────────────────────
        decks_outer = ttk.LabelFrame(paned, text="デッキ管理", padding=6)
        paned.add(decks_outer, weight=3)

        tree_frame = ttk.Frame(decks_outer)
        tree_frame.pack(fill="both", expand=True)

        columns = ("name", "tags", "weakness", "strength")
        self.decks_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", selectmode="browse"
        )
        self.decks_tree.heading("name",     text="デッキ名")
        self.decks_tree.heading("tags",     text="タグ")
        self.decks_tree.heading("weakness", text="弱み")
        self.decks_tree.heading("strength", text="強み")
        self.decks_tree.column("name",     width=160)
        self.decks_tree.column("tags",     width=160)
        self.decks_tree.column("weakness", width=180)
        self.decks_tree.column("strength", width=180, stretch=True)

        dsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self.decks_tree.yview)
        self.decks_tree.configure(yscrollcommand=dsb.set)
        self.decks_tree.pack(side="left", fill="both", expand=True)
        dsb.pack(side="left", fill="y")

        dbtn_bar = ttk.Frame(decks_outer)
        dbtn_bar.pack(fill="x", pady=(6, 0))
        ttk.Button(dbtn_bar, text="＋ 追加", command=self.add_deck,    width=7).pack(side="left", padx=2)
        ttk.Button(dbtn_bar, text="編集",     command=self.edit_deck,   width=6).pack(side="left", padx=2)
        ttk.Button(dbtn_bar, text="削除",     command=self.delete_deck, width=5).pack(side="left", padx=2)

        self.decks_tree.bind("<Double-1>", lambda _: self.edit_deck())

    # ── Data loading ──────────────────────────────────────────────────────────

    def load_tags(self) -> None:
        self._tags = db.get_all_tags()
        self.tags_listbox.delete(0, "end")
        for tag in self._tags:
            self.tags_listbox.insert("end", tag["name"])

    def load_decks(self) -> None:
        self._decks = db.get_all_decks()
        for iid in self.decks_tree.get_children():
            self.decks_tree.delete(iid)
        for deck in self._decks:
            tag_names  = ", ".join(t["name"] for t in deck["tags"])
            weak_names = ", ".join(t["name"] for t in deck.get("weakness_tags", []))
            str_names  = ", ".join(t["name"] for t in deck.get("strength_tags", []))
            self.decks_tree.insert(
                "", "end", iid=str(deck["id"]),
                values=(deck["name"], tag_names, weak_names, str_names),
            )

    def apply_theme(self, colors: dict) -> None:
        self.tags_listbox.configure(
            bg=colors["listbox_bg"], fg=colors["listbox_fg"],
            selectbackground=colors["select_bg"],
            selectforeground=colors["select_fg"],
        )

    # ── Tag CRUD ──────────────────────────────────────────────────────────────

    def add_tag(self) -> None:
        name = simpledialog.askstring("タグを追加", "タグ名:", parent=self.frame)
        if name and name.strip():
            try:
                db.add_tag(name.strip())
                self.load_tags()
            except Exception as exc:
                messagebox.showerror("エラー", f"タグの追加に失敗しました。\n{exc}",
                                     parent=self.frame)

    def rename_tag(self) -> None:
        sel = self.tags_listbox.curselection()
        if not sel:
            messagebox.showinfo("選択なし", "名前変更するタグを選択してください。",
                                parent=self.frame)
            return
        tag = self._tags[sel[0]]
        new_name = simpledialog.askstring(
            "名前変更", "新しいタグ名:", initialvalue=tag["name"], parent=self.frame)
        if new_name and new_name.strip() and new_name.strip() != tag["name"]:
            try:
                db.rename_tag(tag["id"], new_name.strip())
                self.load_tags()
                self.load_decks()
            except Exception as exc:
                messagebox.showerror("エラー", f"タグの名前変更に失敗しました。\n{exc}",
                                     parent=self.frame)

    def delete_tag(self) -> None:
        sel = self.tags_listbox.curselection()
        if not sel:
            messagebox.showinfo("選択なし", "削除するタグを選択してください。",
                                parent=self.frame)
            return
        tag = self._tags[sel[0]]
        if messagebox.askyesno(
            "削除確認",
            f"タグ「{tag['name']}」を削除しますか？\nデッキとの関連も削除されます。",
            parent=self.frame,
        ):
            db.delete_tag(tag["id"])
            self.load_tags()
            self.load_decks()

    # ── Deck CRUD ─────────────────────────────────────────────────────────────

    def add_deck(self) -> None:
        dlg = DeckDialog(self.frame, tags=db.get_all_tags(),
                         weakness_tags=db.get_all_weakness_tags(),
                         strength_tags=db.get_all_strength_tags())
        self.frame.wait_window(dlg.top)
        if dlg.result:
            try:
                db.add_deck(dlg.result["name"], dlg.result["tag_ids"],
                            dlg.result["weakness_tag_names"],
                            dlg.result["strength_tag_names"])
                self.load_decks()
                if self.on_deck_changed:
                    self.on_deck_changed()
            except Exception as exc:
                messagebox.showerror("エラー", f"デッキの追加に失敗しました。\n{exc}",
                                     parent=self.frame)

    def edit_deck(self) -> None:
        sel = self.decks_tree.selection()
        if not sel:
            messagebox.showinfo("選択なし", "編集するデッキを選択してください。",
                                parent=self.frame)
            return
        deck_id = int(sel[0])
        deck = next((d for d in self._decks if d["id"] == deck_id), None)
        if not deck:
            return
        dlg = DeckDialog(self.frame, tags=db.get_all_tags(),
                         weakness_tags=db.get_all_weakness_tags(),
                         strength_tags=db.get_all_strength_tags(),
                         deck=deck)
        self.frame.wait_window(dlg.top)
        if dlg.result:
            try:
                db.update_deck(deck_id, dlg.result["name"], dlg.result["tag_ids"],
                               dlg.result["weakness_tag_names"],
                               dlg.result["strength_tag_names"])
                self.load_decks()
                if self.on_deck_changed:
                    self.on_deck_changed()
            except Exception as exc:
                messagebox.showerror("エラー", f"デッキの更新に失敗しました。\n{exc}",
                                     parent=self.frame)

    def delete_deck(self) -> None:
        sel = self.decks_tree.selection()
        if not sel:
            messagebox.showinfo("選択なし", "削除するデッキを選択してください。",
                                parent=self.frame)
            return
        deck_id = int(sel[0])
        deck = next((d for d in self._decks if d["id"] == deck_id), None)
        if not deck:
            return
        if messagebox.askyesno(
            "削除確認",
            f"デッキ「{deck['name']}」を削除しますか？\n"
            "このデッキに紐づく戦績のデッキ情報は「削除済み」になります。",
            parent=self.frame,
        ):
            db.delete_deck(deck_id)
            self.load_decks()
            if self.on_deck_changed:
                self.on_deck_changed()
