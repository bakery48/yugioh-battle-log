@echo off
REM ============================================================
REM ime_helper.dll ビルドスクリプト
REM
REM [方法A] Visual Studio / Build Tools (推奨)
REM   - "x64 Native Tools Command Prompt for VS 20xx" を開いて実行
REM   - または vcvars64.bat を事前に呼ぶ
REM
REM [方法B] MinGW-w64 が PATH に入っている場合
REM   - 下の MINGW セクションを有効にする
REM ============================================================

setlocal

set OUTDIR=%~dp0..
set SRC=%~dp0ime_helper.cpp

REM --- 方法A: MSVC ---
where cl >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [MSVC] Building ime_helper.dll ...
    cl /nologo /LD /O2 /W3 "%SRC%" ole32.lib ^
       /link /OUT:"%OUTDIR%\ime_helper.dll" /IMPLIB:"%OUTDIR%\ime_helper.lib"
    if %ERRORLEVEL% EQU 0 (
        echo [OK] ime_helper.dll -> %OUTDIR%
    ) else (
        echo [FAILED] MSVC build failed.
    )
    goto end
)

REM --- 方法B: MinGW-w64 ---
where x86_64-w64-mingw32-g++ >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [MinGW] Building ime_helper.dll ...
    x86_64-w64-mingw32-g++ -shared -O2 -o "%OUTDIR%\ime_helper.dll" "%SRC%" ^
        -lole32 -luuid -municode -static-libgcc -static-libstdc++
    if %ERRORLEVEL% EQU 0 (
        echo [OK] ime_helper.dll -> %OUTDIR%
    ) else (
        echo [FAILED] MinGW build failed.
    )
    goto end
)

where g++ >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [g++] Building ime_helper.dll ...
    g++ -shared -O2 -o "%OUTDIR%\ime_helper.dll" "%SRC%" ^
        -lole32 -luuid -static-libgcc -static-libstdc++
    if %ERRORLEVEL% EQU 0 (
        echo [OK] ime_helper.dll -> %OUTDIR%
    ) else (
        echo [FAILED] g++ build failed.
    )
    goto end
)

echo [ERROR] コンパイラが見つかりません。
echo   Visual Studio Build Tools または MinGW-w64 をインストールしてください。
echo   https://aka.ms/vs/17/release/vs_BuildTools.exe
exit /b 1

:end
endlocal
