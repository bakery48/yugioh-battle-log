"""
Suppress the Windows 11 text-prediction popup (テキスト候補).

The popup is a TSF UI element (fires for ASCII and Japanese alike).
Primary fix: ITfUIElementSink.BeginUIElement → set *pbShow = FALSE.
Secondary:   WH_CALLWNDPROC fallback for WM_IME_* messages.

Critical ctypes rule: WINFUNCTYPE callback objects stored in a struct field
are NOT kept alive by ctypes.  They must be held in a Python variable for
the process lifetime, otherwise the thunk is freed and the vtable entry
becomes a dangling pointer.
"""

import sys

# Module-level anchors to prevent garbage collection
_hook_handle = None
_hook_cb     = None
_tsf_anchors = None   # tuple of every ctypes object that must stay alive


def install_ime_hook() -> None:
    """Call once after tk.Tk() is created."""
    if sys.platform != "win32":
        return
    _install_wh_hook()
    _install_tsf_sink()


# ─── shared IMM helper ───────────────────────────────────────────────────────

def _in_kanji_selection(imm32, himc) -> bool:
    """True ONLY when the kanji candidate list is open (ATTR_TARGET_CONVERTED)."""
    import ctypes
    GCS_COMPATTR     = 0x0010
    ATTR_TARGET_CONV = 0x01
    try:
        n = imm32.ImmGetCompositionStringW(himc, GCS_COMPATTR, None, 0)
        if n <= 0:
            return False
        buf = (ctypes.c_ubyte * n)()
        imm32.ImmGetCompositionStringW(himc, GCS_COMPATTR, buf, n)
        return any(b == ATTR_TARGET_CONV for b in buf)
    except Exception:
        return True   # safe: don't suppress on error


# ─── WH_CALLWNDPROC hook (secondary / fallback) ──────────────────────────────

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
            elif cwp.message == WM_IME_REQUEST and cwp.wParam == IMR_DOCUMENTFEED:
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


# ─── TSF ITfUIElementSink (primary fix) ──────────────────────────────────────

