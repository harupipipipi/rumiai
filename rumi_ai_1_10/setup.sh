#!/usr/bin/env bash

# エラー時に即座に停止しない（手動でハンドリング）
set +e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
GUIDE_DIR="$SCRIPT_DIR/rumi_setup/guide"

echo ""
echo "══════════════════════════════════════════════════════"
echo "  🌸 Rumi AI セットアップ"
echo "══════════════════════════════════════════════════════"
echo ""

# ========================================
# ブラウザでファイルを開く関数
# ========================================
open_in_browser() {
    local file="$1"
    if [ ! -f "$file" ]; then
        return 1
    fi
    
    if command -v xdg-open &> /dev/null; then
        xdg-open "$file" 2>/dev/null &
    elif command -v open &> /dev/null; then
        open "$file" 2>/dev/null &
    else
        echo "  ブラウザで開いてください: $file"
        return 1
    fi
    return 0
}

# ========================================
# Python チェック (python3, python)
# ========================================
PYTHON_CMD=""

# python3 を優先
if command -v python3 &> /dev/null; then
    if python3 --version 2>&1 | grep -q "Python 3"; then
        PYTHON_CMD="python3"
    fi
fi

# python3 がなければ python を試す
if [ -z "$PYTHON_CMD" ]; then
    if command -v python &> /dev/null; then
        if python --version 2>&1 | grep -q "Python 3"; then
            PYTHON_CMD="python"
        fi
    fi
fi

# Python が見つからない場合
if [ -z "$PYTHON_CMD" ]; then
    echo "  ✗ Python 3 が見つかりません"
    echo ""
    echo "  Python は Rumi AI の実行に必須です。"
    echo "  インストールガイドを開きます..."
    echo ""
    
    if [ -f "$GUIDE_DIR/python.html" ]; then
        open_in_browser "$GUIDE_DIR/python.html"
    elif [ -f "$GUIDE_DIR/index.html" ]; then
        open_in_browser "$GUIDE_DIR/index.html"
    else
        echo "  https://www.python.org/ から Python をインストールしてください"
    fi
    
    echo ""
    echo "  Python をインストール後、再度実行してください。"
    exit 1
fi

echo "  ✓ Python: $PYTHON_CMD"
echo "    $($PYTHON_CMD --version 2>&1)"
echo ""

# ========================================
# Python バージョン確認 (3.9+)
# ========================================
PY_VERSION_OK=$($PYTHON_CMD -c "import sys; print(1 if sys.version_info >= (3, 9) else 0)" 2>/dev/null)

if [ "$PY_VERSION_OK" != "1" ]; then
    echo "  ✗ Python 3.9 以上が必要です"
    echo ""
    echo "  インストールガイドを開きます..."
    
    if [ -f "$GUIDE_DIR/python.html" ]; then
        open_in_browser "$GUIDE_DIR/python.html"
    fi
    
    exit 1
fi

# ========================================
# Git チェック
# ========================================
if ! command -v git &> /dev/null; then
    echo "  ✗ Git が見つかりません"
    echo ""
    echo "  Git は Pack のインストールに必要です。"
    echo "  インストールガイドを開きます..."
    echo ""
    
    if [ -f "$GUIDE_DIR/git.html" ]; then
        open_in_browser "$GUIDE_DIR/git.html"
    elif [ -f "$GUIDE_DIR/index.html" ]; then
        open_in_browser "$GUIDE_DIR/index.html"
    else
        echo "  https://git-scm.com/ から Git をインストールしてください"
    fi
    
    echo ""
    echo "  Git をインストール後、再度実行してください。"
    exit 1
fi

echo "  ✓ Git: $(git --version 2>&1)"
echo ""

# ========================================
# Docker チェック（任意）
# ========================================
if command -v docker &> /dev/null; then
    echo "  ✓ Docker: $(docker --version 2>&1 | head -n1)"
else
    echo "  ⚠ Docker: 見つかりません（推奨・任意）"
fi
echo ""

# ========================================
# 仮想環境の再作成
# ========================================
echo "  仮想環境をセットアップ中..."

# 既存の仮想環境を削除
if [ -d "$VENV_DIR" ]; then
    echo "    既存の .venv を削除中..."
    rm -rf "$VENV_DIR"
    
    # 削除確認
    if [ -d "$VENV_DIR" ]; then
        echo ""
        echo "    ✗ 削除に失敗しました"
        echo "    手動で削除してください: rm -rf $VENV_DIR"
        exit 1
    fi
    echo "    ✓ 削除完了"
fi

# 新しい仮想環境を作成
echo "    .venv を作成中..."
$PYTHON_CMD -m venv "$VENV_DIR"

if [ $? -ne 0 ]; then
    echo ""
    echo "    ✗ 仮想環境の作成に失敗しました"
    echo ""
    echo "    python3-venv パッケージが必要な場合があります:"
    echo "      Ubuntu/Debian: sudo apt install python3-venv"
    echo "      Fedora:        sudo dnf install python3-venv"
    echo "      Arch:          (通常は不要)"
    exit 1
fi
echo "    ✓ 作成完了"
echo ""

# ========================================
# 仮想環境の有効化
# ========================================
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "  ✗ 仮想環境の Python が見つかりません"
    echo "    $VENV_PYTHON"
    exit 1
fi

echo "  仮想環境を有効化中..."
source "$VENV_DIR/bin/activate"
echo "    ✓ 有効化完了"
echo ""

# ========================================
# pip アップグレード
# ========================================
echo "  pip をアップグレード中..."
"$VENV_PYTHON" -m pip install --upgrade pip > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "    ✓ pip アップグレード完了"
else
    echo "    ⚠ pip アップグレードをスキップ（続行します）"
fi
echo ""

# ========================================
# requirements.txt インストール
# ========================================
if [ ! -f "$REQUIREMENTS" ]; then
    echo "  ✗ requirements.txt が見つかりません"
    echo "    $REQUIREMENTS"
    echo ""
    echo "  リポジトリが正しくクローンされているか確認してください。"
    exit 1
fi

echo "  依存関係をインストール中..."
"$VENV_PIP" install --upgrade -r "$REQUIREMENTS"

if [ $? -ne 0 ]; then
    echo ""
    echo "  ✗ インストールに失敗しました"
    echo "  ネットワーク接続を確認してください。"
    exit 1
fi
echo ""
echo "    ✓ インストール完了"
echo ""

# ========================================
# bootstrap.py 実行
# ========================================
echo "══════════════════════════════════════════════════════"
echo ""

if [ ! -f "$SCRIPT_DIR/bootstrap.py" ]; then
    echo "  ✗ bootstrap.py が見つかりません"
    echo "    $SCRIPT_DIR/bootstrap.py"
    exit 1
fi

"$VENV_PYTHON" "$SCRIPT_DIR/bootstrap.py" "$@"
