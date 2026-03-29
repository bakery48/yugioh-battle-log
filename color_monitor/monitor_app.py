"""
色変化監視アプリ - Color Change Monitor
指定したウィンドウの特定領域の色変化を監視し、変化を検知したらオーバーレイ通知を表示する
"""

import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
import threading
import time
import math
import sys
import ctypes
import json
import os

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

try:
    from PIL import ImageGrab, Image
    import win32gui
    import win32con
    import win32process
    import win32api
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "Pillow", "pywin32", "-q"], check=True)
    from PIL import ImageGrab, Image
    import win32gui
    import win32con
    import win32process
    import win32api

# DPI awareness for accurate coordinates
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass


# ─────────────────────────────────────────────
#  Utility
# ─────────────────────────────────────────────

def color_distance_pct(c1, c2):
    """2色間のユークリッド距離をパーセント(0-100)で返す"""
    r1, g1, b1 = c1
    r2, g2, b2 = c2
    dist = math.sqrt((r1-r2)**2 + (g1-g2)**2 + (b1-b2)**2)
    max_dist = math.sqrt(3 * 255**2)
    return dist / max_dist * 100


def get_region_avg_color(region):
    """指定領域(x1,y1,x2,y2)のスクリーンショットから平均色(R,G,B)を返す"""
    try:
        x1, y1, x2, y2 = region
        if x1 >= x2 or y1 >= y2:
            return None
        img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True)
        img_rgb = img.convert("RGB")
        pixels = list(img_rgb.getdata())
        if not pixels:
            return None
        r = sum(p[0] for p in pixels) // len(pixels)
        g = sum(p[1] for p in pixels) // len(pixels)
        b = sum(p[2] for p in pixels) // len(pixels)
        return (r, g, b)
    except Exception:
        return None


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def get_all_windows():
    """表示中のウィンドウタイトル一覧を返す (hwnd, title)"""
    result = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title.strip():
                result.append((hwnd, title))
    win32gui.EnumWindows(cb, None)
    return result


def get_pixel_color(x, y):
    """画面座標(x,y)のピクセル色を取得"""
    try:
        img = ImageGrab.grab(bbox=(x, y, x+1, y+1), all_screens=True)
        return img.getpixel((0, 0))[:3]
    except Exception:
        return (0, 0, 0)


def resolve_region(rel_region, hwnd):
    """ウィンドウ相対座標 → 現在のスクリーン絶対座標に変換
    rel_region: (rx1, ry1, rx2, ry2)  ウィンドウ左上からのオフセット
    hwnd: 監視対象ウィンドウハンドル
    戻り値: (ax1, ay1, ax2, ay2) スクリーン絶対座標, または None (ウィンドウが見つからない場合)
    """
    try:
        wx, wy, _, _ = win32gui.GetWindowRect(hwnd)
        rx1, ry1, rx2, ry2 = rel_region
        return (wx + rx1, wy + ry1, wx + rx2, wy + ry2)
    except Exception:
        return None


# ─────────────────────────────────────────────
#  RegionSelector: 全画面ドラッグで領域選択
# ─────────────────────────────────────────────

class RegionSelector:
    def __init__(self, root, callback):
        self.callback = callback
        self.start_x = self.start_y = 0
        self.rect_id = None

        self.win = tk.Toplevel(root)
        self.win.attributes("-fullscreen", True)
        self.win.attributes("-alpha", 0.35)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="black")
        self.win.overrideredirect(True)

        self.canvas = tk.Canvas(self.win, cursor="cross",
                                bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        lbl = tk.Label(self.canvas, text="ドラッグして監視領域を選択  /  ESCでキャンセル",
                       fg="white", bg="#333333", font=("Meiryo", 14),
                       padx=10, pady=5)
        lbl.place(relx=0.5, rely=0.02, anchor="n")

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.win.bind("<Escape>", lambda e: self._cancel())

    def _on_press(self, e):
        self.start_x, self.start_y = e.x, e.y
        if self.rect_id:
            self.canvas.delete(self.rect_id)

    def _on_drag(self, e):
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            self.start_x, self.start_y, e.x, e.y,
            outline="#00ff88", width=2, fill="#00ff88", stipple="gray25")

    def _on_release(self, e):
        x1 = min(self.start_x, e.x)
        y1 = min(self.start_y, e.y)
        x2 = max(self.start_x, e.x)
        y2 = max(self.start_y, e.y)
        self.win.destroy()
        if x2 - x1 > 3 and y2 - y1 > 3:
            self.callback((x1, y1, x2, y2))

    def _cancel(self):
        self.win.destroy()


