#!/usr/bin/env python3
"""
Desktop App Pack — サンプルデスクトップアプリ

Rumi AI OS の desktop_app.execute capability を使ったデスクトップアプリのサンプルです。
pack-shell 経由で起動されると、環境変数 RUMI_TOKEN, RUMI_PORT, RUMI_PACK_ID が
自動的に設定されます。

使い方:
  pack-shell run desktop_app_pack --command "python app.py" --working-dir /path/to/desktop_app_pack --api-token "$TOKEN"

  または手動で環境変数を設定して直接起動:
  RUMI_TOKEN=xxx RUMI_PORT=8765 RUMI_PACK_ID=desktop_app_pack python app.py
"""

import json
import os
import tkinter as tk
from tkinter import scrolledtext
from urllib.error import URLError
from urllib.request import Request, urlopen


def get_rumi_env():
    """pack-shell が設定する環境変数を取得する。"""
    return {
        "RUMI_TOKEN": os.environ.get("RUMI_TOKEN", "(未設定)"),
        "RUMI_PORT": os.environ.get("RUMI_PORT", "8765"),
        "RUMI_PACK_ID": os.environ.get("RUMI_PACK_ID", "(未設定)"),
    }


def call_kernel_health(port):
    """Kernel の /health エンドポイントを呼び出す。"""
    url = f"http://127.0.0.1:{port}/health"
    req = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=5) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except URLError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}


class DesktopAppDemo:
    """tkinter ベースのデモアプリケーション。"""

    def __init__(self, root):
        self.root = root
        self.env = get_rumi_env()

        self.root.title("Desktop App Pack — Rumi AI OS サンプル")
        self.root.geometry("600x400")
        self.root.configure(bg="#0f172a")

        # ヘッダー
        header = tk.Label(
            root,
            text="Desktop App Pack",
            font=("Helvetica", 18, "bold"),
            fg="#38bdf8",
            bg="#0f172a",
        )
        header.pack(pady=(20, 5))

        subtitle = tk.Label(
            root,
            text="Rumi AI OS デスクトップアプリサンプル",
            font=("Helvetica", 10),
            fg="#94a3b8",
            bg="#0f172a",
        )
        subtitle.pack(pady=(0, 15))

        # 環境変数表示
        env_frame = tk.Frame(root, bg="#1e293b", highlightbackground="#334155", highlightthickness=1)
        env_frame.pack(padx=20, pady=5, fill="x")

        env_title = tk.Label(
            env_frame,
            text="環境変数（pack-shell から受け取り）",
            font=("Helvetica", 10, "bold"),
            fg="#38bdf8",
            bg="#1e293b",
            anchor="w",
        )
        env_title.pack(padx=10, pady=(8, 4), fill="x")

        for key, value in self.env.items():
            row = tk.Label(
                env_frame,
                text=f"  {key} = {value}",
                font=("Courier", 9),
                fg="#cbd5e1",
                bg="#1e293b",
                anchor="w",
            )
            row.pack(padx=10, pady=1, fill="x")

        tk.Label(env_frame, bg="#1e293b").pack(pady=4)

        # Health Check ボタン
        btn = tk.Button(
            root,
            text="Kernel Health Check を実行",
            font=("Helvetica", 10, "bold"),
            fg="#0f172a",
            bg="#38bdf8",
            activebackground="#818cf8",
            relief="flat",
            padx=16,
            pady=6,
            command=self.do_health_check,
        )
        btn.pack(pady=10)

        # 結果表示
        self.result_area = scrolledtext.ScrolledText(
            root,
            width=65,
            height=8,
            font=("Courier", 9),
            bg="#0f172a",
            fg="#94a3b8",
            insertbackground="#94a3b8",
            relief="flat",
            borderwidth=1,
        )
        self.result_area.pack(padx=20, pady=(5, 20), fill="both", expand=True)
        self.result_area.insert("1.0", "ボタンを押すと Kernel API の結果がここに表示されます。\n")
        self.result_area.configure(state="disabled")

    def do_health_check(self):
        """Health Check を実行して結果を表示する。"""
        port = self.env["RUMI_PORT"]
        self.result_area.configure(state="normal")
        self.result_area.delete("1.0", tk.END)
        self.result_area.insert("1.0", f"GET http://127.0.0.1:{port}/health ...\n\n")
        self.root.update()

        result = call_kernel_health(port)
        formatted = json.dumps(result, indent=2, ensure_ascii=False)
        self.result_area.insert(tk.END, formatted + "\n")
        self.result_area.configure(state="disabled")


def main():
    root = tk.Tk()
    DesktopAppDemo(root)
    root.mainloop()


if __name__ == "__main__":
    main()
