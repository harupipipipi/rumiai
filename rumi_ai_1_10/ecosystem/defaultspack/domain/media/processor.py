"""Media処理ドメインロジック"""

import os
import shutil
import subprocess
import sys


def read_image(path):
    """画像メタデータを取得する（スタブ実装）。

    pathの存在チェックを行い、存在すればファイルサイズを取得する。
    width / height / format はダミー値を返す。

    Args:
        path: 画像ファイルパス

    Returns:
        dict: 画像メタデータ

    Raises:
        FileNotFoundError: パスが存在しない場合
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Image not found: {path}")

    size_bytes = os.path.getsize(path)

    # スタブ: 実際のデコードは行わずダミー値を返す
    ext = os.path.splitext(path)[1].lstrip(".").upper() or "UNKNOWN"
    return {
        "path": path,
        "width": 0,
        "height": 0,
        "format": ext,
        "size_bytes": size_bytes,
    }


def transform_image(path, operations):
    """画像変換（スタブ実装）。

    operations を記録して返すだけで実際の変換は行わない。

    Args:
        path: 画像ファイルパス
        operations: 適用する変換操作のリスト

    Returns:
        dict: 変換結果情報
    """
    applied = [op.get("type", "unknown") for op in (operations or [])]
    return {
        "output_path": path,
        "operations_applied": applied,
    }


def parse_document(path):
    """ドキュメントをパースする（スタブ実装）。

    Args:
        path: ドキュメントファイルパス

    Returns:
        str: パースされたコンテンツ文字列
    """
    return f"parsed content from {path}"


def read_clipboard():
    """クリップボードを読み取る。

    Returns:
        str: クリップボードの内容
    """
    if sys.platform == "darwin":
        completed = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True)
        return completed.stdout
    if os.name == "nt":
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout
    for command in ("wl-paste", "xclip", "xsel"):
        if shutil.which(command):
            args = [command]
            if command == "xclip":
                args.extend(["-selection", "clipboard", "-out"])
            elif command == "xsel":
                args.extend(["--clipboard", "--output"])
            completed = subprocess.run(args, capture_output=True, text=True, check=True)
            return completed.stdout
    raise RuntimeError("system clipboard reader is not available")


def write_clipboard(content):
    """クリップボードに書き込む。

    Args:
        content: 書き込む内容

    Returns:
        bool: 成功した場合 True
    """
    text = str(content)
    if sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=text, text=True, check=True)
        return True
    if os.name == "nt":
        subprocess.run(["clip"], input=text, text=True, check=True)
        return True
    for command in ("wl-copy", "xclip", "xsel"):
        if shutil.which(command):
            args = [command]
            if command == "xclip":
                args.extend(["-selection", "clipboard"])
            elif command == "xsel":
                args.extend(["--clipboard", "--input"])
            subprocess.run(args, input=text, text=True, check=True)
            return True
    raise RuntimeError("system clipboard writer is not available")


def take_screenshot():
    """スクリーンショットを撮る（スタブ実装）。

    Returns:
        dict: スクリーンショット情報
    """
    return {
        "path": "/tmp/screenshot.png",
        "width": 1920,
        "height": 1080,
    }
