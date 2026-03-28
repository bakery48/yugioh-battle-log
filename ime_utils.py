"""
Suppress the Windows 11 text-prediction popup (テキスト候補) for ALL input
(ASCII and Japanese) while keeping the kanji candidate list functional.

Root cause
-----------
The popup is a TSF (Text Services Framework) UI element, not a traditional
IME candidate window.  It fires for plain ASCII (".dfd") as well as kana.
WM_IME_NOTIFY / ImmNotifyIME have zero effect on it.

Fix
----
Implement ITfUIElementSink via ctypes COM and advise it with
ITfUIElementMgr::AdviseUIElementSink.

In BeginUIElement:
  • Check GCS_COMPATTR for ATTR_TARGET_CONVERTED (0x01) — the only attribute
    set when the kanji candidate list is open (user pressed Space).
  • If absent  → prediction / plain typing → set *pbShow = FALSE (suppress).
  • If present → kanji selection           → set *pbShow = TRUE  (allow).

The WH_CALLWNDPROC hook is kept as a belt-and-suspenders fallback that also
suppresses WM_IME_REQUEST / IMR_DOCUMENTFEED (denies surrounding-text context
to the prediction engine).
"""

import sys

_hook_handle = None
_hook_cb     = None
_tsf_refs    = None   # keeps every COM/ctypes object alive


# ─────────────────────────────────────────────────────────────────────────────
def install_ime_hook() -> None:
    """Call once after tk.Tk() is created."""
    if sys.platform != "win32":
        return
    _install_wh_hook()
    _install_tsf_sink()


# ─────────────────────────────────────────────────────────────────────────────
def _in_kanji_selection(imm32, himc) -> bool:
    """True only while the kanji candidate list is open (ATTR_TARGET_CONVERTED)."""
    import ctypes
    GCS_COMPATTR       = 0x0010
    ATTR_TARGET_CONV   = 0x01
    try:
        n = imm32.ImmGetCompositionStringW(himc, GCS_COMPATTR, None, 0)
        if n <= 0:
            return False
        buf = (ctypes.c_ubyte * n)()
        imm32.ImmGetCompositionStringW(himc, GCS_COMPATTR, buf, n)
        return any(b == ATTR_TARGET_CONV for b in buf)
    except Exception:
        return True   # safe: don't suppress on error


# ─────────────────────────────────────────────────────────────────────────────
def _install_wh_hook() -> None:
    global _hook_handle, _hook_cb
    if _hook_handle is not None:
        return
    import ctypes, ctypes.wintypes as wt

    WH_CALLWNDPROC               = 4
    HC_ACTION                    = 0
    WM_NULL                      = 0x0000
    WM_IME_SETCONTEXT            = 0x0281
    WM_IME_NOTIFY                = 0x0282
    WM_IME_REQUEST               = 0x0288
    IMN_OPENCANDIDATE            = 0x0001
    IMN_CHANGECANDIDATE          = 0x0002
    IMR_DOCUMENTFEED             = 7
    ISC_SHOWUIALLCANDIDATEWINDOW = 0x0000000F
    NI_CLOSECANDIDATE            = 0x0011

    class CWPSTRUCT(ctypes.Structure):
        _fields_ = [
            ("lParam",  wt.LPARAM),
            ("wParam",  wt.WPARAM),
            ("message", wt.UINT),
            ("hwnd",    wt.HWND),
        ]

    HOOKPROC = ctypes.WINFUNCTYPE(
        ctypes.c_longlong, ctypes.c_int, wt.WPARAM, wt.LPARAM,
    )

    u32   = ctypes.windll.user32
    imm32 = ctypes.windll.imm32
    k32   = ctypes.windll.kernel32

    u32.CallNextHookEx.restype    = ctypes.c_longlong
    u32.CallNextHookEx.argtypes   = [ctypes.c_void_p, ctypes.c_int, wt.WPARAM, wt.LPARAM]
    u32.SetWindowsHookExW.restype  = ctypes.c_void_p
    u32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wt.HINSTANCE, wt.DWORD]
    k32.GetCurrentThreadId.restype  = wt.DWORD
    k32.GetCurrentThreadId.argtypes = []
    imm32.ImmGetContext.restype    = ctypes.c_void_p
    imm32.ImmGetContext.argtypes   = [wt.HWND]
    imm32.ImmReleaseContext.restype  = ctypes.c_bool
    imm32.ImmReleaseContext.argtypes = [wt.HWND, ctypes.c_void_p]
    imm32.ImmGetCompositionStringW.restype  = ctypes.c_long
    imm32.ImmGetCompositionStringW.argtypes = [ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, wt.DWORD]
    imm32.ImmNotifyIME.restype  = ctypes.c_bool
    imm32.ImmNotifyIME.argtypes = [ctypes.c_void_p, wt.DWORD, wt.DWORD, wt.DWORD]

    _suppressing = [False]

    def _hook(nCode, wParam, lParam):
        close_info = None
        if nCode == HC_ACTION:
            cwp = ctypes.cast(lParam, ctypes.POINTER(CWPSTRUCT)).contents
            if cwp.message == WM_IME_SETCONTEXT:
                cwp.lParam &= ~ISC_SHOWUIALLCANDIDATEWINDOW
            elif (cwp.message == WM_IME_REQUEST and cwp.wParam == IMR_DOCUMENTFEED):
                # Deny surrounding-text context → prediction engine has nothing to work with
                cwp.message = WM_NULL
            elif (cwp.message == WM_IME_NOTIFY
                  and cwp.wParam in (IMN_OPENCANDIDATE, IMN_CHANGECANDIDATE)
                  and not _suppressing[0]):
                himc = imm32.ImmGetContext(cwp.hwnd)
                if himc:
                    if not _in_kanji_selection(imm32, himc):
                        close_info = (himc, cwp.hwnd, cwp.lParam)
                        cwp.message = WM_NULL
                    else:
                        imm32.ImmReleaseContext(cwp.hwnd, himc)

        result = u32.CallNextHookEx(_hook_handle, nCode, wParam, lParam)

        if close_info is not None:
            himc, hwnd, bitmask = close_info
            _suppressing[0] = True
            try:
                closed = False
                for i in range(4):
                    if bitmask & (1 << i):
                        imm32.ImmNotifyIME(himc, NI_CLOSECANDIDATE, i, 0)
                        closed = True
                if not closed:
                    imm32.ImmNotifyIME(himc, NI_CLOSECANDIDATE, 0, 0)
            finally:
                _suppressing[0] = False
                imm32.ImmReleaseContext(hwnd, himc)

        return result

    _hook_cb = HOOKPROC(_hook)
    cb_addr  = ctypes.cast(_hook_cb, ctypes.c_void_p).value or 0
    _hook_handle = u32.SetWindowsHookExW(
        WH_CALLWNDPROC, cb_addr, None, k32.GetCurrentThreadId()
    )


