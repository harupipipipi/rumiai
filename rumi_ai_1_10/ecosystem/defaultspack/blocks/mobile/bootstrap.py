"""blocks.mobile.bootstrap — モバイルクライアント起動時情報。

PCへ接続したスマホが最初に呼ぶ。サーバー情報・ capabilities フラグ・
イベントカーソルを返す。カタログ本体は /api/mobile/v1/capabilities で別途取得。

入力: なし
出力:
  {
    "status": "ok",
    "data": {
      "server": {"device_id": ..., "label": ..., "version": ...},
      "capabilities": {"chat": true, "tools": true, "approvals": ..., "credential_transfer": ...},
      "cursor": "event-..."
    }
  }
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import ok


def _server_info() -> dict:
    label = os.environ.get("RUMI_DEVICE_LABEL") or os.environ.get("RUMI_PC_LABEL") or "MacBook"
    device_id = os.environ.get("RUMI_DEVICE_ID") or "rumi-pc"
    version = os.environ.get("RUMI_VERSION") or "unknown"
    return {"device_id": device_id, "label": label, "version": version}


def run(input_data, context):
    del input_data, context
    return ok(
        {
            "server": _server_info(),
            "capabilities": {
                "chat": True,
                "tools": True,
                "approvals": True,
                "credential_transfer": True,
            },
            "cursor": "event-0",
        }
    )
