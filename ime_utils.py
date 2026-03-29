"""
Windows IME composition font fix.

ウィジェットの実際のフォントを tkinter のフォントシステムから読み取り、
ImmSetCompositionFontW に渡すことで変換前後のフォント不一致を解消する。
CTk の DPI スケーリングにも追従する。
"""

import sys


def fix_entry_ime_font(widget) -> None:
    """
    Read the widget's actual rendered font via tkinter's font API and
    pass it to ImmSetCompositionFontW.

    Usage in main.py:
        for cls in ("TEntry", "Entry"):
            root.bind_class(cls, "<FocusIn>",
                            lambda e: fix_entry_ime_font(e.widget), add="+")
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        import ctypes.wintypes as wt
        import tkinter.font as tkfont

        # ── Read actual font from the widget ──────────────────────────────────
        family   = "Meiryo"
        size_pt  = 10
        size_px  = None          # set if size is already in pixels (negative)
        try:
            font_spec = widget.cget("font")
            if font_spec:
                f = tkfont.Font(font=font_spec)
                actual = f.actual()
                fam = actual.get("family", "")
                if fam:
                    family = fam
                sz = actual.get("size", 10)
                if sz > 0:       # positive → logical points
                    size_pt = sz
                elif sz < 0:     # negative → pixels
                    size_px = sz  # use directly as lfHeight
        except Exception:
            pass

        # ── Build LOGFONT ─────────────────────────────────────────────────────
        class LOGFONT(ctypes.Structure):
            _fields_ = [
                ("lfHeight",         wt.LONG),
                ("lfWidth",          wt.LONG),
                ("lfEscapement",     wt.LONG),
                ("lfOrientation",    wt.LONG),
                ("lfWeight",         wt.LONG),
                ("lfItalic",         ctypes.c_byte),
                ("lfUnderline",      ctypes.c_byte),
                ("lfStrikeOut",      ctypes.c_byte),
                ("lfCharSet",        ctypes.c_byte),
                ("lfOutPrecision",   ctypes.c_byte),
                ("lfClipPrecision",  ctypes.c_byte),
                ("lfQuality",        ctypes.c_byte),
                ("lfPitchAndFamily", ctypes.c_byte),
                ("lfFaceName",       ctypes.c_wchar * 32),
            ]

        u32   = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        imm32 = ctypes.windll.imm32

        hwnd = wt.HWND(widget.winfo_id())

        if size_px is not None:
            lf_height = size_px          # already pixels, already negative
        else:
            hdc = u32.GetDC(hwnd)
            dpi = gdi32.GetDeviceCaps(hdc, 90)   # LOGPIXELSY
            u32.ReleaseDC(hwnd, hdc)
            lf_height = -int(size_pt * dpi / 72)

        lf = LOGFONT()
        lf.lfHeight   = lf_height
        lf.lfWeight   = 400   # FW_NORMAL
        lf.lfCharSet  = 128   # SHIFTJIS_CHARSET
        lf.lfQuality  = 5     # CLEARTYPE_QUALITY
        lf.lfFaceName = family

        himc = imm32.ImmGetContext(hwnd)
        if himc:
            imm32.ImmSetCompositionFontW(himc, ctypes.byref(lf))
            imm32.ImmReleaseContext(hwnd, himc)
    except Exception:
        pass
