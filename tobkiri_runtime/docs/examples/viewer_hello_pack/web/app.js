/**
 * Viewer Hello Pack — Kernel API 通信サンプル
 *
 * Rumi AI OS の Kernel API (localhost:8765) との通信デモです。
 * Pack 開発者はこのコードを参考に、独自のフロントエンドを実装できます。
 */

(function () {
  "use strict";

  // Kernel API のベース URL
  var KERNEL_API_BASE = "http://localhost:8765";

  // DOM 要素
  var statusDot = document.getElementById("status-dot");
  var statusText = document.getElementById("status-text");
  var apiResult = document.getElementById("api-result");

  /**
   * ステータス表示を更新する
   * @param {"ok"|"error"|"loading"} state - 状態
   * @param {string} message - 表示メッセージ
   */
  function setStatus(state, message) {
    statusDot.className = "status-dot " + state;
    statusText.textContent = message;
  }

  /**
   * API レスポンス表示を更新する
   * @param {string} text - 表示テキスト
   */
  function setResult(text) {
    apiResult.textContent = text;
  }

  /**
   * Kernel API への接続をテストする
   * /api/health エンドポイントに GET リクエストを送信します。
   */
  function testConnection() {
    setStatus("loading", "接続を確認中...");

    fetch(KERNEL_API_BASE + "/api/health", {
      method: "GET",
      headers: { "Accept": "application/json" }
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.json();
      })
      .then(function (data) {
        setStatus("ok", "Kernel API に接続できました");
        setResult(JSON.stringify(data, null, 2));
      })
      .catch(function (err) {
        setStatus("error", "接続できません: " + err.message);
        setResult(
          "Kernel API に接続できませんでした。\n" +
            "Rumi AI OS が起動していることを確認してください。\n\n" +
            "エラー: " + err.message
        );
      });
  }

  /**
   * Health Check エンドポイントを呼び出す
   * Kernel が正常に動作しているかを確認し、結果を表示します。
   */
  function fetchHealthCheck() {
    setResult("リクエスト送信中...");

    fetch(KERNEL_API_BASE + "/api/health", {
      method: "GET",
      headers: { "Accept": "application/json" }
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("HTTP " + response.status);
        }
        return response.json();
      })
      .then(function (data) {
        var lines = [
          "=== Health Check 結果 ===",
          "",
          "ステータス: " + (data.status || "不明"),
          "タイムスタンプ: " + new Date().toISOString(),
          "",
          "=== Raw レスポンス ===",
          JSON.stringify(data, null, 2)
        ];
        setResult(lines.join("\n"));
        setStatus("ok", "Kernel API に接続できました");
      })
      .catch(function (err) {
        setResult(
          "=== Health Check 失敗 ===\n\n" +
            "エラー: " + err.message + "\n\n" +
            "考えられる原因:\n" +
            "  - Rumi AI OS の Kernel が起動していない\n" +
            "  - ポート 8765 が異なる\n" +
            "  - ネットワーク接続の問題"
        );
        setStatus("error", "接続できません: " + err.message);
      });
  }

  // グローバルに公開（index.html の onclick から呼べるように）
  window.RumiApp = {
    testConnection: testConnection,
    fetchHealthCheck: fetchHealthCheck
  };

  // ページ読み込み時に自動で接続テスト
  testConnection();
})();
