@echo off
setlocal

set OUTDIR=%~dp0..
set SRC=%~dp0ime_helper.cpp

echo Building ime_helper.dll ...

REM --- Try MSVC (cl.exe) ---
where cl >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Using MSVC cl.exe
    cl /nologo /LD /O2 /W3 "%SRC%" ole32.lib ^
       /link /OUT:"%OUTDIR%\ime_helper.dll" /IMPLIB:"%OUTDIR%\ime_helper.lib"
    if %ERRORLEVEL% EQU 0 (
        echo [OK] ime_helper.dll created.
    ) else (
        echo [FAILED] MSVC build failed.
    )
    goto end
)

REM --- Try MinGW-w64 ---
where x86_64-w64-mingw32-g++ >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Using x86_64-w64-mingw32-g++
    x86_64-w64-mingw32-g++ -shared -O2 -o "%OUTDIR%\ime_helper.dll" "%SRC%" ^
        -lole32 -luuid -municode -static-libgcc -static-libstdc++
    if %ERRORLEVEL% EQU 0 (
        echo [OK] ime_helper.dll created.
    ) else (
        echo [FAILED] MinGW build failed.
    )
    goto end
)

REM --- Try g++ (MinGW in PATH) ---
where g++ >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Using g++
    g++ -shared -O2 -o "%OUTDIR%\ime_helper.dll" "%SRC%" ^
        -lole32 -luuid -static-libgcc -static-libstdc++
    if %ERRORLEVEL% EQU 0 (
        echo [OK] ime_helper.dll created.
    ) else (
        echo [FAILED] g++ build failed.
    )
    goto end
)

echo [ERROR] No compiler found.
echo.
echo Option A: Run this script from "x64 Native Tools Command Prompt for VS 20xx"
echo           (Start Menu -^> Visual Studio -^> Developer Command Prompt)
echo.
echo Option B: Install VS Build Tools (free):
echo           winget install Microsoft.VisualStudio.2022.BuildTools
echo           Then open "x64 Native Tools Command Prompt" and re-run.
exit /b 1

:end
endlocal
