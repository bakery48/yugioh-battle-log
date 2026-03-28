"""
Suppress the Windows 11 IME candidate popup (テキスト候補 / 変換候補).

Why the previous approach failed
---------------------------------
* Tk on Windows routes ALL WM_IME_* messages through the *Toplevel* window
  procedure, not through individual child widget (Entry) HWNDs.
* Child widgets do NOT fire the <Map> virtual event on Windows, so the
  <Map>-based deferred install was never called.
* The WINFUNCTYPE object was passed where c_ssize_t (LONG_PTR) was expected
  without an explicit address cast, silently passing garbage.

Fix
---
1. Call ``suppress_ime_popup(toplevel)`` once per dialog / root window.
2. Subclass the Toplevel HWND immediately (no <Map> needed; Win32 HWNDs are
   synchronously created when Tk widgets are instantiated).
3. In the new WNDPROC, intercept WM_IME_SETCONTEXT and clear the
   ISC_SHOWUIALLCANDIDATEWINDOW bits before forwarding to Tk.
4. Use explicit ``ctypes.cast(cb, ctypes.c_void_p).value`` to obtain the
   raw function-pointer integer required by SetWindowLongPtrW.

No-op on non-Windows platforms.
"""

import sys
from typing import Any

# hwnd -> {"cb": WNDPROC callback, "old": int}  — keeps callbacks alive
_registry: dict[int, dict[str, Any]] = {}


def suppress_ime_popup(widget) -> None:
    """
    Suppress the IME candidate popup for the Toplevel that owns *widget*.

    Recommended usage – call once per dialog::

        self.top = tk.Toplevel(parent)
        ...
        suppress_ime_popup(self.top)

    Safe to call multiple times on the same window (idempotent).
    """
    if sys.platform != "win32":
        return

    import ctypes
    import ctypes.wintypes as wt

    WM_IME_SETCONTEXT            = 0x0281
    ISC_SHOWUIALLCANDIDATEWINDOW = 0x0000000F   # bits 0-3
    GWLP_WNDPROC                 = -4

    u32 = ctypes.windll.user32
    # LONG_PTR = c_ssize_t (pointer-width signed int, 64-bit on Win64)
    _LP = ctypes.c_ssize_t
    u32.SetWindowLongPtrW.restype  = _LP
    u32.SetWindowLongPtrW.argtypes = [wt.HWND, ctypes.c_int, _LP]
    u32.CallWindowProcW.restype    = _LP
    u32.CallWindowProcW.argtypes   = [_LP, wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
    u32.DefWindowProcW.restype     = _LP
    u32.DefWindowProcW.argtypes    = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]

    WNDPROC = ctypes.WINFUNCTYPE(_LP, wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM)

    def _install() -> None:
        try:
            # Always target the enclosing Toplevel / Tk root
            tl   = widget.winfo_toplevel()
            hwnd = tl.winfo_id()
        except Exception:
            return

        if not hwnd or hwnd in _registry:
            return

        def _proc(h: int, msg: int, wp: int, lp: int) -> int:
            rec = _registry.get(h)
            if rec is None:
                return u32.DefWindowProcW(h, msg, wp, lp)
            if msg == WM_IME_SETCONTEXT:
                lp &= ~ISC_SHOWUIALLCANDIDATEWINDOW
            return u32.CallWindowProcW(rec["old"], h, msg, wp, lp)

        cb = WNDPROC(_proc)
        # CRITICAL: cast the WINFUNCTYPE object to a raw void-pointer integer.
        # Passing the object directly when argtypes expects c_ssize_t would
        # silently truncate / corrupt the value on 64-bit Windows.
        cb_addr = ctypes.cast(cb, ctypes.c_void_p).value or 0

        old = int(u32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, _LP(cb_addr)))
        _registry[hwnd] = {"cb": cb, "old": old}

    # Win32 HWNDs are created synchronously — install right away.
    _install()
    # Belt-and-suspenders: retry after Tk has fully initialised the window.
    try:
        widget.after(0, _install)
    except Exception:
        pass
