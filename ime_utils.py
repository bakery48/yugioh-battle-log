"""
Suppress the Windows 11 text-prediction popup (テキスト候補).

Every step is logged to %USERPROFILE%\yugioh_ime.log so you can verify
what is and is not working without reading source code.

DIAGNOSTIC COUNTERS (readable from main.py):
  _begin_count[0]    – number of BeginUIElement callbacks received
  _suppress_count[0] – number of those that were suppressed (pbShow=0)
"""

import sys
import os
import datetime

# ── Log file ──────────────────────────────────────────────────────────────────
_LOG_PATH = os.path.join(os.path.expanduser("~"), "yugioh_ime.log")

# ── File-version stamp (modification time of this file) ──────────────────────
try:
    _FILE_TS = datetime.datetime.fromtimestamp(
        os.path.getmtime(os.path.abspath(__file__))
    ).strftime("%m%d-%H%M")
except Exception:
    _FILE_TS = "?"

def _log(msg: str) -> None:
    try:
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


# ── Module-level anchors ──────────────────────────────────────────────────────
_hook_handle    = None
_hook_cb        = None
_tsf_anchors    = None
_begin_count    = [0]   # incremented every time BeginUIElement fires
_suppress_count = [0]   # incremented every time we set pbShow=FALSE


def install_ime_hook() -> None:
    """Call once after tk.Tk() is created."""
    _log("=" * 60)
    _log("install_ime_hook() called")
    if sys.platform != "win32":
        _log("Not Windows — skipping")
        return
    _install_wh_hook()
    _install_tsf_sink()
    _log(f"WH hook handle : {_hook_handle}")
    _log(f"TSF anchors set: {_tsf_anchors is not None}")
    # Also dump the log to stdout so the console always shows what happened
    try:
        with open(_LOG_PATH, "r", encoding="utf-8") as _f:
            for _line in _f:
                print("  LOG|", _line, end="")
    except Exception:
        pass


def get_status() -> str:
    """Return a one-line status string (shown in the title bar, refreshed periodically)."""
    parts = []
    parts.append("WH:" + ("OK" if _hook_handle else "NG"))
    parts.append("TSF:" + ("OK" if _tsf_anchors is not None else "NG"))
    parts.append(f"BE:{_begin_count[0]}/{_suppress_count[0]}")  # calls/suppressed
    parts.append(f"v{_FILE_TS}")
    return "  [IME " + " ".join(parts) + "]"


# ─── shared IMM helper ────────────────────────────────────────────────────────

def _in_kanji_selection(imm32, himc) -> bool:
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
    except Exception as e:
        _log(f"  _in_kanji_selection error: {e}")
        return True


# ─── WH_CALLWNDPROC hook ──────────────────────────────────────────────────────

def _install_wh_hook() -> None:
    global _hook_handle, _hook_cb
    if _hook_handle is not None:
        return
    try:
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
            _fields_ = [("lParam", wt.LPARAM), ("wParam", wt.WPARAM),
                        ("message", wt.UINT),  ("hwnd",   wt.HWND)]

        HOOKPROC = ctypes.WINFUNCTYPE(
            ctypes.c_longlong, ctypes.c_int, wt.WPARAM, wt.LPARAM)

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
                    closed = any(
                        imm32.ImmNotifyIME(himc, NI_CLOSECANDIDATE, i, 0)
                        for i in range(4) if bitmask & (1 << i)
                    )
                    if not closed:
                        imm32.ImmNotifyIME(himc, NI_CLOSECANDIDATE, 0, 0)
                finally:
                    _suppressing[0] = False
                    imm32.ImmReleaseContext(hwnd, himc)
            return result

        _hook_cb = HOOKPROC(_hook)
        cb_addr  = ctypes.cast(_hook_cb, ctypes.c_void_p).value or 0
        _hook_handle = u32.SetWindowsHookExW(
            WH_CALLWNDPROC, cb_addr, None, k32.GetCurrentThreadId())
        _log(f"WH_CALLWNDPROC installed: handle={_hook_handle}")
    except Exception as e:
        _log(f"WH hook install FAILED: {e}")


