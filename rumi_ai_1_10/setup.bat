@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%.venv"
set "REQUIREMENTS=%SCRIPT_DIR%requirements.txt"
set "GUIDE_DIR=%SCRIPT_DIR%rumi_setup\guide"

echo.
echo ══════════════════════════════════════════════════════
echo   🌸 Rumi AI セットアップ
echo ══════════════════════════════════════════════════════
echo.

REM ========================================
REM Python チェック (python, python3, py)
REM ========================================
set "PYTHON_CMD="

where python >nul 2>&1
if !errorlevel!==0 (
    REM Python 3 か確認
    python --version 2>&1 | findstr /C:"Python 3" >nul
    if !errorlevel!==0 (
        set "PYTHON_CMD=python"
        goto :python_found
    )
)

where python3 >nul 2>&1
if !errorlevel!==0 (
    set "PYTHON_CMD=python3"
    goto :python_found
)

where py >nul 2>&1
if !errorlevel!==0 (
    REM py launcher で Python 3 を指定
    py -3 --version >nul 2>&1
    if !errorlevel!==0 (
        set "PYTHON_CMD=py -3"
        goto :python_found
    )
)

REM Python が見つからない
echo   ✗ Python 3 が見つかりません
echo.
echo   Python は Rumi AI の実行に必須です。
echo   インストールガイドを開きます...
echo.

if exist "%GUIDE_DIR%\python.html" (
    start "" "%GUIDE_DIR%\python.html"
) else if exist "%GUIDE_DIR%\index.html" (
    start "" "%GUIDE_DIR%\index.html"
) else (
    echo   ガイドファイルが見つかりません
    echo   https://www.python.org/ から Python をインストールしてください
)
echo.
echo   Python をインストール後、再度実行してください。
pause
exit /b 1

:python_found
echo   ✓ Python: %PYTHON_CMD%
for /f "tokens=*" %%i in ('%PYTHON_CMD% --version 2^>^&1') do echo     %%i
echo.

REM ========================================
REM Python バージョン確認 (3.9+)
REM ========================================
for /f %%i in ('%PYTHON_CMD% -c "import sys; print(1 if sys.version_info >= (3, 9) else 0)" 2^>nul') do set "PY_OK=%%i"
if not "%PY_OK%"=="1" (
    echo   ✗ Python 3.9 以上が必要です
    echo.
    echo   インストールガイドを開きます...
    if exist "%GUIDE_DIR%\python.html" (
        start "" "%GUIDE_DIR%\python.html"
    )
    pause
    exit /b 1
)

REM ========================================
REM Git チェック
REM ========================================
where git >nul 2>&1
if !errorlevel! neq 0 (
    echo   ✗ Git が見つかりません
    echo.
    echo   Git は Pack のインストールに必要です。
    echo   インストールガイドを開きます...
    echo.
    
    if exist "%GUIDE_DIR%\git.html" (
        start "" "%GUIDE_DIR%\git.html"
    ) else if exist "%GUIDE_DIR%\index.html" (
        start "" "%GUIDE_DIR%\index.html"
    ) else (
        echo   https://git-scm.com/ から Git をインストールしてください
    )
    echo.
    echo   Git をインストール後、再度実行してください。
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('git --version 2^>^&1') do echo   ✓ Git: %%i
echo.

REM ========================================
REM Docker チェック（任意）
REM ========================================
where docker >nul 2>&1
if !errorlevel!==0 (
    for /f "tokens=*" %%i in ('docker --version 2^>^&1') do echo   ✓ Docker: %%i
) else (
    echo   ⚠ Docker: 見つかりません（推奨・任意）
)
echo.

REM ========================================
REM 仮想環境の再作成
REM ========================================
echo   仮想環境をセットアップ中...

REM 既存の仮想環境を削除
if exist "%VENV_DIR%" (
    echo     既存の .venv を削除中...
    rmdir /s /q "%VENV_DIR%" 2>nul
    
    REM 削除確認（ファイルが使用中の場合に失敗する）
    if exist "%VENV_DIR%" (
        echo.
        echo     ✗ 削除に失敗しました
        echo     .venv フォルダが使用中の可能性があります。
        echo     すべてのターミナルを閉じてから再実行してください。
        pause
        exit /b 1
    )
    echo     ✓ 削除完了
)

REM 新しい仮想環境を作成
echo     .venv を作成中...
%PYTHON_CMD% -m venv "%VENV_DIR%"
if !errorlevel! neq 0 (
    echo.
    echo     ✗ 仮想環境の作成に失敗しました
    echo     python -m venv をサポートしているか確認してください
    pause
    exit /b 1
)
echo     ✓ 作成完了
echo.

REM ========================================
REM 仮想環境の有効化
REM ========================================
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"

if not exist "%VENV_PYTHON%" (
    echo   ✗ 仮想環境の Python が見つかりません
    echo     %VENV_PYTHON%
    pause
    exit /b 1
)

echo   仮想環境を有効化中...
call "%VENV_DIR%\Scripts\activate.bat"
echo     ✓ 有効化完了
echo.

REM ========================================
REM pip アップグレード
REM ========================================
echo   pip をアップグレード中...
"%VENV_PYTHON%" -m pip install --upgrade pip >nul 2>&1
if !errorlevel!==0 (
    echo     ✓ pip アップグレード完了
) else (
    echo     ⚠ pip アップグレードをスキップ（続行します）
)
echo.

REM ========================================
REM requirements.txt インストール
REM ========================================
if not exist "%REQUIREMENTS%" (
    echo   ✗ requirements.txt が見つかりません
    echo     %REQUIREMENTS%
    echo.
    echo   リポジトリが正しくクローンされているか確認してください。
    pause
    exit /b 1
)

echo   依存関係をインストール中...
"%VENV_PIP%" install --upgrade -r "%REQUIREMENTS%"
if !errorlevel! neq 0 (
    echo.
    echo   ✗ インストールに失敗しました
    echo   ネットワーク接続を確認してください。
    pause
    exit /b 1
)
echo.
echo     ✓ インストール完了
echo.

REM ========================================
REM bootstrap.py 実行
REM ========================================
echo ══════════════════════════════════════════════════════
echo.

if not exist "%SCRIPT_DIR%bootstrap.py" (
    echo   ✗ bootstrap.py が見つかりません
    echo     %SCRIPT_DIR%bootstrap.py
    pause
    exit /b 1
)

"%VENV_PYTHON%" "%SCRIPT_DIR%bootstrap.py" %*

endlocal