# ─────────────────────────────────────────────────────────────────────────────
def _install_tsf_sink() -> None:
    """
    Install ITfUIElementSink via TSF COM to suppress the Windows 11
    text-prediction popup at the source.
    """
    global _tsf_refs
    try:
        import ctypes, ctypes.wintypes as wt, struct

        imm32 = ctypes.windll.imm32
        u32   = ctypes.windll.user32
        ole32 = ctypes.windll.ole32

        imm32.ImmGetContext.restype    = ctypes.c_void_p
        imm32.ImmGetContext.argtypes   = [wt.HWND]
        imm32.ImmReleaseContext.restype  = ctypes.c_bool
        imm32.ImmReleaseContext.argtypes = [wt.HWND, ctypes.c_void_p]
        imm32.ImmGetCompositionStringW.restype  = ctypes.c_long
        imm32.ImmGetCompositionStringW.argtypes = [ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, wt.DWORD]
        u32.GetFocus.restype  = wt.HWND
        u32.GetFocus.argtypes = []

        HRESULT = ctypes.c_long
        S_OK            = 0
        E_NOINTERFACE   = ctypes.c_long(0x80004002).value

        # ── GUID ──────────────────────────────────────────────────────────
        class GUID(ctypes.Structure):
            _fields_ = [('b', ctypes.c_byte * 16)]

        def _g(s):
            s = s.strip('{}')
            p = s.split('-')
            d1, d2, d3 = int(p[0], 16), int(p[1], 16), int(p[2], 16)
            d4 = bytes.fromhex(p[3] + p[4])
            raw = struct.pack('<IHH8s', d1, d2, d3, d4)
            g = GUID()
            ctypes.memmove(g.b, raw, 16)
            return g

        CLSID_TF_ThreadMgr  = _g('{529A9E6B-6587-4F23-AB9E-9C7D683E3C50}')
        IID_ITfThreadMgr    = _g('{AA80E801-2021-11D2-93E0-0060B067B86E}')
        IID_ITfUIElemMgr    = _g('{EA1EA136-19DF-11D7-A6D2-00065B84435C}')
        IID_ITfUIElemSink   = _g('{EA1EA135-19DF-11D7-A6D2-00065B84435C}')
        IID_IUnknown        = _g('{00000000-0000-0000-C000-000000000046}')

        # ── COM vtable prototypes ─────────────────────────────────────────
        QI_t    = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p,
                                     ctypes.POINTER(GUID),
                                     ctypes.POINTER(ctypes.c_void_p))
        Ref_t   = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
        Begin_t = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p,
                                     wt.DWORD, ctypes.POINTER(wt.BOOL))
        Dword_t = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wt.DWORD)

        class _Vtbl(ctypes.Structure):
            _fields_ = [
                ('QI',     QI_t),
                ('AddRef', Ref_t),
                ('Release',Ref_t),
                ('Begin',  Begin_t),
                ('Update', Dword_t),
                ('End',    Dword_t),
            ]

        class _Obj(ctypes.Structure):
            _fields_ = [('lpVtbl', ctypes.POINTER(_Vtbl))]

        # ── Sink implementations ──────────────────────────────────────────
        unk_bytes  = bytes(IID_IUnknown.b)
        sink_bytes = bytes(IID_ITfUIElemSink.b)

        def _qi(this, riid, ppv):
            if bytes(riid.contents.b) in (unk_bytes, sink_bytes):
                ppv[0] = this
                return S_OK
            ppv[0] = 0
            return E_NOINTERFACE

        def _addref(this):  return 2
        def _release(this): return 1

        def _begin(this, eid, pb):
            """Suppress prediction; allow kanji candidate (ATTR_TARGET_CONVERTED)."""
            try:
                hwnd = u32.GetFocus()
                if hwnd:
                    himc = imm32.ImmGetContext(hwnd)
                    if himc:
                        kanji = _in_kanji_selection(imm32, himc)
                        imm32.ImmReleaseContext(hwnd, himc)
                        pb[0] = wt.BOOL(1 if kanji else 0)
                        return S_OK
            except Exception:
                pass
            pb[0] = wt.BOOL(1)   # allow on error
            return S_OK

        def _update(this, eid): return S_OK
        def _end(this, eid):    return S_OK

        vtbl = _Vtbl(
            QI=QI_t(_qi), AddRef=Ref_t(_addref), Release=Ref_t(_release),
            Begin=Begin_t(_begin), Update=Dword_t(_update), End=Dword_t(_end),
        )
        obj = _Obj()
        obj.lpVtbl = ctypes.pointer(vtbl)

        # ── CoInitialize ─────────────────────────────────────────────────
        ole32.CoInitialize.restype  = HRESULT
        ole32.CoInitialize.argtypes = [ctypes.c_void_p]
        hr = ole32.CoInitialize(None)
        if hr not in (0, 1):   # S_OK or S_FALSE (already init)
            return

        # ── CoCreateInstance(CLSID_TF_ThreadMgr) ─────────────────────────
        ole32.CoCreateInstance.restype  = HRESULT
        ole32.CoCreateInstance.argtypes = [
            ctypes.POINTER(GUID), ctypes.c_void_p, wt.DWORD,
            ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
        ]
        pTM = ctypes.c_void_p()
        hr  = ole32.CoCreateInstance(
            ctypes.byref(CLSID_TF_ThreadMgr), None, 1,
            ctypes.byref(IID_ITfThreadMgr),  ctypes.byref(pTM),
        )
        if hr or not pTM.value:
            return

        # ── QI pTM → ITfUIElementMgr ──────────────────────────────────────
        # vtable[0] = IUnknown::QueryInterface
        def _vtbl_fn(ptr, idx, proto):
            vt = ctypes.cast(
                ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p)).contents,
                ctypes.POINTER(ctypes.c_void_p),
            )
            return proto(vt[idx])

        GenQI = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p,
                                   ctypes.POINTER(GUID),
                                   ctypes.POINTER(ctypes.c_void_p))
        pUEM = ctypes.c_void_p()
        hr   = _vtbl_fn(pTM, 0, GenQI)(pTM, ctypes.byref(IID_ITfUIElemMgr), ctypes.byref(pUEM))
        if hr or not pUEM.value:
            return

        # ── ITfUIElementMgr::AdviseUIElementSink (vtable index 5) ─────────
        # [0]QI [1]AddRef [2]Release [3]GetUIElement [4]EnumUIElements
        # [5]AdviseUIElementSink [6]UnadviseUIElementSink
        AdviseT = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p,
                                     ctypes.c_void_p,
                                     ctypes.POINTER(wt.DWORD))
        advise  = _vtbl_fn(pUEM, 5, AdviseT)
        cookie  = wt.DWORD(0)
        obj_ptr = ctypes.cast(ctypes.byref(obj), ctypes.c_void_p).value
        hr      = advise(pUEM, obj_ptr, ctypes.byref(cookie))

        if hr == 0:
            # Keep everything alive
            _tsf_refs = (obj, vtbl, pTM, pUEM, cookie,
                         _qi, _addref, _release, _begin, _update, _end)

    except Exception:
        pass   # fail silently; WH_CALLWNDPROC fallback still active


# Back-compat shim
def suppress_ime_popup(widget) -> None:   # noqa: ARG001
    pass
