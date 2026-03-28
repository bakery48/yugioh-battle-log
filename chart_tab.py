"""Opponent deck distribution pie chart tab."""

import tkinter as tk
from tkinter import ttk, messagebox
from collections import Counter

import database as db
from constants import RANKS, MPL_FONT_CANDIDATES

try:
    import matplotlib
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    matplotlib.use("TkAgg")

    # Configure Japanese font
    available = {f.name for f in fm.fontManager.ttflist}
    chosen = next((f for f in MPL_FONT_CANDIDATES if f in available), None)
    if chosen:
        matplotlib.rcParams["font.family"] = chosen
    else:
        matplotlib.rcParams["font.family"] = "sans-serif"
        matplotlib.rcParams["axes.unicode_minus"] = False

    MPL_OK = True
except ImportError:
    MPL_OK = False

OTHERS_LABEL = "その他"
OTHERS_THRESHOLD = 0.05  # 5 %


class ChartTab:
    def __init__(self, parent: tk.Widget):
        self.frame = ttk.Frame(parent)
        self._build_ui()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        if not MPL_OK:
            ttk.Label(
                self.frame,
                text=(
                    "matplotlib がインストールされていません。\n"
                    "pip install matplotlib を実行してから再起動してください。"
                ),
                foreground="red",
            ).pack(pady=50)
            return

        # ── Filter panel ──────────────────────────────────────────────────────
        filter_frame = ttk.LabelFrame(self.frame, text="フィルタ", padding=8)
        filter_frame.pack(fill=tk.X, padx=6, pady=(6, 2))

        # Date range
        ttk.Label(filter_frame, text="期間:").grid(row=0, column=0, sticky=tk.E, padx=(0, 4))
        self.date_from_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.date_from_var, width=12).grid(
            row=0, column=1, padx=2
        )
        ttk.Label(filter_frame, text="～").grid(row=0, column=2)
        self.date_to_var = tk.StringVar()
        ttk.Entry(filter_frame, textvariable=self.date_to_var, width=12).grid(
            row=0, column=3, padx=2
        )
        ttk.Label(filter_frame, text="YYYY-MM-DD", foreground="gray").grid(
            row=0, column=4, padx=6
        )

        # Ranks
        ttk.Label(filter_frame, text="ランク:").grid(
            row=1, column=0, sticky=tk.E, padx=(0, 4), pady=4
        )
        rank_inner = ttk.Frame(filter_frame)
        rank_inner.grid(row=1, column=1, columnspan=6, sticky=tk.W)
        self.rank_vars: dict = {}
        for rank in RANKS:
            var = tk.BooleanVar()
            self.rank_vars[rank] = var
            ttk.Checkbutton(rank_inner, text=rank, variable=var).pack(
                side=tk.LEFT, padx=3
            )

        # Buttons
        btn_row = ttk.Frame(filter_frame)
        btn_row.grid(row=2, column=0, columnspan=7, pady=(6, 2))
        ttk.Button(btn_row, text="グラフ表示", command=self.draw_chart, width=10).pack(
            side=tk.LEFT, padx=6
        )
        ttk.Button(btn_row, text="リセット", command=self.reset, width=8).pack(
            side=tk.LEFT, padx=6
        )

        # ── Chart canvas ──────────────────────────────────────────────────────
        canvas_frame = ttk.Frame(self.frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.fig = Figure(dpi=100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=canvas_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self._draw_placeholder()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _draw_placeholder(self) -> None:
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.text(
            0.5, 0.5,
            "フィルタを設定して「グラフ表示」を押してください",
            ha="center", va="center",
            transform=ax.transAxes,
            fontsize=12, color="gray",
        )
        ax.axis("off")
        self.canvas.draw()

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

    # ── Public ────────────────────────────────────────────────────────────────

    def reset(self) -> None:
        self.date_from_var.set("")
        self.date_to_var.set("")
        for v in self.rank_vars.values():
            v.set(False)
        self._draw_placeholder()

    def draw_chart(self) -> None:
        filters = self._get_filters()
        battles = db.get_battles(filters or None)

        self.fig.clear()
        ax = self.fig.add_subplot(111)

        if not battles:
            ax.text(
                0.5, 0.5, "該当する戦績がありません",
                ha="center", va="center",
                transform=ax.transAxes, fontsize=12, color="gray",
            )
            ax.axis("off")
            self.canvas.draw()
            return

        total = len(battles)
        counter = Counter(b["opponent_deck"] for b in battles)

        threshold = OTHERS_THRESHOLD * total
        main: dict = {}
        others_count = 0
        for deck, count in counter.items():
            if count > threshold:
                main[deck] = count
            else:
                others_count += count

        if others_count > 0:
            main[OTHERS_LABEL] = others_count

        sorted_items = sorted(main.items(), key=lambda x: x[1], reverse=True)
        labels = [item[0] for item in sorted_items]
        sizes = [item[1] for item in sorted_items]

        # Colors
        cmap = plt.get_cmap("tab20")
        colors = [cmap(i / max(len(labels), 1)) for i in range(len(labels))]

        # Explode "その他" slice slightly
        explode = [0.05 if lbl == OTHERS_LABEL else 0.0 for lbl in labels]

        wedges, _, autotexts = ax.pie(
            sizes,
            labels=None,
            autopct=lambda p: f"{p:.1f}%" if p >= 3.0 else "",
            colors=colors,
            startangle=90,
            pctdistance=0.82,
            explode=explode,
            wedgeprops={"linewidth": 0.8, "edgecolor": "white"},
        )
        for at in autotexts:
            at.set_fontsize(8)

        # Legend with counts and percentages
        legend_labels = [
            f"{lbl}  {cnt}回 ({cnt / total * 100:.1f}%)"
            for lbl, cnt in zip(labels, sizes)
        ]
        ax.legend(
            wedges,
            legend_labels,
            title="相手デッキ",
            title_fontsize=9,
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            fontsize=8,
            framealpha=0.9,
        )

        ax.set_title(
            f"相手デッキ分布　（全 {total} 戦  ／  5% 以下は「{OTHERS_LABEL}」に統合）",
            fontsize=11,
            fontweight="bold",
            pad=12,
        )

        self.fig.tight_layout()
        self.canvas.draw()
