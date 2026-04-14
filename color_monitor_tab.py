"""Color change monitor tab."""

import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
import threading
import time
import math
import json
import os
import customtkinter as ctk

SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "color_monitor", "settings.json")

try:
    from PIL import ImageGrab
    import win32gui
    _DEPS_OK = True
except ImportError:
    _DEPS_OK = False

_FONT      = ("Meiryo", 10)
_FONT_BOLD = ("Meiryo", 10, "bold")


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
        return ImageGrab.grab(bbox=(x, y, x + 1, y + 1),
                               all_screens=True).getpixel((0, 0))[:3]
    except Exception:
        return (0, 0, 0)


def _rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _virtual_screen_rect():
    """全モニターを包む仮想スクリーンの (x, y, width, height) を返す。"""
    try:
        import ctypes
        u32 = ctypes.windll.user32
        x = u32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
        y = u32.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
        w = u32.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
        h = u32.GetSystemMetrics(79)   # SM_CYVIRTUALSCREEN
        return x, y, w, h
    except Exception:
        return 0, 0, 1920, 1080


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
    def __init__(self, root, callback):
        self.callback = callback
        self.start_x = self.start_y = 0
        self.rect_id = None

        vx, vy, vw, vh = _virtual_screen_rect()
        self._vx = vx   # canvas座標 → スクリーン絶対座標へのオフセット
        self._vy = vy

        self.win = tk.Toplevel(root)
        # -fullscreen はプライマリモニターのみ。全モニターをカバーするため geometry を直接指定
        self.win.overrideredirect(True)
        self.win.attributes("-alpha", 0.35)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="black")
        self.win.geometry(f"{vw}x{vh}+{vx}+{vy}")

        self.canvas = tk.Canvas(self.win, cursor="cross", bg="black",
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        tk.Label(self.canvas,
                 text="ドラッグして監視領域を選択  /  ESCでキャンセル",
                 fg="white", bg="#333333", font=("Meiryo", 14), padx=10, pady=5
                 ).place(relx=0.5, rely=0.02, anchor="n")

        self.canvas.bind("<ButtonPress-1>",   self._on_press)
        self.canvas.bind("<B1-Motion>",        self._on_drag)
        self.canvas.bind("<ButtonRelease-1>",  self._on_release)
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
            # canvas座標はウィンドウ左上相対なので、仮想スクリーン原点を加算して絶対座標へ
            self.callback((x1 + self._vx, y1 + self._vy,
                           x2 + self._vx, y2 + self._vy))


# ─── ColorPickerOverlay ───────────────────────────────────────────────────────

class _ColorPickerOverlay:
    def __init__(self, root, callback):
        self.callback = callback
        vx, vy, vw, vh = _virtual_screen_rect()
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-alpha", 0.01)
        self.win.attributes("-topmost", True)
        self.win.configure(cursor="crosshair")
        self.win.geometry(f"{vw}x{vh}+{vx}+{vy}")
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
                                font=("Meiryo", max(30, w // 14), "bold"),
                                anchor="center")
        self.canvas.create_text(w // 2, int(h * 0.65),
                                text="クリックして閉じる", fill="#ffdddd",
                                font=("Meiryo", max(14, w // 32)),
                                anchor="center")
        self.win.bind("<Button-1>", lambda e: self._close())
        self.win.bind("<Escape>",   lambda e: self._close())

        self._colors = ["#ff2222", "#cc0000", "#ff4444", "#aa0000"]
        self._idx    = 0
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
        self.config         = config
        self.alert_callback = alert_callback
        self._stop_event    = threading.Event()
        self._state         = "WAIT_START"
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
        rel_region  = self.config["region"]
        hwnd        = self.config["hwnd"]
        start_color = self.config["start_color"]
        end_color   = self.config["end_color"]
        threshold   = self.config["threshold"]
        wait_sec    = self.config["wait_sec"]

        if not rel_region or not start_color or not end_color:
            return

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
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.pack(fill="both", expand=True)

        if not _DEPS_OK:
            ctk.CTkLabel(
                self.frame,
                text="Pillow と pywin32 が必要です。\npip install Pillow pywin32",
                text_color="red", justify="center", font=_FONT,
            ).pack(expand=True, pady=40)
            return

        self.region          = None
        self.start_color     = None
        self.end_color       = None
        self.selected_hwnd   = None
        self._windows_list   = []
        self._monitor_thread = None

        self._build_ui()
        self._load_settings()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = ctk.CTkFrame(self.frame, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=4, pady=4)

        _canvas = tk.Canvas(outer, highlightthickness=0)
        _vsb = ttk.Scrollbar(outer, orient="vertical", command=_canvas.yview)
        _canvas.configure(yscrollcommand=_vsb.set)
        _vsb.pack(side="right", fill="y")
        _canvas.pack(side="left", fill="both", expand=True)

        scroll = ctk.CTkFrame(_canvas, fg_color="transparent")
        _win = _canvas.create_window((0, 0), window=scroll, anchor="nw")
        scroll.bind("<Configure>",
                    lambda e: _canvas.configure(
                        scrollregion=_canvas.bbox("all")))
        _canvas.bind("<Configure>",
                     lambda e: _canvas.itemconfig(_win, width=e.width))
        _canvas.bind("<MouseWheel>",
                     lambda e: _canvas.yview_scroll(
                         int(-e.delta / 120), "units"))

        # ── ウィンドウ選択 ────────────────────────────────────────────────────
        wf = ctk.CTkFrame(scroll, border_width=1)
        wf.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(wf, text="監視対象ウィンドウ", font=_FONT_BOLD).pack(
            anchor="w", padx=8, pady=(4, 2))
        row = ctk.CTkFrame(wf, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(0, 6))
        self.win_combo = ctk.CTkComboBox(row, width=420, font=_FONT,
                                          dropdown_font=_FONT,
                                          command=self._on_window_select)
        self.win_combo.pack(side="left", padx=(0, 6))
        ctk.CTkButton(row, text="🔄 更新", command=self._refresh_windows,
                      width=80, font=_FONT).pack(side="left")
        self._refresh_windows()

        # ── 監視領域 ──────────────────────────────────────────────────────────
        rf = ctk.CTkFrame(scroll, border_width=1)
        rf.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(rf, text="監視領域  ※ウィンドウ内の相対座標",
                     font=_FONT_BOLD).pack(anchor="w", padx=8, pady=(4, 2))
        row2 = ctk.CTkFrame(rf, fg_color="transparent")
        row2.pack(fill="x", padx=8, pady=(0, 6))
        self.region_label = ctk.CTkLabel(row2, text="未設定",
                                          text_color="gray", width=280, font=_FONT,
                                          anchor="w")
        self.region_label.pack(side="left", padx=(0, 8))
        ctk.CTkButton(row2, text="🖱 ドラッグで選択",
                      command=self._pick_region, width=130,
                      font=_FONT).pack(side="left")

        # ── 色設定 ────────────────────────────────────────────────────────────
        cf = ctk.CTkFrame(scroll, border_width=1)
        cf.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(cf, text="色設定", font=_FONT_BOLD).pack(
            anchor="w", padx=8, pady=(4, 2))
        colors_row = ctk.CTkFrame(cf, fg_color="transparent")
        colors_row.pack(fill="x", padx=8, pady=(0, 6))

        for col, (which, label) in enumerate((("start", "開始色（変化前）"),
                                               ("end",   "終了色（変化後）"))):
            sf = ctk.CTkFrame(colors_row, border_width=1)
            sf.grid(row=0, column=col, padx=(0, 16), sticky="w")
            ctk.CTkLabel(sf, text=label, font=_FONT_BOLD).pack(
                anchor="w", padx=6, pady=(4, 2))
            top_row = ctk.CTkFrame(sf, fg_color="transparent")
            top_row.pack(anchor="w", padx=6)
            # tk.Canvas for actual color swatch (CTk doesn't support bg colors easily)
            canvas = tk.Canvas(top_row, width=36, height=24,
                               relief="sunken", bd=1)
            canvas.pack(side="left", padx=(0, 6))
            lbl = ctk.CTkLabel(top_row, text="未設定", width=80, font=_FONT)
            lbl.pack(side="left")
            if which == "start":
                self.start_canvas, self.start_label = canvas, lbl
            else:
                self.end_canvas,   self.end_label   = canvas, lbl
            btn_row2 = ctk.CTkFrame(sf, fg_color="transparent")
            btn_row2.pack(anchor="w", padx=6, pady=(4, 6))
            ctk.CTkButton(btn_row2, text="スクリーンから取得",
                          command=lambda w=which: self._pick_color(w),
                          width=140, font=_FONT).pack(side="left", padx=(0, 4))
            ctk.CTkButton(btn_row2, text="ダイアログ",
                          command=lambda w=which: self._pick_color_dialog(w),
                          width=90, font=_FONT).pack(side="left")

        # ── パラメータ ────────────────────────────────────────────────────────
        pf = ctk.CTkFrame(scroll, border_width=1)
        pf.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(pf, text="監視パラメータ", font=_FONT_BOLD).pack(
            anchor="w", padx=8, pady=(4, 2))
        param_row = ctk.CTkFrame(pf, fg_color="transparent")
        param_row.pack(fill="x", padx=8, pady=(0, 6))

        ctk.CTkLabel(param_row, text="色一致の閾値 (%):", font=_FONT).grid(
            row=0, column=0, sticky="w", padx=(0, 6))
        self.threshold_var = tk.DoubleVar(value=10.0)
        ctk.CTkSlider(param_row, from_=1, to=50, variable=self.threshold_var,
                      orientation="horizontal", width=180,
                      command=self._on_threshold_change).grid(row=0, column=1)
        self.threshold_disp = ctk.CTkLabel(param_row, text="10.0%", width=50,
                                            font=_FONT)
        self.threshold_disp.grid(row=0, column=2, padx=(6, 24))

        ctk.CTkLabel(param_row, text="検知後の待機時間 (秒):", font=_FONT).grid(
            row=0, column=3, sticky="w", padx=(0, 6))
        self.wait_var = tk.StringVar(value="3")
        ctk.CTkEntry(param_row, textvariable=self.wait_var, width=60,
                     font=_FONT).grid(row=0, column=4)

        # ── 状態 ──────────────────────────────────────────────────────────────
        sf2 = ctk.CTkFrame(scroll, border_width=1)
        sf2.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(sf2, text="状態", font=_FONT_BOLD).pack(
            anchor="w", padx=8, pady=(4, 2))
        row3 = ctk.CTkFrame(sf2, fg_color="transparent")
        row3.pack(fill="x", padx=8, pady=(0, 6))
        self.status_label = ctk.CTkLabel(row3, text="● 停止中",
                                          text_color="gray", width=90, font=_FONT)
        self.status_label.pack(side="left", padx=(0, 16))
        self.color_preview = ctk.CTkLabel(row3, text="現在色: ─", font=_FONT)
        self.color_preview.pack(side="left")
        self.cur_color_canvas = tk.Canvas(row3, width=28, height=20,
                                          relief="sunken", bd=1)
        self.cur_color_canvas.pack(side="left", padx=(6, 0))

        # ── 操作ボタン ────────────────────────────────────────────────────────
        bf = ctk.CTkFrame(scroll, fg_color="transparent")
        bf.pack(fill="x", pady=(4, 0))
        self.start_btn = ctk.CTkButton(bf, text="▶ 監視開始",
                                        command=self._start_monitor,
                                        width=110, font=_FONT)
        self.start_btn.pack(side="left", padx=(0, 8))
        self.stop_btn = ctk.CTkButton(bf, text="■ 停止",
                                       command=self._stop_monitor,
                                       width=80, font=_FONT, state="disabled")
        self.stop_btn.pack(side="left")

        self._update_color_preview()

    # ── ウィンドウ選択 ────────────────────────────────────────────────────────

    def _refresh_windows(self, match_title=None):
        wins = _get_all_windows()
        self._windows_list = wins
        values = [f"{hwnd}  │  {t[:60]}" for hwnd, t in wins]
        self.win_combo.configure(values=values)
        if match_title:
            for i, (_, t) in enumerate(wins):
                if match_title in t or t in match_title:
                    self.win_combo.set(values[i])
                    self._on_window_select(values[i])
                    return
        if values:
            self.win_combo.set(values[0])
            self._on_window_select(values[0])

    def _on_window_select(self, value):
        try:
            idx = [f"{hwnd}  │  {t[:60]}"
                   for hwnd, t in self._windows_list].index(value)
            self.selected_hwnd, _ = self._windows_list[idx]
        except (ValueError, IndexError):
            pass

    # ── 領域選択 ──────────────────────────────────────────────────────────────

    def _pick_region(self):
        toplevel = self.frame.winfo_toplevel()
        toplevel.iconify()
        self.frame.after(300, lambda: _RegionSelector(toplevel,
                                                       self._on_region_selected))

    def _on_region_selected(self, abs_region):
        self.frame.winfo_toplevel().deiconify()
        ax1, ay1, ax2, ay2 = abs_region
        w, h = ax2 - ax1, ay2 - ay1
        if self.selected_hwnd:
            try:
                wx, wy, _, _ = win32gui.GetWindowRect(self.selected_hwnd)
                rx1, ry1 = ax1 - wx, ay1 - wy
                self.region = (rx1, ry1, rx1 + w, ry1 + h)
                self.region_label.configure(
                    text=f"相対座標 ({rx1}, {ry1})  サイズ {w}×{h}",
                    text_color=ctk.ThemeManager.theme["CTkLabel"]["text_color"])
                return
            except Exception:
                pass
        self.region = abs_region
        self.region_label.configure(
            text=f"絶対座標 ({ax1},{ay1})→({ax2},{ay2})",
            text_color="orange")

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
        cur = self.start_color if which == "start" else self.end_color
        initial = _rgb_to_hex(cur) if cur else None
        result = colorchooser.askcolor(color=initial, title="色を選択")
        if result and result[0]:
            self._set_color(which, tuple(int(v) for v in result[0]))

    def _set_color(self, which, color):
        hex_c = _rgb_to_hex(color)
        if which == "start":
            self.start_color = color
            self.start_canvas.configure(bg=hex_c)
            self.start_label.configure(text=hex_c)
        else:
            self.end_color = color
            self.end_canvas.configure(bg=hex_c)
            self.end_label.configure(text=hex_c)

    def _on_threshold_change(self, _):
        self.threshold_disp.configure(
            text=f"{round(self.threshold_var.get(), 1)}%")

    # ── 監視制御 ──────────────────────────────────────────────────────────────

    def _start_monitor(self):
        if not self.region:
            messagebox.showwarning("設定不足", "監視領域を設定してください",
                                   parent=self.frame)
            return
        if not self.start_color:
            messagebox.showwarning("設定不足", "開始色を設定してください",
                                   parent=self.frame)
            return
        if not self.end_color:
            messagebox.showwarning("設定不足", "終了色を設定してください",
                                   parent=self.frame)
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
            lambda: self.frame.after(0, self._show_alert),
        )
        self._monitor_thread.start()
        self.status_label.configure(text="● 監視中", text_color="green")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")

    def _stop_monitor(self):
        if self._monitor_thread:
            self._monitor_thread.stop()
        self.status_label.configure(text="● 停止中", text_color="gray")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")

    def _show_alert(self):
        _AlertWindow(self.frame.winfo_toplevel())

    # ── 設定保存・読み込み ────────────────────────────────────────────────────

    def save_settings(self):
        win_title = None
        val = self.win_combo.get()
        for hwnd, t in self._windows_list:
            if val.startswith(str(hwnd)):
                win_title = t
                break
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
                import json
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            return
        try:
            import json
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
            self.region_label.configure(
                text=f"相対座標 ({rx1}, {ry1})  サイズ {rx2-rx1}×{ry2-ry1}")
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
                    self.color_preview.configure(text=f"現在色: {hex_c}")
                    self.cur_color_canvas.configure(bg=hex_c)
        self.frame.after(500, self._update_color_preview)
