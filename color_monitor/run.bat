@echo off
chcp 65001 > nul
echo 色変化監視アプリを起動しています...
echo.
echo 依存関係を確認中...
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [エラー] 依存関係のインストールに失敗しました。
    echo Python がインストールされているか確認してください。
    pause
    exit /b 1
)
echo 起動中...
python monitor_app.py
if errorlevel 1 (
    echo.
    echo [エラー] アプリの起動に失敗しました。
    pause
)