# ─────────────────────────────────────────────
#  ColorPickerOverlay: クリックで画面の色を取得
# ─────────────────────────────────────────────

class ColorPickerOverlay:
    def __init__(self, root, callback):
        self.callback = callback

        self.win = tk.Toplevel(root)
        self.win.attributes("-fullscreen", True)
        self.win.attributes("-alpha", 0.01)
        self.win.attributes("-topmost", True)
        self.win.overrideredirect(True)
        self.win.configure(cursor="crosshair")

        self.win.bind("<ButtonPress-1>", self._on_click)
        self.win.bind("<Escape>", lambda e: self.win.destroy())

    def _on_click(self, e):
        # スクリーン絶対座標を取得
        sx = self.win.winfo_rootx() + e.x
        sy = self.win.winfo_rooty() + e.y
        self.win.destroy()
        color = get_pixel_color(sx, sy)
        self.callback(color)


# ─────────────────────────────────────────────
#  AlertWindow: 変化検知時のオーバーレイ通知
# ─────────────────────────────────────────────

class AlertWindow:
    def __init__(self, root):
        self.win = tk.Toplevel(root)
        self.win.attributes("-topmost", True)
        self.win.overrideredirect(True)

        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        w, h = int(sw * 0.7), int(sh * 0.4)
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.win.geometry(f"{w}x{h}+{x}+{y}")

        self.canvas = tk.Canvas(self.win, bg="#cc0000",
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        # アニメーション用
        self._anim_colors = ["#ff2222", "#cc0000", "#ff4444", "#aa0000"]
        self._anim_idx = 0
        self._anim_active = True

        # テキスト
        self.canvas.create_text(
            w // 2, h * 0.38,
            text="⚠  色が変わりました！",
            fill="white",
            font=("Meiryo", max(30, w // 14), "bold"),
            anchor="center"
        )
        self.canvas.create_text(
            w // 2, h * 0.65,
            text="クリックして閉じる",
            fill="#ffdddd",
            font=("Meiryo", max(14, w // 32)),
            anchor="center"
        )

        self.win.bind("<Button-1>", lambda e: self._close())
        self.win.bind("<Escape>", lambda e: self._close())

        self._animate()

    def _animate(self):
        if not self._anim_active:
            return
        c = self._anim_colors[self._anim_idx % len(self._anim_colors)]
        self.canvas.configure(bg=c)
        self._anim_idx += 1
        self.win.after(400, self._animate)

    def _close(self):
        self._anim_active = False
        self.win.destroy()


# ─────────────────────────────────────────────
#  MonitorThread: バックグラウンド監視ループ
# ─────────────────────────────────────────────

class MonitorThread(threading.Thread):
    def __init__(self, config, alert_callback):
        super().__init__(daemon=True)
        self.config = config
        self.alert_callback = alert_callback
        self._stop_event = threading.Event()

        # 状態機械
        # WAIT_START: 開始色を待つ
        # WAIT_END:   終了色を待つ (開始色を検知済み)
        # WAIT_TIMER: 終了色を検知して指定秒数経過待ち
        self._state = "WAIT_START"
        self._end_detected_at = None

    def run(self):
        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception:
                pass
            time.sleep(0.1)

    def stop(self):
        self._stop_event.set()

    def _tick(self):
        rel_region = self.config["region"]
        hwnd = self.config["hwnd"]
        start_color = self.config["start_color"]
        end_color = self.config["end_color"]
        threshold = self.config["threshold"]
        wait_sec = self.config["wait_sec"]

        if not rel_region or not start_color or not end_color:
            return

        # ウィンドウ現在位置に追従して絶対座標を解決
        region = resolve_region(rel_region, hwnd)
        if region is None:
            return

        avg = get_region_avg_color(region)
        if avg is None:
            return

        dist_start = color_distance_pct(avg, start_color)
        dist_end = color_distance_pct(avg, end_color)

        if self._state == "WAIT_START":
            if dist_start <= threshold:
                self._state = "WAIT_END"
        elif self._state == "WAIT_END":
            if dist_end <= threshold:
                self._state = "WAIT_TIMER"
                self._end_detected_at = time.time()
            elif dist_start > threshold * 2:
                # 開始色でも終了色でもない → リセット
                self._state = "WAIT_START"
        elif self._state == "WAIT_TIMER":
            if dist_end <= threshold:
                elapsed = time.time() - self._end_detected_at
                if elapsed >= wait_sec:
                    self._state = "WAIT_START"
                    self.alert_callback()
            else:
                # 終了色でなくなった → キャンセル
                self._state = "WAIT_START"
                self._end_detected_at = None


# ─────────────────────────────────────────────
#  MainApp: メインウィンドウ・設定UI
# ─────────────────────────────────────────────

class MainApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("色変化監視アプリ")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e2e")

        # フォント
        self.font_label = ("Meiryo", 10)
        self.font_bold = ("Meiryo", 10, "bold")
        self.font_small = ("Meiryo", 9)

        # 設定値
        self.region = None
        self.start_color = None
        self.end_color = None
        self.selected_hwnd = None
        self._saved_window_title = None  # タイトルによる自動マッチング用

        self._monitor_thread = None
        self._windows_list = []

        self._build_ui()
        self._load_settings()          # UI構築後に設定読み込み
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    # ── UI構築 ────────────────────────────────

    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}

        # ── タイトル
        title_frame = tk.Frame(self.root, bg="#12122a", pady=8)
        title_frame.pack(fill="x")
        tk.Label(title_frame, text="🎨  色変化監視アプリ",
                 fg="#a0d0ff", bg="#12122a",
                 font=("Meiryo", 16, "bold")).pack()

        main = tk.Frame(self.root, bg="#1e1e2e", padx=16, pady=10)
        main.pack(fill="both", expand=True)

        # ── セクション 1: ウィンドウ選択
        self._section(main, "🖥  監視対象ウィンドウ")
        wframe = tk.Frame(main, bg="#1e1e2e")
        wframe.pack(fill="x", pady=(0, 8))

        self.win_combo = ttk.Combobox(wframe, state="readonly", width=38,
                                      font=self.font_label)
        self.win_combo.pack(side="left", padx=(0, 6))
        self.win_combo.bind("<<ComboboxSelected>>", self._on_window_select)

        tk.Button(wframe, text="🔄 更新", command=self._refresh_windows,
                  bg="#3a3a5c", fg="white", font=self.font_small,
                  relief="flat", padx=8, cursor="hand2"
                  ).pack(side="left")

        self._refresh_windows()

        # ── セクション 2: 監視領域
        self._section(main, "📐  監視領域")
        rframe = tk.Frame(main, bg="#1e1e2e")
        rframe.pack(fill="x", pady=(0, 8))

        self.region_label = tk.Label(rframe, text="未設定", fg="#888",
                                     bg="#2a2a3e", font=self.font_small,
                                     width=28, relief="sunken", padx=4)
        self.region_label.pack(side="left", padx=(0, 6))

        tk.Button(rframe, text="🖱 ドラッグで選択",
                  command=self._pick_region,
                  bg="#3a3a5c", fg="white", font=self.font_small,
                  relief="flat", padx=8, cursor="hand2"
                  ).pack(side="left")

        # ── セクション 3: 色設定
        self._section(main, "🎨  色設定")
        cframe = tk.Frame(main, bg="#1e1e2e")
        cframe.pack(fill="x", pady=(0, 8))

        # 開始色
        sf = tk.Frame(cframe, bg="#1e1e2e")
        sf.pack(side="left", padx=(0, 20))
        tk.Label(sf, text="開始色 (変化前)", fg="#aaa", bg="#1e1e2e",
                 font=self.font_small).pack(anchor="w")
        srow = tk.Frame(sf, bg="#1e1e2e")
        srow.pack()
        self.start_canvas = tk.Canvas(srow, width=36, height=28,
                                      bg="#555", relief="sunken", bd=1)
        self.start_canvas.pack(side="left", padx=(0, 4))
        self.start_label = tk.Label(srow, text="未設定", fg="#888",
                                    bg="#1e1e2e", font=self.font_small, width=8)
        self.start_label.pack(side="left")
        tk.Button(sf, text="スクリーンから取得",
                  command=lambda: self._pick_color("start"),
                  bg="#3a3a5c", fg="white", font=self.font_small,
                  relief="flat", padx=6, cursor="hand2").pack(pady=(2, 0))
        tk.Button(sf, text="カラーダイアログ",
                  command=lambda: self._pick_color_dialog("start"),
                  bg="#2a2a3e", fg="#aaa", font=self.font_small,
                  relief="flat", padx=6, cursor="hand2").pack(pady=(2, 0))

        # 終了色
        ef = tk.Frame(cframe, bg="#1e1e2e")
        ef.pack(side="left")
        tk.Label(ef, text="終了色 (変化後)", fg="#aaa", bg="#1e1e2e",
                 font=self.font_small).pack(anchor="w")
        erow = tk.Frame(ef, bg="#1e1e2e")
        erow.pack()
        self.end_canvas = tk.Canvas(erow, width=36, height=28,
                                    bg="#555", relief="sunken", bd=1)
        self.end_canvas.pack(side="left", padx=(0, 4))
        self.end_label = tk.Label(erow, text="未設定", fg="#888",
                                  bg="#1e1e2e", font=self.font_small, width=8)
        self.end_label.pack(side="left")
        tk.Button(ef, text="スクリーンから取得",
                  command=lambda: self._pick_color("end"),
                  bg="#3a3a5c", fg="white", font=self.font_small,
                  relief="flat", padx=6, cursor="hand2").pack(pady=(2, 0))
        tk.Button(ef, text="カラーダイアログ",
                  command=lambda: self._pick_color_dialog("end"),
                  bg="#2a2a3e", fg="#aaa", font=self.font_small,
                  relief="flat", padx=6, cursor="hand2").pack(pady=(2, 0))

        # ── セクション 4: パラメータ
        self._section(main, "⚙  監視パラメータ")
        pframe = tk.Frame(main, bg="#1e1e2e")
        pframe.pack(fill="x", pady=(0, 8))

        # 閾値
        tf = tk.Frame(pframe, bg="#1e1e2e")
        tf.pack(side="left", padx=(0, 24))
        tk.Label(tf, text="色一致の閾値 (%)", fg="#aaa", bg="#1e1e2e",
                 font=self.font_small).pack(anchor="w")
        trow = tk.Frame(tf, bg="#1e1e2e")
        trow.pack()
        self.threshold_var = tk.DoubleVar(value=10.0)
        self.threshold_slider = ttk.Scale(trow, from_=1, to=50,
                                          variable=self.threshold_var,
                                          orient="horizontal", length=160,
                                          command=self._on_threshold_change)
        self.threshold_slider.pack(side="left")
        self.threshold_disp = tk.Label(trow, text="10.0%", fg="white",
                                       bg="#1e1e2e", font=self.font_small, width=6)
        self.threshold_disp.pack(side="left", padx=(4, 0))

        # 待機時間
        df = tk.Frame(pframe, bg="#1e1e2e")
        df.pack(side="left")
        tk.Label(df, text="検知後の待機時間 (秒)", fg="#aaa", bg="#1e1e2e",
                 font=self.font_small).pack(anchor="w")
        self.wait_var = tk.StringVar(value="3")
        tk.Spinbox(df, from_=0, to=3600, textvariable=self.wait_var,
                   width=6, font=self.font_label,
                   bg="#2a2a3e", fg="white", insertbackground="white",
                   buttonbackground="#3a3a5c").pack(anchor="w")

        # ── セクション 5: 監視状態表示
        self._section(main, "📊  状態")
        sframe = tk.Frame(main, bg="#1e1e2e")
        sframe.pack(fill="x", pady=(0, 8))

        self.status_label = tk.Label(sframe, text="●  停止中",
                                     fg="#888", bg="#2a2a3e",
                                     font=("Meiryo", 11, "bold"),
                                     relief="sunken", padx=10, pady=4)
        self.status_label.pack(side="left", padx=(0, 10))

        self.color_preview = tk.Label(sframe, text="現在色: ─",
                                      fg="#aaa", bg="#1e1e2e",
                                      font=self.font_small)
        self.color_preview.pack(side="left")

        self.cur_color_canvas = tk.Canvas(sframe, width=28, height=20,
                                          bg="#555", relief="sunken", bd=1)
        self.cur_color_canvas.pack(side="left", padx=(4, 0))

        # ── 操作ボタン
        bframe = tk.Frame(self.root, bg="#12122a", pady=8)
        bframe.pack(fill="x")

        self.start_btn = tk.Button(bframe, text="▶  監視開始",
                                   command=self._start_monitor,
                                   bg="#007acc", fg="white",
                                   font=("Meiryo", 11, "bold"),
                                   relief="flat", padx=20, pady=6,
                                   cursor="hand2")
        self.start_btn.pack(side="left", padx=(16, 8))

        self.stop_btn = tk.Button(bframe, text="■  停止",
                                  command=self._stop_monitor,
                                  bg="#555", fg="#aaa",
                                  font=("Meiryo", 11, "bold"),
                                  relief="flat", padx=20, pady=6,
                                  cursor="hand2", state="disabled")
        self.stop_btn.pack(side="left")

        # 色更新タイマー
        self._update_color_preview()

    def _section(self, parent, title):
        f = tk.Frame(parent, bg="#1e1e2e")
        f.pack(fill="x", pady=(8, 2))
        tk.Label(f, text=title, fg="#a0d0ff", bg="#1e1e2e",
                 font=self.font_bold).pack(side="left")
        sep = tk.Frame(f, bg="#3a3a5c", height=1)
        sep.pack(side="left", fill="x", expand=True, padx=(6, 0))

    # ── イベントハンドラ ──────────────────────

    def _refresh_windows(self, match_title=None):
        wins = get_all_windows()
        self._windows_list = wins
        titles = [f"{hwnd}  │  {t[:60]}" for hwnd, t in wins]
        self.win_combo["values"] = titles
        # タイトルでの自動マッチング
        if match_title:
            for i, (_, t) in enumerate(wins):
                if match_title in t or t in match_title:
                    self.win_combo.current(i)
                    self._on_window_select(None)
                    return
        if titles:
            self.win_combo.current(0)
            self._on_window_select(None)

    def _on_window_select(self, _):
        idx = self.win_combo.current()
        if 0 <= idx < len(self._windows_list):
            self.selected_hwnd, _ = self._windows_list[idx]

    def _pick_region(self):
        self.root.iconify()
        time.sleep(0.3)
        RegionSelector(self.root, self._on_region_selected)

    def _on_region_selected(self, abs_region):
        """スクリーン絶対座標で選択された領域をウィンドウ相対座標に変換して保存"""
        ax1, ay1, ax2, ay2 = abs_region
        w = ax2 - ax1
        h = ay2 - ay1
        if self.selected_hwnd:
            try:
                wx, wy, _, _ = win32gui.GetWindowRect(self.selected_hwnd)
                rx1, ry1 = ax1 - wx, ay1 - wy
                self.region = (rx1, ry1, rx1 + w, ry1 + h)
                self.region_label.config(
                    text=f"ウィンドウ相対 ({rx1},{ry1}) [{w}×{h}]",
                    fg="white")
            except Exception:
                # hwnd取得失敗時は絶対座標で保存
                self.region = abs_region
                self.region_label.config(
                    text=f"({ax1},{ay1}) → ({ax2},{ay2}) [{w}×{h}]",
                    fg="#ffaa44")
        else:
            self.region = abs_region
            self.region_label.config(
                text=f"({ax1},{ay1}) → ({ax2},{ay2}) [{w}×{h}]",
                fg="#ffaa44")
        self.root.deiconify()

    def _pick_color(self, which):
        self.root.iconify()
        time.sleep(0.3)
        ColorPickerOverlay(self.root,
                           lambda c: self._on_color_picked(which, c))

    def _on_color_picked(self, which, color):
        self.root.deiconify()
        self._set_color(which, color)

    def _pick_color_dialog(self, which):
        initial = None
        if which == "start" and self.start_color:
            initial = rgb_to_hex(self.start_color)
        elif which == "end" and self.end_color:
            initial = rgb_to_hex(self.end_color)
        result = colorchooser.askcolor(color=initial,
                                       title="色を選択")
        if result and result[0]:
            rgb = tuple(int(v) for v in result[0])
            self._set_color(which, rgb)

    def _set_color(self, which, color):
        hex_c = rgb_to_hex(color)
        if which == "start":
            self.start_color = color
            self.start_canvas.configure(bg=hex_c)
            self.start_label.configure(text=hex_c, fg="white")
        else:
            self.end_color = color
            self.end_canvas.configure(bg=hex_c)
            self.end_label.configure(text=hex_c, fg="white")

    def _on_threshold_change(self, _):
        val = round(self.threshold_var.get(), 1)
        self.threshold_disp.config(text=f"{val}%")

    # ── 監視制御 ─────────────────────────────

    def _start_monitor(self):
        if not self.region:
            messagebox.showwarning("設定不足", "監視領域を設定してください")
            return
        if not self.start_color:
            messagebox.showwarning("設定不足", "開始色を設定してください")
            return
        if not self.end_color:
            messagebox.showwarning("設定不足", "終了色を設定してください")
            return

        try:
            wait_sec = float(self.wait_var.get())
        except ValueError:
            wait_sec = 3.0

        config = {
            "region": self.region,
            "hwnd": self.selected_hwnd,
            "start_color": self.start_color,
            "end_color": self.end_color,
            "threshold": self.threshold_var.get(),
            "wait_sec": wait_sec,
        }

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.stop()

        self._monitor_thread = MonitorThread(config, self._on_alert)
        self._monitor_thread.start()

        self.status_label.config(text="●  監視中", fg="#00ff88")
        self.start_btn.config(state="disabled", bg="#555")
        self.stop_btn.config(state="normal", bg="#cc4444", fg="white")

    def _stop_monitor(self):
        if self._monitor_thread:
            self._monitor_thread.stop()
        self.status_label.config(text="●  停止中", fg="#888")
        self.start_btn.config(state="normal", bg="#007acc")
        self.stop_btn.config(state="disabled", bg="#555", fg="#aaa")

    def _on_alert(self):
        """監視スレッドから呼ばれる → GUIスレッドで通知ウィンドウを開く"""
        self.root.after(0, self._show_alert)

    def _show_alert(self):
        AlertWindow(self.root)

    # ── 設定の保存・読み込み ──────────────────

    def _on_close(self):
        self._save_settings()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.stop()
        self.root.destroy()

    def _save_settings(self):
        # 現在選択中のウィンドウタイトルを保存
        win_title = None
        idx = self.win_combo.current()
        if 0 <= idx < len(self._windows_list):
            _, win_title = self._windows_list[idx]

        data = {
            "window_title": win_title,
            "start_color": list(self.start_color) if self.start_color else None,
            "end_color":   list(self.end_color)   if self.end_color   else None,
            "region":      list(self.region)       if self.region      else None,
            "threshold":   self.threshold_var.get(),
            "wait_sec":    self.wait_var.get(),
        }
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            return
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        # 色設定
        if data.get("start_color"):
            self._set_color("start", tuple(data["start_color"]))
        if data.get("end_color"):
            self._set_color("end", tuple(data["end_color"]))

        # 監視パラメータ
        if data.get("threshold") is not None:
            self.threshold_var.set(data["threshold"])
            self._on_threshold_change(None)
        if data.get("wait_sec") is not None:
            self.wait_var.set(str(data["wait_sec"]))

        # 監視領域
        if data.get("region"):
            r = tuple(data["region"])
            self.region = r
            rx1, ry1, rx2, ry2 = r
            w, h = rx2 - rx1, ry2 - ry1
            self.region_label.config(
                text=f"ウィンドウ相対 ({rx1},{ry1}) [{w}×{h}]",
                fg="white")

        # ウィンドウタイトルで自動マッチング
        if data.get("window_title"):
            self._refresh_windows(match_title=data["window_title"])

    # ── 現在色プレビュー更新 ──────────────────

    def _update_color_preview(self):
        if self.region and self._monitor_thread and self._monitor_thread.is_alive():
            # ウィンドウ相対座標を現在の絶対座標に変換してプレビュー
            abs_region = resolve_region(self.region, self.selected_hwnd) \
                if self.selected_hwnd else self.region
            if abs_region:
                avg = get_region_avg_color(abs_region)
                if avg:
                    hex_c = rgb_to_hex(avg)
                    self.color_preview.config(text=f"現在色: {hex_c}")
                    self.cur_color_canvas.configure(bg=hex_c)
        self.root.after(500, self._update_color_preview)


# ─────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    MainApp()
