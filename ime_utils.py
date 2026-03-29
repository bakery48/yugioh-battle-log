"""
Windows IME composition font fix.

ImmSetCompositionFontW を Entry の FocusIn 時に呼ぶことで、
変換前（確定前）と変換後でフォントが変わる問題を解消する。
"""

import sys


def fix_entry_ime_font(hwnd_id: int,
                       font_name: str = "Meiryo",
                       point_size: int = 10) -> None:
    """
    Call ImmSetCompositionFontW so the IME composition (pre-confirmation)
    string is rendered in the same font as confirmed text.

    Usage in main.py:
        root.bind_class("TEntry", "<FocusIn>",
                        lambda e: fix_entry_ime_font(e.widget.winfo_id()), add="+")
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
        hwnd  = wt.HWND(hwnd_id)
        hdc   = u32.GetDC(hwnd)
        dpi   = gdi32.GetDeviceCaps(hdc, 90)  # LOGPIXELSY
        u32.ReleaseDC(hwnd, hdc)

        lf = LOGFONT()
        lf.lfHeight   = -int(point_size * dpi / 72)
        lf.lfWeight   = 400   # FW_NORMAL
        lf.lfCharSet  = 128   # SHIFTJIS_CHARSET
        lf.lfQuality  = 5     # CLEARTYPE_QUALITY
        lf.lfFaceName = font_name

        himc = imm32.ImmGetContext(hwnd)
        if himc:
            imm32.ImmSetCompositionFontW(himc, ctypes.byref(lf))
            imm32.ImmReleaseContext(hwnd, himc)
    except Exception:
        pass
