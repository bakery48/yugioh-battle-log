"""Color change monitor tab."""

import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
import threading
import time
import math
import json
import os
import sys

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "color_monitor", "settings.json")

try:
    from PIL import ImageGrab
    import win32gui
    _DEPS_OK = True
except ImportError:
    _DEPS_OK = False


# ─── Utilities ────────────────────────────────────────────────────────────────

def _color_distance_pct(c1, c2):
    dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))
    return dist / math.sqrt(3 * 255 ** 2) * 100


def _get_region_avg_color(region):
    try:
        x1, y1, x2, y2 = region
        if x1 >= x2 or y1 >= y2:
            return None
        img = ImageGrab.grab(bbox=(x1, y1, x2, y2), all_screens=True).convert("RGB")
        pixels = list(img.getdata())
        if not pixels:
            return None
        n = len(pixels)
        return (sum(p[0] for p in pixels) // n,
                sum(p[1] for p in pixels) // n,
                sum(p[2] for p in pixels) // n)
    except Exception:
        return None


def _get_pixel_color(x, y):
    try:
        return ImageGrab.grab(bbox=(x, y, x + 1, y + 1), all_screens=True).getpixel((0, 0))[:3]
    except Exception:
        return (0, 0, 0)


def _rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _get_all_windows():
    result = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title.strip():
                result.append((hwnd, title))
    win32gui.EnumWindows(cb, None)
    return result


def _resolve_region(rel_region, hwnd):
    """ウィンドウ相対座標 → スクリーン絶対座標"""
    try:
        wx, wy, _, _ = win32gui.GetWindowRect(hwnd)
        rx1, ry1, rx2, ry2 = rel_region
        return (wx + rx1, wy + ry1, wx + rx2, wy + ry2)
    except Exception:
        return None


# ─── RegionSelector ───────────────────────────────────────────────────────────

class _RegionSelector:
    """全画面ドラッグで領域を選択し、スクリーン絶対座標で callback を呼ぶ。"""

    def __init__(self, root, callback):
        self.callback = callback
        self.start_x = self.start_y = 0
        self.rect_id = None

        self.win = tk.Toplevel(root)
        self.win.attributes("-fullscreen", True)
        self.win.attributes("-alpha", 0.35)
        self.win.attributes("-topmost", True)
        self.win.overrideredirect(True)
        self.win.configure(bg="black")

        self.canvas = tk.Canvas(self.win, cursor="cross", bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        tk.Label(self.canvas, text="ドラッグして監視領域を選択  /  ESCでキャンセル",
                 fg="white", bg="#333333", font=("Meiryo", 14), padx=10, pady=5
                 ).place(relx=0.5, rely=0.02, anchor="n")

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.win.bind("<Escape>", lambda e: self.win.destroy())

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
        x1, y1 = min(self.start_x, e.x), min(self.start_y, e.y)
        x2, y2 = max(self.start_x, e.x), max(self.start_y, e.y)
        self.win.destroy()
        if x2 - x1 > 3 and y2 - y1 > 3:
            self.callback((x1, y1, x2, y2))


# ─── ColorPickerOverlay ───────────────────────────────────────────────────────

class _ColorPickerOverlay:
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
        sx = self.win.winfo_rootx() + e.x
        sy = self.win.winfo_rooty() + e.y
        self.win.destroy()
        self.callback(_get_pixel_color(sx, sy))


# ─── AlertWindow ──────────────────────────────────────────────────────────────

class _AlertWindow:
    def __init__(self, root):
        self.win = tk.Toplevel(root)
        self.win.attributes("-topmost", True)
        self.win.overrideredirect(True)

        sw, sh = self.win.winfo_screenwidth(), self.win.winfo_screenheight()
        w, h = int(sw * 0.7), int(sh * 0.4)
        self.win.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

        self.canvas = tk.Canvas(self.win, bg="#cc0000", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(w // 2, int(h * 0.38),
                                text="⚠  色が変わりました！", fill="white",
                                font=("Meiryo", max(30, w // 14), "bold"), anchor="center")
        self.canvas.create_text(w // 2, int(h * 0.65),
                                text="クリックして閉じる", fill="#ffdddd",
                                font=("Meiryo", max(14, w // 32)), anchor="center")
        self.win.bind("<Button-1>", lambda e: self._close())
        self.win.bind("<Escape>",   lambda e: self._close())

        self._colors = ["#ff2222", "#cc0000", "#ff4444", "#aa0000"]
        self._idx = 0
        self._active = True
        self._animate()

    def _animate(self):
        if not self._active:
            return
        self.canvas.configure(bg=self._colors[self._idx % len(self._colors)])
        self._idx += 1
        self.win.after(400, self._animate)

    def _close(self):
        self._active = False
        self.win.destroy()


# ─── MonitorThread ────────────────────────────────────────────────────────────

class _MonitorThread(threading.Thread):
    def __init__(self, config, alert_callback):
        super().__init__(daemon=True)
        self.config = config
        self.alert_callback = alert_callback
        self._stop_event = threading.Event()
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
        hwnd       = self.config["hwnd"]
        start_color = self.config["start_color"]
        end_color   = self.config["end_color"]
        threshold   = self.config["threshold"]
        wait_sec    = self.config["wait_sec"]

        if not rel_region or not start_color or not end_color:
            return

        # ウィンドウ相対座標をその都度絶対座標に変換 → ウィンドウ移動に追従
        region = _resolve_region(rel_region, hwnd)
        if region is None:
            return

        avg = _get_region_avg_color(region)
        if avg is None:
            return

        dist_start = _color_distance_pct(avg, start_color)
        dist_end   = _color_distance_pct(avg, end_color)

        if self._state == "WAIT_START":
            if dist_start <= threshold:
                self._state = "WAIT_END"
        elif self._state == "WAIT_END":
            if dist_end <= threshold:
                self._state = "WAIT_TIMER"
                self._end_detected_at = time.time()
            elif dist_start > threshold * 2:
                self._state = "WAIT_START"
        elif self._state == "WAIT_TIMER":
            if dist_end <= threshold:
                if time.time() - self._end_detected_at >= wait_sec:
                    self._state = "WAIT_START"
                    self.alert_callback()
            else:
                self._state = "WAIT_START"
                self._end_detected_at = None


# ─── ColorMonitorTab ──────────────────────────────────────────────────────────

class ColorMonitorTab:
    def __init__(self, parent: tk.Widget):
        self.frame = tk.Frame(parent, bg="#1e1e2e")

        if not _DEPS_OK:
            tk.Label(self.frame,
                     text="Pillow と pywin32 が必要です。\npip install Pillow pywin32",
                     bg="#1e1e2e", fg="#ff8888",
                     font=("Meiryo", 12), justify="center"
                     ).pack(expand=True)
            return

        self.region = None
        self.start_color = None
        self.end_color = None
        self.selected_hwnd = None
        self._windows_list = []
        self._monitor_thread = None

        self._build_ui()
        self._load_settings()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # タイトル
        title_frame = tk.Frame(self.frame, bg="#12122a", pady=8)
        title_frame.pack(fill="x")
        tk.Label(title_frame, text="🎨  色変化監視",
                 fg="#a0d0ff", bg="#12122a",
                 font=("Meiryo", 14, "bold")).pack()

        main = tk.Frame(self.frame, bg="#1e1e2e", padx=16, pady=10)
        main.pack(fill="both", expand=True)

        # セクション1: ウィンドウ選択
        self._section(main, "🖥  監視対象ウィンドウ")
        wf = tk.Frame(main, bg="#1e1e2e")
        wf.pack(fill="x", pady=(0, 8))
        self.win_combo = ttk.Combobox(wf, state="readonly", width=40,
                                      font=("Meiryo", 9))
        self.win_combo.pack(side="left", padx=(0, 6))
        self.win_combo.bind("<<ComboboxSelected>>", self._on_window_select)
        tk.Button(wf, text="🔄 更新", command=self._refresh_windows,
                  bg="#3a3a5c", fg="white", font=("Meiryo", 9),
                  relief="flat", padx=8, cursor="hand2").pack(side="left")
        self._refresh_windows()

        # セクション2: 監視領域（ウィンドウ相対座標）
        self._section(main, "📐  監視領域  ※ウィンドウ内の相対座標で記録")
        rf = tk.Frame(main, bg="#1e1e2e")
        rf.pack(fill="x", pady=(0, 8))
        self.region_label = tk.Label(rf, text="未設定", fg="#888",
                                     bg="#2a2a3e", font=("Meiryo", 9),
                                     width=30, relief="sunken", padx=4)
        self.region_label.pack(side="left", padx=(0, 6))
        tk.Button(rf, text="🖱 ドラッグで選択", command=self._pick_region,
                  bg="#3a3a5c", fg="white", font=("Meiryo", 9),
                  relief="flat", padx=8, cursor="hand2").pack(side="left")

        # セクション3: 色設定
        self._section(main, "🎨  色設定")
        cf = tk.Frame(main, bg="#1e1e2e")
        cf.pack(fill="x", pady=(0, 8))

        for which, label in (("start", "開始色 (変化前)"), ("end", "終了色 (変化後)")):
            sf = tk.Frame(cf, bg="#1e1e2e")
            sf.pack(side="left", padx=(0, 24))
            tk.Label(sf, text=label, fg="#aaa", bg="#1e1e2e",
                     font=("Meiryo", 9)).pack(anchor="w")
            row = tk.Frame(sf, bg="#1e1e2e")
            row.pack()
            canvas = tk.Canvas(row, width=36, height=28, bg="#555",
                               relief="sunken", bd=1)
            canvas.pack(side="left", padx=(0, 4))
            lbl = tk.Label(row, text="未設定", fg="#888", bg="#1e1e2e",
                           font=("Meiryo", 9), width=9)
            lbl.pack(side="left")
            if which == "start":
                self.start_canvas, self.start_label = canvas, lbl
            else:
                self.end_canvas, self.end_label = canvas, lbl
            tk.Button(sf, text="スクリーンから取得",
                      command=lambda w=which: self._pick_color(w),
                      bg="#3a3a5c", fg="white", font=("Meiryo", 9),
                      relief="flat", padx=6, cursor="hand2").pack(pady=(2, 0))
            tk.Button(sf, text="カラーダイアログ",
                      command=lambda w=which: self._pick_color_dialog(w),
                      bg="#2a2a3e", fg="#aaa", font=("Meiryo", 9),
                      relief="flat", padx=6, cursor="hand2").pack(pady=(2, 0))

        # セクション4: パラメータ
        self._section(main, "⚙  監視パラメータ")
        pf = tk.Frame(main, bg="#1e1e2e")
        pf.pack(fill="x", pady=(0, 8))

        tf = tk.Frame(pf, bg="#1e1e2e")
        tf.pack(side="left", padx=(0, 24))
        tk.Label(tf, text="色一致の閾値 (%)", fg="#aaa", bg="#1e1e2e",
                 font=("Meiryo", 9)).pack(anchor="w")
        tr = tk.Frame(tf, bg="#1e1e2e")
        tr.pack()
        self.threshold_var = tk.DoubleVar(value=10.0)
        ttk.Scale(tr, from_=1, to=50, variable=self.threshold_var,
                  orient="horizontal", length=160,
                  command=self._on_threshold_change).pack(side="left")
        self.threshold_disp = tk.Label(tr, text="10.0%", fg="white",
                                       bg="#1e1e2e", font=("Meiryo", 9), width=6)
        self.threshold_disp.pack(side="left", padx=(4, 0))

        df = tk.Frame(pf, bg="#1e1e2e")
        df.pack(side="left")
        tk.Label(df, text="検知後の待機時間 (秒)", fg="#aaa", bg="#1e1e2e",
                 font=("Meiryo", 9)).pack(anchor="w")
        self.wait_var = tk.StringVar(value="3")
        tk.Spinbox(df, from_=0, to=3600, textvariable=self.wait_var,
                   width=6, font=("Meiryo", 10),
                   bg="#2a2a3e", fg="white", insertbackground="white",
                   buttonbackground="#3a3a5c").pack(anchor="w")

        # セクション5: 状態
        self._section(main, "📊  状態")
        sf2 = tk.Frame(main, bg="#1e1e2e")
        sf2.pack(fill="x", pady=(0, 8))
        self.status_label = tk.Label(sf2, text="●  停止中", fg="#888",
                                     bg="#2a2a3e", font=("Meiryo", 11, "bold"),
                                     relief="sunken", padx=10, pady=4)
        self.status_label.pack(side="left", padx=(0, 10))
        self.color_preview = tk.Label(sf2, text="現在色: ─",
                                      fg="#aaa", bg="#1e1e2e", font=("Meiryo", 9))
        self.color_preview.pack(side="left")
        self.cur_color_canvas = tk.Canvas(sf2, width=28, height=20,
                                          bg="#555", relief="sunken", bd=1)
        self.cur_color_canvas.pack(side="left", padx=(4, 0))

        # 操作ボタン
        bf = tk.Frame(self.frame, bg="#12122a", pady=8)
        bf.pack(fill="x")
        self.start_btn = tk.Button(bf, text="▶  監視開始",
                                   command=self._start_monitor,
                                   bg="#007acc", fg="white",
                                   font=("Meiryo", 11, "bold"),
                                   relief="flat", padx=20, pady=6, cursor="hand2")
        self.start_btn.pack(side="left", padx=(16, 8))
        self.stop_btn = tk.Button(bf, text="■  停止",
                                  command=self._stop_monitor,
                                  bg="#555", fg="#aaa",
                                  font=("Meiryo", 11, "bold"),
                                  relief="flat", padx=20, pady=6,
                                  cursor="hand2", state="disabled")
        self.stop_btn.pack(side="left")

        self._update_color_preview()

    def _section(self, parent, title):
        f = tk.Frame(parent, bg="#1e1e2e")
        f.pack(fill="x", pady=(8, 2))
        tk.Label(f, text=title, fg="#a0d0ff", bg="#1e1e2e",
                 font=("Meiryo", 10, "bold")).pack(side="left")
        tk.Frame(f, bg="#3a3a5c", height=1).pack(
            side="left", fill="x", expand=True, padx=(6, 0))

    # ── ウィンドウ選択 ────────────────────────────────────────────────────────

    def _refresh_windows(self, match_title=None):
        wins = _get_all_windows()
        self._windows_list = wins
        self.win_combo["values"] = [f"{hwnd}  │  {t[:60]}" for hwnd, t in wins]
        if match_title:
            for i, (_, t) in enumerate(wins):
                if match_title in t or t in match_title:
                    self.win_combo.current(i)
                    self._on_window_select(None)
                    return
        if wins:
            self.win_combo.current(0)
            self._on_window_select(None)

    def _on_window_select(self, _):
        idx = self.win_combo.current()
        if 0 <= idx < len(self._windows_list):
            self.selected_hwnd, _ = self._windows_list[idx]

    # ── 領域選択（ウィンドウ相対座標で保存） ─────────────────────────────────

    def _pick_region(self):
        toplevel = self.frame.winfo_toplevel()
        toplevel.iconify()
        self.frame.after(300, lambda: _RegionSelector(toplevel, self._on_region_selected))

    def _on_region_selected(self, abs_region):
        """スクリーン絶対座標 → ウィンドウ相対座標に変換して保存"""
        self.frame.winfo_toplevel().deiconify()
        ax1, ay1, ax2, ay2 = abs_region
        w, h = ax2 - ax1, ay2 - ay1
        if self.selected_hwnd:
            try:
                wx, wy, _, _ = win32gui.GetWindowRect(self.selected_hwnd)
                rx1, ry1 = ax1 - wx, ay1 - wy
                self.region = (rx1, ry1, rx1 + w, ry1 + h)
                self.region_label.config(
                    text=f"相対座標 ({rx1}, {ry1})  サイズ {w}×{h}", fg="white")
                return
            except Exception:
                pass
        # hwnd 取得失敗時は絶対座標で保存（黄色で警告）
        self.region = abs_region
        self.region_label.config(
            text=f"絶対座標 ({ax1},{ay1})→({ax2},{ay2})", fg="#ffaa44")

    # ── 色選択 ────────────────────────────────────────────────────────────────

    def _pick_color(self, which):
        toplevel = self.frame.winfo_toplevel()
        toplevel.iconify()
        self.frame.after(300, lambda: _ColorPickerOverlay(
            toplevel, lambda c: self._on_color_picked(which, c)))

    def _on_color_picked(self, which, color):
        self.frame.winfo_toplevel().deiconify()
        self._set_color(which, color)

    def _pick_color_dialog(self, which):
        initial = _rgb_to_hex(self.start_color if which == "start" else self.end_color or (0, 0, 0))
        result = colorchooser.askcolor(color=initial, title="色を選択")
        if result and result[0]:
            self._set_color(which, tuple(int(v) for v in result[0]))

    def _set_color(self, which, color):
        hex_c = _rgb_to_hex(color)
        if which == "start":
            self.start_color = color
            self.start_canvas.configure(bg=hex_c)
            self.start_label.configure(text=hex_c, fg="white")
        else:
            self.end_color = color
            self.end_canvas.configure(bg=hex_c)
            self.end_label.configure(text=hex_c, fg="white")

    def _on_threshold_change(self, _):
        self.threshold_disp.config(text=f"{round(self.threshold_var.get(), 1)}%")

    # ── 監視制御 ──────────────────────────────────────────────────────────────

    def _start_monitor(self):
        if not self.region:
            messagebox.showwarning("設定不足", "監視領域を設定してください", parent=self.frame)
            return
        if not self.start_color:
            messagebox.showwarning("設定不足", "開始色を設定してください", parent=self.frame)
            return
        if not self.end_color:
            messagebox.showwarning("設定不足", "終了色を設定してください", parent=self.frame)
            return
        try:
            wait_sec = float(self.wait_var.get())
        except ValueError:
            wait_sec = 3.0

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.stop()

        self._monitor_thread = _MonitorThread(
            {"region": self.region, "hwnd": self.selected_hwnd,
             "start_color": self.start_color, "end_color": self.end_color,
             "threshold": self.threshold_var.get(), "wait_sec": wait_sec},
            lambda: self.frame.after(0, self._show_alert)
        )
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

    def _show_alert(self):
        _AlertWindow(self.frame.winfo_toplevel())

    # ── 設定保存・読み込み ────────────────────────────────────────────────────

    def save_settings(self):
        win_title = None
        idx = self.win_combo.current()
        if 0 <= idx < len(self._windows_list):
            _, win_title = self._windows_list[idx]
        data = {
            "window_title": win_title,
            "start_color":  list(self.start_color) if self.start_color else None,
            "end_color":    list(self.end_color)   if self.end_color   else None,
            "region":       list(self.region)      if self.region      else None,
            "threshold":    self.threshold_var.get(),
            "wait_sec":     self.wait_var.get(),
        }
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            return
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return

        if data.get("start_color"):
            self._set_color("start", tuple(data["start_color"]))
        if data.get("end_color"):
            self._set_color("end", tuple(data["end_color"]))
        if data.get("threshold") is not None:
            self.threshold_var.set(data["threshold"])
            self._on_threshold_change(None)
        if data.get("wait_sec") is not None:
            self.wait_var.set(str(data["wait_sec"]))
        if data.get("region"):
            r = tuple(data["region"])
            self.region = r
            rx1, ry1, rx2, ry2 = r
            self.region_label.config(
                text=f"相対座標 ({rx1}, {ry1})  サイズ {rx2-rx1}×{ry2-ry1}",
                fg="white")
        if data.get("window_title"):
            self._refresh_windows(match_title=data["window_title"])

    # ── 現在色プレビュー ──────────────────────────────────────────────────────

    def _update_color_preview(self):
        if (self.region and self.selected_hwnd
                and self._monitor_thread and self._monitor_thread.is_alive()):
            abs_region = _resolve_region(self.region, self.selected_hwnd)
            if abs_region:
                avg = _get_region_avg_color(abs_region)
                if avg:
                    hex_c = _rgb_to_hex(avg)
                    self.color_preview.config(text=f"現在色: {hex_c}")
                    self.cur_color_canvas.configure(bg=hex_c)
        self.frame.after(500, self._update_color_preview)
