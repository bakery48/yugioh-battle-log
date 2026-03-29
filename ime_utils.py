"""
Windows IME composition font fix.

HWND の DC から現在の GDI フォントを読み取り、そのまま IME 合成フォントに
セットすることで、変換前（確定前）と変換後でフォントが変わる問題を解消する。
フォント名・サイズをハードコードしないため CTk のスケーリングにも対応。
"""

import sys


def fix_entry_ime_font(hwnd_id: int) -> None:
    """
    Read the widget's actual GDI font from its DC and pass it to
    ImmSetCompositionFontW, ensuring pre/post-confirmation text look identical.

    Usage in main.py:
        for cls in ("TEntry", "Entry"):
            root.bind_class(cls, "<FocusIn>",
                            lambda e: fix_entry_ime_font(e.widget.winfo_id()),
                            add="+")
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        import ctypes.wintypes as wt

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

        OBJ_FONT = 6
        hwnd = wt.HWND(hwnd_id)
        hdc  = u32.GetDC(hwnd)

        # Read the font currently selected in the widget's DC —
        # this automatically reflects CTk's DPI/widget scaling.
        hfont = gdi32.GetCurrentObject(hdc, OBJ_FONT)
        lf = LOGFONT()
        gdi32.GetObjectW(hfont, ctypes.sizeof(lf), ctypes.byref(lf))
        u32.ReleaseDC(hwnd, hdc)

        # Ensure Japanese glyphs render correctly in the composition window.
        lf.lfCharSet = 128  # SHIFTJIS_CHARSET

        himc = imm32.ImmGetContext(hwnd)
        if himc:
            imm32.ImmSetCompositionFontW(himc, ctypes.byref(lf))
            imm32.ImmReleaseContext(hwnd, himc)
    except Exception:
        pass
