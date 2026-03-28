"""
Suppress Windows IME prediction popup (テキスト候補) without breaking kanji conversion.

Root cause
-----------
WM_IME_NOTIFY / IMN_OPENCANDIDATE is a *notification* that the IME server has
already shown the candidate window.  Setting the message to WM_NULL in a
WH_CALLWNDPROC hook only prevents the *app's window procedure* from seeing it —
the popup is already visible.

Fix
----
In the WH_CALLWNDPROC hook, when we see IMN_OPENCANDIDATE while the composition
is NOT in kanji-convert mode (plain kana / text-prediction phase):

  1. Null the message (so the window proc stays unaware).
  2. After CallNextHookEx returns, call ImmNotifyIME(NI_CLOSECANDIDATE) to tell
     the IME server to close the popup it just opened.

A _suppressing flag prevents the resulting IMN_CLOSECANDIDATE notification from
triggering a re-entrant ImmNotifyIME call.

No-op on non-Windows platforms.
"""

import sys

_hook_handle = None   # integer HHOOK
_hook_cb     = None   # HOOKPROC — must live for the process lifetime


def install_ime_hook() -> None:
    """Install the thread-local hook.  Call once after tk.Tk() is created."""
    global _hook_handle, _hook_cb

    if sys.platform != "win32" or _hook_handle is not None:
        return

    import ctypes
    import ctypes.wintypes as wt

    # ── Constants ─────────────────────────────────────────────────────────────
    WH_CALLWNDPROC               = 4
    HC_ACTION                    = 0
    WM_NULL                      = 0x0000
    WM_IME_SETCONTEXT            = 0x0281
    WM_IME_NOTIFY                = 0x0282
    IMN_OPENCANDIDATE            = 0x0001
    IMN_CHANGECANDIDATE          = 0x0002
    ISC_SHOWUIALLCANDIDATEWINDOW = 0x0000000F
    NI_CLOSECANDIDATE            = 0x0011

    GCS_COMPATTR                 = 0x0010
    ATTR_TARGET_CONVERTED        = 0x01
    ATTR_CONVERTED               = 0x02

    # ── Structs ───────────────────────────────────────────────────────────────
    class CWPSTRUCT(ctypes.Structure):
        _fields_ = [
            ("lParam",  wt.LPARAM),
            ("wParam",  wt.WPARAM),
            ("message", wt.UINT),
            ("hwnd",    wt.HWND),
        ]

    HOOKPROC = ctypes.WINFUNCTYPE(
        ctypes.c_longlong,
        ctypes.c_int, wt.WPARAM, wt.LPARAM,
    )

    # ── DLL handles with correct signatures ───────────────────────────────────
    u32   = ctypes.windll.user32
    imm32 = ctypes.windll.imm32
    k32   = ctypes.windll.kernel32

    u32.CallNextHookEx.restype    = ctypes.c_longlong
    u32.CallNextHookEx.argtypes   = [
        ctypes.c_void_p, ctypes.c_int, wt.WPARAM, wt.LPARAM,
    ]
    u32.SetWindowsHookExW.restype  = ctypes.c_void_p
    u32.SetWindowsHookExW.argtypes = [
        ctypes.c_int, ctypes.c_void_p, wt.HINSTANCE, wt.DWORD,
    ]
    k32.GetCurrentThreadId.restype  = wt.DWORD
    k32.GetCurrentThreadId.argtypes = []

    imm32.ImmGetContext.restype    = ctypes.c_void_p
    imm32.ImmGetContext.argtypes   = [wt.HWND]
    imm32.ImmReleaseContext.restype  = ctypes.c_bool
    imm32.ImmReleaseContext.argtypes = [wt.HWND, ctypes.c_void_p]
    imm32.ImmGetCompositionStringW.restype  = ctypes.c_long
    imm32.ImmGetCompositionStringW.argtypes = [
        ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, wt.DWORD,
    ]
    imm32.ImmNotifyIME.restype  = ctypes.c_bool
    imm32.ImmNotifyIME.argtypes = [
        ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.DWORD,
    ]

    # ── Re-entrancy guard ─────────────────────────────────────────────────────
    _suppressing = [False]

    # ── Helper ────────────────────────────────────────────────────────────────
    def _is_converting(himc) -> bool:
        """
        Return True when the IME is in kanji-convert mode (user pressed Space).
        Return False during plain kana / text-prediction phase.
        """
        try:
            n = imm32.ImmGetCompositionStringW(himc, GCS_COMPATTR, None, 0)
            if n <= 0:
                return False
            buf = (ctypes.c_ubyte * n)()
            imm32.ImmGetCompositionStringW(himc, GCS_COMPATTR, buf, n)
            return any(b in (ATTR_TARGET_CONVERTED, ATTR_CONVERTED) for b in buf)
        except Exception:
            return True   # safe default: don't suppress on error

    # ── Hook procedure ────────────────────────────────────────────────────────
    def _hook(nCode: int, wParam: int, lParam: int) -> int:
        close_info = None   # (himc, hwnd, lp_bitmask) to close after next-hook

        if nCode == HC_ACTION:
            cwp = ctypes.cast(lParam, ctypes.POINTER(CWPSTRUCT)).contents

            if cwp.message == WM_IME_SETCONTEXT:
                # Clear candidate-window activation bits on focus-in
                cwp.lParam &= ~ISC_SHOWUIALLCANDIDATEWINDOW

            elif (cwp.message == WM_IME_NOTIFY
                  and cwp.wParam in (IMN_OPENCANDIDATE, IMN_CHANGECANDIDATE)
                  and not _suppressing[0]):
                himc = imm32.ImmGetContext(cwp.hwnd)
                if himc:
                    converting = _is_converting(himc)
                    if not converting:
                        # Text-prediction popup → null the notification and
                        # schedule ImmNotifyIME(NI_CLOSECANDIDATE) after
                        # CallNextHookEx so we close the already-visible popup.
                        close_info = (himc, cwp.hwnd, cwp.lParam)
                        cwp.message = WM_NULL
                    else:
                        imm32.ImmReleaseContext(cwp.hwnd, himc)

        result = u32.CallNextHookEx(_hook_handle, nCode, wParam, lParam)

        # Close the prediction popup that the IME server already opened.
        if close_info is not None:
            himc, hwnd, bitmask = close_info
            _suppressing[0] = True
            try:
                for i in range(4):
                    if bitmask & (1 << i):
                        imm32.ImmNotifyIME(himc, NI_CLOSECANDIDATE, i, 0)
                # Fallback: also close list 0 in case bitmask was 0
                if not bitmask:
                    imm32.ImmNotifyIME(himc, NI_CLOSECANDIDATE, 0, 0)
            finally:
                _suppressing[0] = False
                imm32.ImmReleaseContext(hwnd, himc)

        return result

    # ── Install ───────────────────────────────────────────────────────────────
    _hook_cb = HOOKPROC(_hook)
    cb_addr  = ctypes.cast(_hook_cb, ctypes.c_void_p).value or 0

    _hook_handle = u32.SetWindowsHookExW(
        WH_CALLWNDPROC,
        cb_addr,
        None,                         # hMod = NULL (same-process hook)
        k32.GetCurrentThreadId(),
    )


# Back-compat shim (kept so old call sites compile without error)
def suppress_ime_popup(widget) -> None:  # noqa: ARG001
    pass