# ─── TSF ITfUIElementSink ─────────────────────────────────────────────────────

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
        imm32.ImmGetCompositionStringW.argtypes = [ctypes.c_void_p, wt.DWORD, ctypes.c_void_p, wt.DWORD]
        u32.GetFocus.restype  = wt.HWND
        u32.GetFocus.argtypes = []

        HRESULT = ctypes.c_long
        S_OK    = 0
        E_NOINT = ctypes.c_long(0x80004002).value

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

        QI_t    = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p,
                                     ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))
        Ref_t   = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)
        Begin_t = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wt.DWORD, ctypes.POINTER(wt.BOOL))
        Dword_t = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, wt.DWORD)

        class Vtbl(ctypes.Structure):
            _fields_ = [('QI',     QI_t),
                        ('AddRef', Ref_t),
                        ('Release',Ref_t),
                        ('Begin',  Begin_t),
                        ('Update', Dword_t),
                        ('End',    Dword_t)]

        class SinkObj(ctypes.Structure):
            _fields_ = [('lpVtbl', ctypes.POINTER(Vtbl))]

        unk_b  = bytes(IID_IUnknown.b)
        sink_b = bytes(IID_ITfUIElemSink.b)

        def _qi(this, riid, ppv):
            if bytes(riid.contents.b) in (unk_b, sink_b):
                ppv[0] = this; return S_OK
            ppv[0] = 0; return E_NOINT

        def _addref(this):  return 2
        def _release(this): return 1

        def _begin(this, eid, pb):
            _begin_count[0] += 1
            try:
                hwnd  = u32.GetFocus()
                kanji = False
                if hwnd:
                    himc = imm32.ImmGetContext(hwnd)
                    if himc:
                        kanji = _in_kanji_selection(imm32, himc)
                        imm32.ImmReleaseContext(hwnd, himc)
                    else:
                        _log(f"  BeginUIElement #{_begin_count[0]} eid={eid} hwnd={hwnd} himc=NULL")
                else:
                    _log(f"  BeginUIElement #{_begin_count[0]} eid={eid} hwnd=NULL (no focus)")
                pb[0] = 1 if kanji else 0
                if not kanji:
                    _suppress_count[0] += 1
                _log(f"  BeginUIElement #{_begin_count[0]} eid={eid} "
                     f"hwnd={hwnd} kanji={kanji} → pbShow={pb[0]}")
            except Exception as e:
                _log(f"  BeginUIElement error: {e}")
                pb[0] = 1
            return S_OK

        def _update(this, eid): return S_OK
        def _end(this, eid):    return S_OK

        # Keep every callback object alive explicitly
        cb_qi     = QI_t(_qi)
        cb_addref = Ref_t(_addref)
        cb_release= Ref_t(_release)
        cb_begin  = Begin_t(_begin)
        cb_update = Dword_t(_update)
        cb_end    = Dword_t(_end)

        vtbl = Vtbl(QI=cb_qi, AddRef=cb_addref, Release=cb_release,
                    Begin=cb_begin, Update=cb_update, End=cb_end)
        obj = SinkObj()
        obj.lpVtbl = ctypes.pointer(vtbl)

        # ── CoInitialize ──────────────────────────────────────────────────
        ole32.CoInitialize.restype  = HRESULT
        ole32.CoInitialize.argtypes = [ctypes.c_void_p]
        hr = ole32.CoInitialize(None)
        _log(f"CoInitialize hr=0x{hr & 0xFFFFFFFF:08X}")
        if hr not in (S_OK, 1):
            _log("  → incompatible apartment model, aborting TSF sink")
            return

        # ── CoCreateInstance(CLSID_TF_ThreadMgr) ─────────────────────────
        ole32.CoCreateInstance.restype  = HRESULT
        ole32.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p,
                                           wt.DWORD, ctypes.POINTER(GUID),
                                           ctypes.POINTER(ctypes.c_void_p)]
        pTM = ctypes.c_void_p()
        hr  = ole32.CoCreateInstance(ctypes.byref(CLSID_TF_ThreadMgr), None, 1,
                                     ctypes.byref(IID_ITfThreadMgr), ctypes.byref(pTM))
        _log(f"CoCreateInstance(TF_ThreadMgr) hr=0x{hr & 0xFFFFFFFF:08X} ptr={pTM.value}")
        if hr or not pTM.value:
            return

        # ── Helper: call COM vtable method ────────────────────────────────
        def _call(ptr, idx, proto, *args):
            vt = ctypes.cast(
                ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p)).contents,
                ctypes.POINTER(ctypes.c_void_p))
            return proto(vt[idx])(ptr, *args)

        GenQI = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p,
                                   ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))

        # ── QI pTM → ITfUIElementMgr ──────────────────────────────────────
        pUEM = ctypes.c_void_p()
        hr   = _call(pTM, 0, GenQI,
                     ctypes.byref(IID_ITfUIElemMgr), ctypes.byref(pUEM))
        _log(f"QI(ITfUIElementMgr) hr=0x{hr & 0xFFFFFFFF:08X} ptr={pUEM.value}")
        if hr or not pUEM.value:
            return

        # ── AdviseUIElementSink (vtable index 5) ─────────────────────────
        AdviseT = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p,
                                     ctypes.c_void_p, ctypes.POINTER(wt.DWORD))
        cookie  = wt.DWORD(0)
        obj_ptr = ctypes.cast(ctypes.byref(obj), ctypes.c_void_p).value
        hr      = _call(pUEM, 5, AdviseT, obj_ptr, ctypes.byref(cookie))
        _log(f"AdviseUIElementSink hr=0x{hr & 0xFFFFFFFF:08X} cookie={cookie.value}")

        if hr == 0:
            _tsf_anchors = (obj, vtbl, pTM, pUEM, cookie,
                            cb_qi, cb_addref, cb_release,
                            cb_begin, cb_update, cb_end,
                            _qi, _addref, _release, _begin, _update, _end)
            _log("TSF ITfUIElementSink installed successfully")
        else:
            _log("AdviseUIElementSink FAILED — TSF suppression inactive")

    except Exception as e:
        _log(f"_install_tsf_sink EXCEPTION: {e}")
        import traceback
        _log(traceback.format_exc())


def suppress_ime_popup(widget) -> None:   # noqa: ARG001
    pass
