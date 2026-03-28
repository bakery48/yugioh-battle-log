"""
Windows IME utility – suppress the テキスト候補 (text-prediction) popup.

The popup is driven by WM_IME_SETCONTEXT.  We subclass the native window
procedure of each Entry widget, intercept that message, and clear the
ISC_SHOWUIALLCANDIDATEWINDOW bits so that the prediction/candidate UI is
never drawn.  The inline composition window (where the user sees the kana
being typed) is unaffected, and the regular kanji-candidate list that appears
when the user presses Space is preserved because the DefaultIME window proc
still handles candidate display through ImmAssociateContextEx.

No-op on non-Windows platforms.
"""

import sys

_registry: dict = {}   # hwnd -> {"cb": WNDPROC, "old": int}  (prevent GC)


def suppress_ime_popup(widget) -> None:
    """
    Suppress the IME text-prediction popup for a tkinter Entry (or Text)
    widget.  Call right after widget creation.
    """
    if sys.platform != "win32":
        return

    import ctypes
    import ctypes.wintypes as wt

    WM_IME_SETCONTEXT         = 0x0281
    ISC_SHOWUIALLCANDIDATEWINDOW = 0x0000000F   # bits 0-3
    GWLP_WNDPROC              = -4

    user32 = ctypes.windll.user32
    # Need 64-bit-safe signatures
    user32.SetWindowLongPtrW.restype  = ctypes.c_longlong
    user32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_longlong]
    user32.CallWindowProcW.restype    = ctypes.c_longlong
    user32.CallWindowProcW.argtypes   = [
        ctypes.c_longlong, wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM,
    ]

    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_longlong,
        wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM,
    )

    def _install() -> None:
        try:
            hwnd = widget.winfo_id()
        except Exception:
            return
        if not hwnd or hwnd in _registry:
            return

        def _proc(h: int, msg: int, wp: int, lp: int) -> int:
            rec = _registry.get(h)
            old = rec["old"] if rec else 0
            if msg == WM_IME_SETCONTEXT:
                lp = lp & ~ISC_SHOWUIALLCANDIDATEWINDOW
            if old:
                return user32.CallWindowProcW(old, h, msg, wp, lp)
            return user32.DefWindowProcW(h, msg, wp, lp)

        cb = WNDPROC(_proc)
        old = user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, cb)
        _registry[hwnd] = {"cb": cb, "old": old}

    # The widget may not have an HWND yet if it hasn't been drawn.
    widget.bind("<Map>", lambda _e: _install(), add=True)
    if widget.winfo_ismapped():
        _install()
