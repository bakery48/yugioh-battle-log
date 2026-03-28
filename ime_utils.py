"""
Suppress the Windows IME candidate popup (テキスト候補 / 変換候補).

Why window-subclassing failed
------------------------------
Tk routes WM_IME_* messages through an internal "focus proxy" HWND rather
than directly to individual child widgets.  There is no single, stable HWND
we can subclass to catch every relevant WM_IME_SETCONTEXT call.

Solution: thread-local WH_CALLWNDPROC hook
-------------------------------------------
SetWindowsHookExW(WH_CALLWNDPROC, ..., threadId) installs a hook that is
called for *every* SendMessage on the current thread, before the target
window proc runs.  The hook receives a writable CWPSTRUCT pointer, so we
can clear ISC_SHOWUIALLCANDIDATEWINDOW in lParam and the window proc will
see the modified value — effectively preventing all candidate windows from
being drawn, for every widget in the application.

Call ``install_ime_hook()`` once, at application startup.
No-op on non-Windows platforms.
"""

import sys

_hook_handle = None   # raw integer HHOOK (kept to pass to CallNextHookEx)
_hook_cb     = None   # HOOKPROC object — must stay alive for the process lifetime


def install_ime_hook() -> None:
    """
    Install a thread-local WH_CALLWNDPROC hook that suppresses the IME
    candidate window for every window on the calling thread.

    Call once from ``main.py`` after ``tk.Tk()`` is created.
    """
    global _hook_handle, _hook_cb

    if sys.platform != "win32" or _hook_handle is not None:
        return

    import ctypes
    import ctypes.wintypes as wt

    WH_CALLWNDPROC               = 4
    HC_ACTION                    = 0
    WM_IME_SETCONTEXT            = 0x0281
    ISC_SHOWUIALLCANDIDATEWINDOW = 0x0000000F   # bits 0-3: 4 candidate panels

    # CWPSTRUCT — the writable message info passed to WH_CALLWNDPROC hooks
    class CWPSTRUCT(ctypes.Structure):
        _fields_ = [
            ("lParam",  wt.LPARAM),
            ("wParam",  wt.WPARAM),
            ("message", wt.UINT),
            ("hwnd",    wt.HWND),
        ]

    HOOKPROC = ctypes.WINFUNCTYPE(
        ctypes.c_longlong,
        ctypes.c_int,   # nCode
        wt.WPARAM,      # wParam
        wt.LPARAM,      # lParam  (pointer to CWPSTRUCT)
    )

    u32 = ctypes.windll.user32
    u32.CallNextHookEx.restype    = ctypes.c_longlong
    u32.CallNextHookEx.argtypes   = [
        ctypes.c_void_p, ctypes.c_int, wt.WPARAM, wt.LPARAM,
    ]
    u32.SetWindowsHookExW.restype  = ctypes.c_void_p
    u32.SetWindowsHookExW.argtypes = [
        ctypes.c_int, ctypes.c_void_p, wt.HINSTANCE, wt.DWORD,
    ]
    u32.GetCurrentThreadId.restype  = wt.DWORD
    u32.GetCurrentThreadId.argtypes = []

    def _hook(nCode: int, wParam: int, lParam: int) -> int:
        if nCode == HC_ACTION:
            cwp = ctypes.cast(lParam, ctypes.POINTER(CWPSTRUCT)).contents
            if cwp.message == WM_IME_SETCONTEXT:
                # Clear candidate-window bits; keep composition window bit
                cwp.lParam &= ~ISC_SHOWUIALLCANDIDATEWINDOW
        return u32.CallNextHookEx(_hook_handle, nCode, wParam, lParam)

    _hook_cb = HOOKPROC(_hook)
    cb_addr  = ctypes.cast(_hook_cb, ctypes.c_void_p).value or 0

    _hook_handle = u32.SetWindowsHookExW(
        WH_CALLWNDPROC,
        cb_addr,
        None,                          # hMod = NULL for same-process hook
        u32.GetCurrentThreadId(),
    )


# ---------------------------------------------------------------------------
# Back-compat shim: old callers used suppress_ime_popup(widget).
# Now a no-op because the thread hook covers every window automatically.
# ---------------------------------------------------------------------------
def suppress_ime_popup(widget) -> None:  # noqa: ARG001
    pass
