"""
Suppress Windows IME prediction popup (テキスト候補) without breaking kanji conversion.

Root cause of previous failures
---------------------------------
WM_IME_SETCONTEXT fires only when a window *gains focus*. The prediction
popup that appears while typing is opened by a different message:

    WM_IME_NOTIFY  wParam = IMN_OPENCANDIDATE (0x0001)

This is sent by the IME every time it wants to show or refresh the
floating candidate list.

Strategy
---------
Install a thread-local WH_CALLWNDPROC hook once at startup.  In the hook:

  1. WM_IME_SETCONTEXT  →  clear ISC_SHOWUIALLCANDIDATEWINDOW bits so
     the classic candidate window is never activated on focus-in.

  2. WM_IME_NOTIFY / IMN_OPENCANDIDATE or IMN_CHANGECANDIDATE
     →  check whether the composition string is in *kanji-convert mode*
        (ATTR_TARGET_CONVERTED / ATTR_CONVERTED set by ImmGetCompositionString).
     • If NOT converting  →  this is a text-prediction popup; suppress it
       by replacing the message with WM_NULL.
     • If converting      →  this is the normal kanji-candidate list the
       user triggered with Space; leave it alone.

Modifying the CWPSTRUCT pointed to by lParam in a WH_CALLWNDPROC hook
is defined behaviour: Windows reads the (possibly modified) struct when
it calls the window procedure.

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

    GCS_COMPATTR                 = 0x0010
    ATTR_TARGET_CONVERTED        = 0x01
    ATTR_CONVERTED               = 0x02

    # ── Struct ────────────────────────────────────────────────────────────────
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

    # ── Helper ────────────────────────────────────────────────────────────────
    def _is_converting(himc) -> bool:
        """
        Return True when the IME composition is in kanji-convert mode
        (user pressed Space).  Return False during plain kana input
        (text-prediction phase).
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
        if nCode == HC_ACTION:
            cwp = ctypes.cast(lParam, ctypes.POINTER(CWPSTRUCT)).contents

            if cwp.message == WM_IME_SETCONTEXT:
                # Clear candidate-window activation bits on focus-in
                cwp.lParam &= ~ISC_SHOWUIALLCANDIDATEWINDOW

            elif cwp.message == WM_IME_NOTIFY and cwp.wParam in (
                IMN_OPENCANDIDATE, IMN_CHANGECANDIDATE
            ):
                himc = imm32.ImmGetContext(cwp.hwnd)
                if himc:
                    converting = _is_converting(himc)
                    imm32.ImmReleaseContext(cwp.hwnd, himc)
                    if not converting:
                        # Prediction popup (kana-input phase) → swallow
                        cwp.message = WM_NULL

        return u32.CallNextHookEx(_hook_handle, nCode, wParam, lParam)

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
