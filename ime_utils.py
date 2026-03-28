"""
Suppress Windows 11 IME prediction popup (テキスト候補) while keeping the
kanji candidate list functional.

Root cause of previous failures
---------------------------------
ATTR_CONVERTED (0x02) is set on kana characters that were produced by
romaji-to-kana conversion (e.g. "sa" → "さ").  We were treating this as
"kanji conversion mode" and skipping suppression — so the prediction popup
was never closed.

ATTR_TARGET_CONVERTED (0x01) is the *only* attribute that means "kanji
candidate window is open and this character is the actively selected
candidate."  We must check ONLY for that.

Strategy
---------
WH_CALLWNDPROC hook, per-thread:

  1. WM_IME_SETCONTEXT   → clear ISC_SHOWUIALLCANDIDATEWINDOW bits.
  2. WM_IME_NOTIFY / IMN_OPENCANDIDATE or IMN_CHANGECANDIDATE:
       • Check composition attributes for ATTR_TARGET_CONVERTED ONLY.
       • If absent (prediction / plain kana):
           – Null the message so the window proc ignores it.
           – After CallNextHookEx, call ImmNotifyIME(NI_CLOSECANDIDATE)
             to explicitly close the popup the IME server already opened.
       • If present (kanji candidate selection): leave untouched.

A _suppressing flag prevents the resulting IMN_CLOSECANDIDATE from
triggering a re-entrant call.

No-op on non-Windows platforms.
"""

import sys

_hook_handle = None   # integer HHOOK
_hook_cb     = None   # HOOKPROC — must stay alive for the process lifetime


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
    # ONLY this attribute means the kanji candidate list is actively open
    # and the character is being selected from the list.
    # ATTR_CONVERTED (0x02) is also set for romaji→kana conversion — do NOT
    # use it to decide "kanji mode", or we will never suppress predictions.
    ATTR_TARGET_CONVERTED        = 0x01

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

    # ── DLL handles ───────────────────────────────────────────────────────────
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
    def _in_kanji_selection(himc) -> bool:
        """
        Return True ONLY when the user has pressed Space and the kanji
        candidate list is showing (ATTR_TARGET_CONVERTED present).

        Return False for:
          • plain kana input       (ATTR_INPUT 0x00)
          • romaji→kana conversion (ATTR_CONVERTED 0x02)
          • prediction popup       (ATTR_INPUT 0x00)
          • empty composition
        """
        try:
            n = imm32.ImmGetCompositionStringW(himc, GCS_COMPATTR, None, 0)
            if n <= 0:
                return False
            buf = (ctypes.c_ubyte * n)()
            imm32.ImmGetCompositionStringW(himc, GCS_COMPATTR, buf, n)
            return any(b == ATTR_TARGET_CONVERTED for b in buf)
        except Exception:
            return True   # safe default: don't suppress on error

    # ── Hook procedure ────────────────────────────────────────────────────────
    def _hook(nCode: int, wParam: int, lParam: int) -> int:
        close_info = None   # (himc, hwnd, lp_bitmask) – close after next-hook

        if nCode == HC_ACTION:
            cwp = ctypes.cast(lParam, ctypes.POINTER(CWPSTRUCT)).contents

            if cwp.message == WM_IME_SETCONTEXT:
                # Tell the IME not to show its default candidate UI on focus.
                cwp.lParam &= ~ISC_SHOWUIALLCANDIDATEWINDOW

            elif (cwp.message == WM_IME_NOTIFY
                  and cwp.wParam in (IMN_OPENCANDIDATE, IMN_CHANGECANDIDATE)
                  and not _suppressing[0]):
                himc = imm32.ImmGetContext(cwp.hwnd)
                if himc:
                    in_kanji = _in_kanji_selection(himc)
                    if not in_kanji:
                        # Prediction / plain-kana phase:
                        # null the notification AND schedule ImmNotifyIME to
                        # close the popup the IME server already opened.
                        close_info = (himc, cwp.hwnd, cwp.lParam)
                        cwp.message = WM_NULL
                    else:
                        # Kanji candidate selection – leave alone.
                        imm32.ImmReleaseContext(cwp.hwnd, himc)

        result = u32.CallNextHookEx(_hook_handle, nCode, wParam, lParam)

        # Actively close the prediction popup after the window proc returns.
        if close_info is not None:
            himc, hwnd, bitmask = close_info
            _suppressing[0] = True
            try:
                # Close each candidate list indicated by the bitmask.
                closed_any = False
                for i in range(4):
                    if bitmask & (1 << i):
                        imm32.ImmNotifyIME(himc, NI_CLOSECANDIDATE, i, 0)
                        closed_any = True
                if not closed_any:
                    # bitmask was 0 – try closing list 0 as a fallback.
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
        None,                           # hMod = NULL (same-process, per-thread)
        k32.GetCurrentThreadId(),
    )


def suppress_ime_popup(widget) -> None:   # noqa: ARG001
    """Back-compat shim – no longer needed."""
    pass