def _install_tsf_sink() -> None:
    global _tsf_anchors
    if _tsf_anchors is not None:
        return
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
        imm32.ImmGetCompositionStringW.argtypes = [
            ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, wt.DWORD]
        u32.GetFocus.restype  = wt.HWND
        u32.GetFocus.argtypes = []

        HRESULT       = ctypes.c_long
        S_OK          = 0
        E_NOINT       = ctypes.c_long(0x80004002).value

        # ── GUID ──────────────────────────────────────────────────────────
        class GUID(ctypes.Structure):
            _fields_ = [('b', ctypes.c_byte * 16)]

        def _g(s):
            s = s.strip('{}'); p = s.split('-')
            d1, d2, d3 = int(p[0],16), int(p[1],16), int(p[2],16)
            d4 = bytes.fromhex(p[3] + p[4])
            raw = struct.pack('<IHH8s', d1, d2, d3, d4)
            g = GUID(); ctypes.memmove(g.b, raw, 16); return g

        CLSID_TF_ThreadMgr = _g('{529A9E6B-6587-4F23-AB9E-9C7D683E3C50}')
        IID_ITfThreadMgr   = _g('{AA80E801-2021-11D2-93E0-0060B067B86E}')
        IID_ITfUIElemMgr   = _g('{EA1EA136-19DF-11D7-A6D2-00065B84435C}')
        IID_ITfUIElemSink  = _g('{EA1EA135-19DF-11D7-A6D2-00065B84435C}')
        IID_IUnknown       = _g('{00000000-0000-0000-C000-000000000046}')

        # ── Vtable WINFUNCTYPE prototypes ─────────────────────────────────
        QI_t    = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p,
                                     ctypes.POINTER(GUID),
                                     ctypes.POINTER(ctypes.c_void_p))
        Ref_t   = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
        Begin_t = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p,
                                     wt.DWORD, ctypes.POINTER(wt.BOOL))
        Dword_t = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wt.DWORD)

        # ── Vtable and COM object structures ──────────────────────────────
        class Vtbl(ctypes.Structure):
            _fields_ = [
                ('QI',     QI_t),
                ('AddRef', Ref_t),
                ('Release',Ref_t),
                ('Begin',  Begin_t),
                ('Update', Dword_t),
                ('End',    Dword_t),
            ]

        class SinkObj(ctypes.Structure):
            _fields_ = [('lpVtbl', ctypes.POINTER(Vtbl))]

        # ── Sink implementation functions ─────────────────────────────────
        unk_bytes  = bytes(IID_IUnknown.b)
        sink_bytes = bytes(IID_ITfUIElemSink.b)

        def _qi(this, riid, ppv):
            if bytes(riid.contents.b) in (unk_bytes, sink_bytes):
                ppv[0] = this
                return S_OK
            ppv[0] = 0
            return E_NOINT

        def _addref(this):  return 2
        def _release(this): return 1

        def _begin(this, eid, pb):
            """Suppress prediction/completion; allow kanji candidate list."""
            try:
                hwnd = u32.GetFocus()
                kanji = False
                if hwnd:
                    himc = imm32.ImmGetContext(hwnd)
                    if himc:
                        kanji = _in_kanji_selection(imm32, himc)
                        imm32.ImmReleaseContext(hwnd, himc)
                    # himc == 0 means no IME context → not kanji → suppress
                pb[0] = 1 if kanji else 0
            except Exception:
                pb[0] = 1   # allow on unexpected error
            return S_OK

        def _update(this, eid): return S_OK
        def _end(this, eid):    return S_OK

        # ── CRITICAL: wrap callbacks BEFORE putting into struct ───────────
        # ctypes does NOT keep a Python reference to WINFUNCTYPE objects
        # stored in struct fields — only the raw C pointer is stored.
        # We must hold explicit Python references or the thunks are freed.
        cb_qi     = QI_t(_qi)
        cb_addref = Ref_t(_addref)
        cb_release= Ref_t(_release)
        cb_begin  = Begin_t(_begin)
        cb_update = Dword_t(_update)
        cb_end    = Dword_t(_end)

        vtbl = Vtbl(
            QI=cb_qi, AddRef=cb_addref, Release=cb_release,
            Begin=cb_begin, Update=cb_update, End=cb_end,
        )
        obj = SinkObj()
        obj.lpVtbl = ctypes.pointer(vtbl)

        # ── CoInitialize ──────────────────────────────────────────────────
        ole32.CoInitialize.restype  = HRESULT
        ole32.CoInitialize.argtypes = [ctypes.c_void_p]
        hr = ole32.CoInitialize(None)
        if hr not in (S_OK, 1):   # S_OK or S_FALSE (already initialised)
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

        # ── Helper: call vtable method N on a COM pointer ─────────────────
        def _call(ptr, idx, proto, *args):
            vt = ctypes.cast(
                ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p)).contents,
                ctypes.POINTER(ctypes.c_void_p),
            )
            return proto(vt[idx])(ptr, *args)

        GenQI = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p,
                                   ctypes.POINTER(GUID),
                                   ctypes.POINTER(ctypes.c_void_p))

        # ── QI pTM → ITfUIElementMgr ──────────────────────────────────────
        pUEM = ctypes.c_void_p()
        hr   = _call(pTM, 0, GenQI,
                     ctypes.byref(IID_ITfUIElemMgr), ctypes.byref(pUEM))
        if hr or not pUEM.value:
            return

        # ── AdviseUIElementSink (ITfUIElementMgr vtable[5]) ──────────────
        # [0]QI [1]AddRef [2]Release [3]GetUIElement [4]EnumUIElements
        # [5]AdviseUIElementSink [6]UnadviseUIElementSink
        AdviseT = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p,
                                     ctypes.c_void_p,
                                     ctypes.POINTER(wt.DWORD))
        cookie  = wt.DWORD(0)
        obj_ptr = ctypes.cast(ctypes.byref(obj), ctypes.c_void_p).value
        hr      = _call(pUEM, 5, AdviseT, obj_ptr, ctypes.byref(cookie))

        if hr == 0:
            # Keep EVERYTHING alive — any of these being freed = crash / silent failure
            _tsf_anchors = (
                obj, vtbl, pTM, pUEM, cookie,
                cb_qi, cb_addref, cb_release, cb_begin, cb_update, cb_end,
                _qi, _addref, _release, _begin, _update, _end,
            )

    except Exception:
        pass   # fail silently; WH_CALLWNDPROC still active as fallback


def suppress_ime_popup(widget) -> None:   # noqa: ARG001
    """Back-compat shim — no longer needed."""
    pass
