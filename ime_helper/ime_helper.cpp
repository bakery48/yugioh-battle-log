// ime_helper.cpp  – TSF ITfUIElementSink (MinGW-w64 / MSVC compatible)
//
// Cross-compile from Linux:
//   x86_64-w64-mingw32-g++ -shared -O2 -o ime_helper.dll ime_helper.cpp \
//       -lole32 -luuid -limm32 -static-libgcc -static-libstdc++
//
// Build with MSVC (x64 Native Tools Command Prompt):
//   cl /nologo /LD /O2 /W3 ime_helper.cpp ole32.lib imm32.lib /link /OUT:ime_helper.dll

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <msctf.h>
#include <imm.h>
#include <new>

// TF_CLIENTID_NULL is not defined in MinGW headers
#ifndef TF_CLIENTID_NULL
#define TF_CLIENTID_NULL ((TfClientId)0)
#endif

// ---------------------------------------------------------------
// Globals
// ---------------------------------------------------------------
static ITfThreadMgr*    g_pThreadMgr   = nullptr;
static ITfSource*       g_pSource      = nullptr;  // for AdviseSink
static ITfUIElementMgr* g_pUIElemMgr   = nullptr;  // for GetUIElement
static DWORD            g_dwSinkCookie = TF_INVALID_COOKIE;
static TfClientId       g_clientId     = TF_CLIENTID_NULL;
static LONG             g_suppressCount = 0;
static LONG             g_allowCount    = 0;

// ---------------------------------------------------------------
// Is IME in kanji-selection mode? (Space pressed, ATTR_TARGET_CONVERTED set)
// ---------------------------------------------------------------
static bool in_kanji_selection() {
    HWND hwnd = GetFocus();
    if (!hwnd) hwnd = GetForegroundWindow();
    if (!hwnd) return false;

    HIMC himc = ImmGetContext(hwnd);
    if (!himc) return false;

    const DWORD MY_GCS_COMPATTR     = 0x0010;
    const BYTE  ATTR_TARGET_CONV = 0x01;

    LONG n = ImmGetCompositionStringW(himc, MY_GCS_COMPATTR, nullptr, 0);
    bool found = false;
    if (n > 0) {
        BYTE* buf = new (std::nothrow) BYTE[n];
        if (buf) {
            ImmGetCompositionStringW(himc, MY_GCS_COMPATTR, buf, n);
            for (LONG i = 0; i < n && !found; ++i)
                if (buf[i] == ATTR_TARGET_CONV) found = true;
            delete[] buf;
        }
    }
    ImmReleaseContext(hwnd, himc);
    return found;
}

// ---------------------------------------------------------------
// CUIElementSink
// ---------------------------------------------------------------
class CUIElementSink : public ITfUIElementSink {
    LONG m_cRef;
public:
    CUIElementSink() : m_cRef(1) {}

    // --- IUnknown ---
    STDMETHODIMP QueryInterface(REFIID riid, void** ppv) override {
        if (!ppv) return E_POINTER;
        *ppv = nullptr;
        if (IsEqualIID(riid, IID_IUnknown) ||
            IsEqualIID(riid, IID_ITfUIElementSink)) {
            *ppv = static_cast<ITfUIElementSink*>(this);
            AddRef();
            return S_OK;
        }
        return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef() override {
        return (ULONG)InterlockedIncrement(&m_cRef);
    }
    STDMETHODIMP_(ULONG) Release() override {
        ULONG r = (ULONG)InterlockedDecrement(&m_cRef);
        if (!r) delete this;
        return r;
    }

    // --- ITfUIElementSink ---
    STDMETHODIMP BeginUIElement(DWORD /*dwUIElementId*/, BOOL* pbShow) override {
        if (!pbShow) return E_POINTER;
        if (in_kanji_selection()) {
            *pbShow = TRUE;   // 漢字変換候補は表示する
            InterlockedIncrement(&g_allowCount);
        } else {
            *pbShow = FALSE;  // テキスト予測は非表示にする
            InterlockedIncrement(&g_suppressCount);
        }
        return S_OK;
    }
    STDMETHODIMP UpdateUIElement(DWORD) override { return S_OK; }
    STDMETHODIMP EndUIElement(DWORD)   override  { return S_OK; }
};

static CUIElementSink* g_pSink = nullptr;

// ---------------------------------------------------------------
// Exported API
// ---------------------------------------------------------------
extern "C" {

__declspec(dllexport) BOOL WINAPI ime_helper_init() {
    HRESULT hr = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    if (FAILED(hr) && hr != RPC_E_CHANGED_MODE) return FALSE;

    hr = CoCreateInstance(CLSID_TF_ThreadMgr, nullptr, CLSCTX_INPROC_SERVER,
                          IID_ITfThreadMgr, (void**)&g_pThreadMgr);
    if (FAILED(hr) || !g_pThreadMgr) return FALSE;

    hr = g_pThreadMgr->Activate(&g_clientId);
    if (FAILED(hr)) goto fail_threadmgr;

    // ITfUIElementMgr (optional – only for GetUIElement, not required for sink)
    g_pThreadMgr->QueryInterface(IID_ITfUIElementMgr, (void**)&g_pUIElemMgr);

    // Sink registration via ITfSource::AdviseSink
    hr = g_pThreadMgr->QueryInterface(IID_ITfSource, (void**)&g_pSource);
    if (FAILED(hr) || !g_pSource) goto fail_activate;

    g_pSink = new (std::nothrow) CUIElementSink();
    if (!g_pSink) goto fail_source;

    hr = g_pSource->AdviseSink(IID_ITfUIElementSink,
                               static_cast<IUnknown*>(g_pSink),
                               &g_dwSinkCookie);
    if (FAILED(hr)) goto fail_sink;

    return TRUE;

fail_sink:
    g_pSink->Release(); g_pSink = nullptr;
fail_source:
    g_pSource->Release(); g_pSource = nullptr;
fail_activate:
    if (g_pUIElemMgr) { g_pUIElemMgr->Release(); g_pUIElemMgr = nullptr; }
    g_pThreadMgr->Deactivate();
fail_threadmgr:
    g_pThreadMgr->Release(); g_pThreadMgr = nullptr;
    return FALSE;
}

__declspec(dllexport) void WINAPI ime_helper_uninit() {
    if (g_pSource && g_dwSinkCookie != TF_INVALID_COOKIE) {
        g_pSource->UnadviseSink(g_dwSinkCookie);
        g_dwSinkCookie = TF_INVALID_COOKIE;
    }
    if (g_pSink)      { g_pSink->Release();      g_pSink      = nullptr; }
    if (g_pSource)    { g_pSource->Release();    g_pSource    = nullptr; }
    if (g_pUIElemMgr) { g_pUIElemMgr->Release(); g_pUIElemMgr = nullptr; }
    if (g_pThreadMgr) {
        if (g_clientId != TF_CLIENTID_NULL) g_pThreadMgr->Deactivate();
        g_pThreadMgr->Release(); g_pThreadMgr = nullptr;
    }
}

__declspec(dllexport) BOOL  WINAPI ime_helper_is_active()       { return g_dwSinkCookie != TF_INVALID_COOKIE; }
__declspec(dllexport) DWORD WINAPI ime_helper_suppress_count()  { return (DWORD)g_suppressCount; }
__declspec(dllexport) DWORD WINAPI ime_helper_allow_count()     { return (DWORD)g_allowCount; }

} // extern "C"

BOOL WINAPI DllMain(HINSTANCE, DWORD, LPVOID) { return TRUE; }
