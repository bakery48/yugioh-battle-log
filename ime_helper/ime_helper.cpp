// ime_helper.cpp  – TSF ITfUIElementSink を正しい COM で実装
//
// Build (MSVC / Developer Command Prompt):
//   cl /nologo /LD /O2 /W3 ime_helper.cpp ole32.lib /link /OUT:ime_helper.dll
//
// Build (MinGW-w64 cross from Linux):
//   x86_64-w64-mingw32-g++ -shared -O2 -o ime_helper.dll ime_helper.cpp \
//       -lole32 -luuid -municode -static-libgcc -static-libstdc++

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <msctf.h>
#include <oleauto.h>
#include <new>

// ---------------------------------------------------------------
// Globals
// ---------------------------------------------------------------
static ITfThreadMgr*      g_pThreadMgr    = nullptr;
static ITfUIElementMgr*   g_pUIElemMgr    = nullptr;
static DWORD              g_dwSinkCookie  = TF_INVALID_COOKIE;
static TfClientId         g_clientId      = TF_CLIENTID_NULL;
static DWORD              g_suppressCount = 0;
static DWORD              g_allowCount    = 0;

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
            IsEqualIID(riid, __uuidof(ITfUIElementSink))) {
            *ppv = static_cast<ITfUIElementSink*>(this);
            AddRef();
            return S_OK;
        }
        return E_NOINTERFACE;
    }
    STDMETHODIMP_(ULONG) AddRef() override {
        return InterlockedIncrement(&m_cRef);
    }
    STDMETHODIMP_(ULONG) Release() override {
        ULONG r = InterlockedDecrement(&m_cRef);
        if (!r) delete this;
        return r;
    }

    // --- ITfUIElementSink ---
    STDMETHODIMP BeginUIElement(DWORD dwUIElementId, BOOL* pbShow) override {
        if (!pbShow) return E_POINTER;

        // 漢字変換候補ウィンドウ (ITfCandidateListUIElement) は許可する
        if (g_pUIElemMgr) {
            ITfUIElement* pElem = nullptr;
            if (SUCCEEDED(g_pUIElemMgr->GetUIElement(dwUIElementId, &pElem)) && pElem) {
                ITfCandidateListUIElement* pCand = nullptr;
                HRESULT hr = pElem->QueryInterface(
                    __uuidof(ITfCandidateListUIElement), (void**)&pCand);
                pElem->Release();
                if (SUCCEEDED(hr) && pCand) {
                    pCand->Release();
                    *pbShow = TRUE;   // 漢字候補は表示を許可
                    ++g_allowCount;
                    return S_OK;
                }
            }
        }

        // それ以外 (テキスト予測 IMN_OPENCANDIDATE) は非表示
        *pbShow = FALSE;
        ++g_suppressCount;
        return S_OK;
    }

    STDMETHODIMP UpdateUIElement(DWORD /*dwUIElementId*/) override { return S_OK; }
    STDMETHODIMP EndUIElement(DWORD /*dwUIElementId*/) override   { return S_OK; }
};

static CUIElementSink* g_pSink = nullptr;

// ---------------------------------------------------------------
// Exported API
// ---------------------------------------------------------------
extern "C" {

// 初期化。成功時TRUE、失敗時FALSE
__declspec(dllexport) BOOL WINAPI ime_helper_init() {
    // CoInitialize は呼び出し元スレッドが既に行っていると仮定。
    // 念のため試みるが RPC_E_CHANGED_MODE は無視する。
    HRESULT hr = CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
    if (FAILED(hr) && hr != RPC_E_CHANGED_MODE) return FALSE;

    hr = CoCreateInstance(CLSID_TF_ThreadMgr, nullptr, CLSCTX_INPROC_SERVER,
                          IID_ITfThreadMgr, (void**)&g_pThreadMgr);
    if (FAILED(hr) || !g_pThreadMgr) return FALSE;

    hr = g_pThreadMgr->Activate(&g_clientId);
    if (FAILED(hr)) goto fail_threadmgr;

    hr = g_pThreadMgr->QueryInterface(
        __uuidof(ITfUIElementMgr), (void**)&g_pUIElemMgr);
    if (FAILED(hr) || !g_pUIElemMgr) goto fail_activate;

    g_pSink = new (std::nothrow) CUIElementSink();
    if (!g_pSink) goto fail_mgr;

    hr = g_pUIElemMgr->AdviseUIElementSink(g_pSink, &g_dwSinkCookie);
    if (FAILED(hr)) goto fail_sink;

    return TRUE;

fail_sink:
    g_pSink->Release(); g_pSink = nullptr;
fail_mgr:
    g_pUIElemMgr->Release(); g_pUIElemMgr = nullptr;
fail_activate:
    g_pThreadMgr->Deactivate();
fail_threadmgr:
    g_pThreadMgr->Release(); g_pThreadMgr = nullptr;
    return FALSE;
}

// 後片付け
__declspec(dllexport) void WINAPI ime_helper_uninit() {
    if (g_pUIElemMgr && g_dwSinkCookie != TF_INVALID_COOKIE) {
        g_pUIElemMgr->UnadviseUIElementSink(g_dwSinkCookie);
        g_dwSinkCookie = TF_INVALID_COOKIE;
    }
    if (g_pSink)      { g_pSink->Release();      g_pSink      = nullptr; }
    if (g_pUIElemMgr) { g_pUIElemMgr->Release(); g_pUIElemMgr = nullptr; }
    if (g_pThreadMgr) {
        if (g_clientId != TF_CLIENTID_NULL) g_pThreadMgr->Deactivate();
        g_pThreadMgr->Release(); g_pThreadMgr = nullptr;
    }
}

// 現在アクティブかどうか
__declspec(dllexport) BOOL WINAPI ime_helper_is_active() {
    return (g_pUIElemMgr != nullptr && g_dwSinkCookie != TF_INVALID_COOKIE)
           ? TRUE : FALSE;
}

// デバッグ用カウンタ
__declspec(dllexport) DWORD WINAPI ime_helper_suppress_count() {
    return g_suppressCount;
}
__declspec(dllexport) DWORD WINAPI ime_helper_allow_count() {
    return g_allowCount;
}

} // extern "C"

BOOL WINAPI DllMain(HINSTANCE, DWORD, LPVOID) { return TRUE; }
