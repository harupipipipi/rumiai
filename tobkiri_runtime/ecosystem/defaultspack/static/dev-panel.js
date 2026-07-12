/* ============================================================
   rumiai defaults — Dev Panel
   Ctrl+Shift+D でトグル表示する開発者ツール
   ============================================================ */
(function(){
"use strict";

/* --- State --- */
var devState = {
  visible: false,
  inspectData: null,
  historyData: null,
  activeTab: "inspect", // "inspect" | "history" | "edit"
  editPromptName: "",
  editPromptBody: "",
};

var baseUrl = window.location.origin;

/* --- API helpers --- */
function devFetch(url, opts){
  opts = opts || {};
  var fetchOpts = {
    method: opts.method || "GET",
    headers: {"Content-Type":"application/json"}
  };
  if(opts.body !== undefined) fetchOpts.body = JSON.stringify(opts.body);
  return fetch(baseUrl + url, fetchOpts).then(function(res){ return res.json(); });
}

function fetchInspect(){
  devFetch("/api/dev/inspect").then(function(res){
    devState.inspectData = (res.status === "ok") ? res.data : null;
    renderDevPanel();
  }).catch(function(){ devState.inspectData = null; renderDevPanel(); });
}

function fetchHistory(){
  devFetch("/api/dev/prompt-history").then(function(res){
    devState.historyData = (res.status === "ok") ? res.data : null;
    renderDevPanel();
  }).catch(function(){ devState.historyData = null; renderDevPanel(); });
}

function editPromptLive(name, body){
  devFetch("/api/dev/edit-prompt", {
    method: "POST",
    body: { prompt_name: name, new_body: body }
  }).then(function(res){
    if(res.status === "ok"){
      devShowToast("Prompt updated: " + name, "success");
      fetchInspect();
    } else {
      devShowToast("Error: " + ((res.error && res.error.message) || "unknown"), "error");
    }
  }).catch(function(err){ devShowToast("Error: " + err.message, "error"); });
}

function replayRequest(requestId, overrides){
  devFetch("/api/dev/replay", {
    method: "POST",
    body: { request_id: requestId, overrides: overrides || {} }
  }).then(function(res){
    if(res.status === "ok"){
      devState.inspectData = res.data;
      devState.activeTab = "inspect";
      devShowToast("Replay complete", "success");
      renderDevPanel();
    } else {
      devShowToast("Replay error: " + ((res.error && res.error.message) || "unknown"), "error");
    }
  }).catch(function(err){ devShowToast("Replay error: " + err.message, "error"); });
}

/* --- Toast (reuses existing toast container) --- */
function devShowToast(msg, type){
  if(typeof window.showToast === "function"){
    window.showToast(msg, type);
    return;
  }
  var container = document.getElementById("toast-container");
  if(!container) return;
  var el = document.createElement("div");
  el.className = "toast " + (type || "info");
  el.textContent = msg;
  container.appendChild(el);
  setTimeout(function(){ if(el.parentNode) el.parentNode.removeChild(el); }, 4000);
}

/* --- Escape HTML --- */
function esc(s){
  if(!s) return "";
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

/* --- Render --- */
function renderDevPanel(){
  var panel = document.getElementById("dev-panel");
  if(!panel) return;
  panel.style.display = devState.visible ? "flex" : "none";

  var body = document.getElementById("dev-panel-body");
  if(!body) return;

  var html = "";

  // Tab bar
  html += '<div class="dev-tabs">';
  html += '<button class="dev-tab' + (devState.activeTab==="inspect"?" active":"") + '" data-dev-tab="inspect">Inspect</button>';
  html += '<button class="dev-tab' + (devState.activeTab==="history"?" active":"") + '" data-dev-tab="history">History</button>';
  html += '<button class="dev-tab' + (devState.activeTab==="edit"?" active":"") + '" data-dev-tab="edit">Edit Prompt</button>';
  html += '</div>';

  // Tab content
  if(devState.activeTab === "inspect"){
    html += renderInspectTab();
  } else if(devState.activeTab === "history"){
    html += renderHistoryTab();
  } else if(devState.activeTab === "edit"){
    html += renderEditTab();
  }

  body.innerHTML = html;
  bindDevEvents(body);
}

function renderInspectTab(){
  var d = devState.inspectData;
  var html = '<div class="dev-section">';
  if(!d || (!d.request_id && !d.replay_result)){
    html += '<p class="dev-muted">No request data yet. Send a message first, then inspect.</p>';
    html += '<button class="dev-btn dev-btn-primary" id="dev-refresh-inspect">Refresh</button>';
    html += '</div>';
    return html;
  }

  // If it's a replay result
  if(d.replay_result){
    html += '<h4 class="dev-h4">Replay Result</h4>';
    html += '<div class="dev-kv"><span class="dev-key">Replay Request ID:</span> <span class="dev-val">' + esc(d.replay_request_id) + '</span></div>';
    if(d.overrides_applied && Object.keys(d.overrides_applied).length > 0){
      html += '<div class="dev-kv"><span class="dev-key">Overrides:</span> <pre class="dev-pre">' + esc(JSON.stringify(d.overrides_applied, null, 2)) + '</pre></div>';
    }
    html += '<div class="dev-kv"><span class="dev-key">Result:</span> <pre class="dev-pre">' + esc(JSON.stringify(d.replay_result, null, 2)) + '</pre></div>';
    html += '<h4 class="dev-h4">Original Request</h4>';
    d = d.original;
  }

  html += '<div class="dev-kv"><span class="dev-key">Request ID:</span> <span class="dev-val">' + esc(d.request_id) + '</span></div>';
  html += '<div class="dev-kv"><span class="dev-key">Conversation:</span> <span class="dev-val">' + esc(d.conversation_id || "N/A") + '</span></div>';
  html += '<div class="dev-kv"><span class="dev-key">Model:</span> <span class="dev-val">' + esc(d.model) + '</span></div>';
  html += '<div class="dev-kv"><span class="dev-key">Timestamp:</span> <span class="dev-val">' + esc(d.timestamp) + '</span></div>';

  // Prompt used
  html += '<h4 class="dev-h4">Prompt Used</h4>';
  html += '<pre class="dev-pre dev-prompt-preview">' + esc(d.prompt_used || "(none)") + '</pre>';

  // Tools called
  html += '<h4 class="dev-h4">Tools Called</h4>';
  if(d.tools_called && d.tools_called.length > 0){
    html += '<ul class="dev-list">';
    for(var i = 0; i < d.tools_called.length; i++){
      var t = d.tools_called[i];
      html += '<li>' + esc(typeof t === "string" ? t : JSON.stringify(t)) + '</li>';
    }
    html += '</ul>';
  } else {
    html += '<p class="dev-muted">No tools called</p>';
  }

  // Context info
  if(d.context_info && Object.keys(d.context_info).length > 0){
    html += '<h4 class="dev-h4">Context Info</h4>';
    html += '<pre class="dev-pre">' + esc(JSON.stringify(d.context_info, null, 2)) + '</pre>';
  }

  // Actions
  html += '<div class="dev-actions">';
  html += '<button class="dev-btn dev-btn-primary" id="dev-refresh-inspect">Refresh</button>';
  if(d.request_id){
    html += '<button class="dev-btn dev-btn-accent" id="dev-replay-btn" data-rid="' + esc(d.request_id) + '">Replay</button>';
  }
  html += '</div>';

  html += '</div>';
  return html;
}

function renderHistoryTab(){
  var html = '<div class="dev-section">';
  html += '<div class="dev-actions"><button class="dev-btn dev-btn-primary" id="dev-refresh-history">Refresh History</button></div>';

  var d = devState.historyData;
  if(!d || !d.history || d.history.length === 0){
    html += '<p class="dev-muted">No prompt usage history.</p>';
    html += '</div>';
    return html;
  }

  html += '<table class="dev-table"><thead><tr>';
  html += '<th>Time</th><th>Model</th><th>Conversation</th><th>Prompt</th><th>Tools</th><th></th>';
  html += '</tr></thead><tbody>';

  for(var i = 0; i < d.history.length; i++){
    var h = d.history[i];
    var promptPreview = (h.prompt_used || "").substring(0, 60);
    if((h.prompt_used || "").length > 60) promptPreview += "...";
    var toolNames = (h.tools_called || []).map(function(t){ return typeof t === "string" ? t : (t.name || "?"); }).join(", ");
    html += '<tr>';
    html += '<td class="dev-td-sm">' + esc(h.timestamp || "") + '</td>';
    html += '<td>' + esc(h.model) + '</td>';
    html += '<td class="dev-td-sm">' + esc((h.conversation_id || "").substring(0, 8)) + '</td>';
    html += '<td class="dev-td-prompt">' + esc(promptPreview) + '</td>';
    html += '<td class="dev-td-sm">' + esc(toolNames || "-") + '</td>';
    html += '<td><button class="dev-btn dev-btn-sm" data-dev-inspect-rid="' + esc(h.request_id) + '">Inspect</button></td>';
    html += '</tr>';
  }

  html += '</tbody></table></div>';
  return html;
}

function renderEditTab(){
  var html = '<div class="dev-section">';
  html += '<h4 class="dev-h4">Edit Prompt (Live)</h4>';
  html += '<p class="dev-muted">Enter a prompt name (or "system" for system prompt) and the new body. Changes apply immediately.</p>';
  html += '<div class="dev-form-group">';
  html += '<label class="dev-label">Prompt Name</label>';
  html += '<input type="text" class="dev-input" id="dev-edit-name" placeholder="system" value="' + esc(devState.editPromptName) + '">';
  html += '</div>';
  html += '<div class="dev-form-group">';
  html += '<label class="dev-label">Prompt Body</label>';
  html += '<textarea class="dev-textarea" id="dev-edit-body" rows="10" placeholder="Enter prompt content...">' + esc(devState.editPromptBody) + '</textarea>';
  html += '</div>';
  html += '<div class="dev-actions">';
  html += '<button class="dev-btn dev-btn-accent" id="dev-apply-edit">Apply</button>';
  html += '</div>';
  html += '</div>';
  return html;
}

/* --- Event binding --- */
function bindDevEvents(container){
  // Tab switching
  var tabs = container.querySelectorAll("[data-dev-tab]");
  for(var i = 0; i < tabs.length; i++){
    tabs[i].addEventListener("click", function(e){
      devState.activeTab = this.getAttribute("data-dev-tab");
      if(devState.activeTab === "history" && !devState.historyData) fetchHistory();
      renderDevPanel();
    });
  }

  // Refresh inspect
  var refreshBtn = document.getElementById("dev-refresh-inspect");
  if(refreshBtn) refreshBtn.addEventListener("click", function(){ fetchInspect(); });

  // Refresh history
  var refreshHistBtn = document.getElementById("dev-refresh-history");
  if(refreshHistBtn) refreshHistBtn.addEventListener("click", function(){ fetchHistory(); });

  // Replay button
  var replayBtn = document.getElementById("dev-replay-btn");
  if(replayBtn){
    replayBtn.addEventListener("click", function(){
      var rid = this.getAttribute("data-rid");
      if(!rid) return;
      var overrideModel = prompt("Override model (leave empty for same):");
      var overridePrompt = prompt("Override system prompt (leave empty for same):");
      var overrides = {};
      if(overrideModel) overrides.model = overrideModel;
      if(overridePrompt) overrides.system_prompt = overridePrompt;
      replayRequest(rid, overrides);
    });
  }

  // Inspect from history
  var inspectBtns = container.querySelectorAll("[data-dev-inspect-rid]");
  for(var j = 0; j < inspectBtns.length; j++){
    inspectBtns[j].addEventListener("click", function(){
      var rid = this.getAttribute("data-dev-inspect-rid");
      devFetch("/api/dev/inspect?request_id=" + encodeURIComponent(rid)).then(function(res){
        if(res.status === "ok"){
          devState.inspectData = res.data;
          devState.activeTab = "inspect";
          renderDevPanel();
        }
      });
    });
  }

  // Edit prompt apply
  var applyBtn = document.getElementById("dev-apply-edit");
  if(applyBtn){
    applyBtn.addEventListener("click", function(){
      var nameEl = document.getElementById("dev-edit-name");
      var bodyEl = document.getElementById("dev-edit-body");
      if(!nameEl || !bodyEl) return;
      var name = nameEl.value.trim();
      var body = bodyEl.value;
      if(!name){ devShowToast("Prompt name is required", "error"); return; }
      devState.editPromptName = name;
      devState.editPromptBody = body;
      editPromptLive(name, body);
    });
  }
}

/* --- Inject CSS --- */
function injectDevStyles(){
  var style = document.createElement("style");
  style.textContent = [
    "/* ====== Dev Panel ====== */",
    "#dev-panel{",
    "  display:none;position:fixed;right:0;top:0;bottom:0;width:480px;z-index:3000;",
    "  background:var(--bg-secondary,#16213e);border-left:2px solid var(--accent,#6c63ff);",
    "  flex-direction:column;overflow:hidden;",
    "  box-shadow:-4px 0 24px rgba(0,0,0,0.5);",
    "  font-family:var(--font-family,system-ui,sans-serif);font-size:13px;color:var(--text-primary,#e8e8f0);",
    "}",
    "#dev-panel-header{",
    "  padding:10px 16px;border-bottom:1px solid var(--border-color,#2a2a4a);",
    "  display:flex;align-items:center;justify-content:space-between;flex-shrink:0;",
    "  background:var(--bg-tertiary,#0f3460);",
    "}",
    "#dev-panel-header h3{font-size:14px;font-weight:700;color:var(--accent,#6c63ff);margin:0}",
    "#dev-panel-header .dev-shortcut{font-size:11px;color:var(--text-muted,#707090);margin-left:8px}",
    "#dev-panel-close{",
    "  width:28px;height:28px;border-radius:6px;border:none;background:none;",
    "  color:var(--text-secondary,#a0a0c0);cursor:pointer;display:flex;align-items:center;justify-content:center;",
    "  font-size:16px;transition:background 0.15s;",
    "}",
    "#dev-panel-close:hover{background:var(--bg-hover,#252550)}",
    "#dev-panel-body{flex:1;overflow-y:auto;padding:12px 16px}",
    ".dev-tabs{display:flex;gap:2px;margin-bottom:12px;border-bottom:1px solid var(--border-color,#2a2a4a);padding-bottom:8px}",
    ".dev-tab{",
    "  padding:6px 14px;border-radius:6px 6px 0 0;border:none;background:none;",
    "  color:var(--text-secondary,#a0a0c0);cursor:pointer;font-size:12px;font-weight:600;",
    "  transition:background 0.15s,color 0.15s;",
    "}",
    ".dev-tab:hover{background:var(--bg-hover,#252550);color:var(--text-primary,#e8e8f0)}",
    ".dev-tab.active{background:var(--bg-active,#2a2a5a);color:var(--accent,#6c63ff)}",
    ".dev-section{margin-bottom:16px}",
    ".dev-h4{font-size:12px;font-weight:700;color:var(--accent,#6c63ff);margin:12px 0 6px;text-transform:uppercase;letter-spacing:0.5px}",
    ".dev-kv{padding:4px 0;display:flex;flex-wrap:wrap;gap:4px;align-items:baseline}",
    ".dev-key{font-size:11px;color:var(--text-muted,#707090);font-weight:600;min-width:120px}",
    ".dev-val{font-size:13px;color:var(--text-primary,#e8e8f0);word-break:break-all}",
    ".dev-pre{",
    "  background:var(--bg-primary,#1a1a2e);padding:10px 12px;border-radius:6px;",
    "  font-family:var(--font-mono,'SF Mono',monospace);font-size:12px;line-height:1.5;",
    "  overflow-x:auto;white-space:pre-wrap;word-break:break-all;",
    "  border:1px solid var(--border-color,#2a2a4a);margin:4px 0;max-height:300px;overflow-y:auto;",
    "}",
    ".dev-prompt-preview{max-height:200px}",
    ".dev-muted{color:var(--text-muted,#707090);font-size:12px;margin:8px 0}",
    ".dev-list{list-style:none;padding:0;margin:4px 0}",
    ".dev-list li{padding:3px 0;font-size:12px;color:var(--text-secondary,#a0a0c0)}",
    ".dev-list li::before{content:'\\2022';color:var(--accent,#6c63ff);margin-right:8px}",
    ".dev-actions{display:flex;gap:8px;margin-top:12px}",
    ".dev-btn{",
    "  padding:6px 14px;border-radius:6px;border:1px solid var(--border-color,#2a2a4a);",
    "  background:var(--bg-active,#2a2a5a);color:var(--text-primary,#e8e8f0);",
    "  cursor:pointer;font-size:12px;font-weight:600;transition:background 0.15s;",
    "}",
    ".dev-btn:hover{background:var(--bg-hover,#252550)}",
    ".dev-btn-primary{background:var(--info,#3498db);color:#fff;border-color:var(--info,#3498db)}",
    ".dev-btn-primary:hover{background:#2980b9}",
    ".dev-btn-accent{background:var(--accent,#6c63ff);color:#fff;border-color:var(--accent,#6c63ff)}",
    ".dev-btn-accent:hover{background:var(--accent-hover,#7b73ff)}",
    ".dev-btn-sm{padding:3px 8px;font-size:11px}",
    ".dev-table{width:100%;border-collapse:collapse;font-size:12px;margin-top:8px}",
    ".dev-table th{",
    "  text-align:left;padding:6px 8px;border-bottom:2px solid var(--border-color,#2a2a4a);",
    "  color:var(--text-muted,#707090);font-size:11px;text-transform:uppercase;letter-spacing:0.3px;",
    "}",
    ".dev-table td{padding:6px 8px;border-bottom:1px solid var(--border-color,#2a2a4a);vertical-align:top}",
    ".dev-table tr:hover td{background:var(--bg-hover,#252550)}",
    ".dev-td-sm{font-size:11px;color:var(--text-muted,#707090);max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
    ".dev-td-prompt{max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
    ".dev-form-group{margin-bottom:10px}",
    ".dev-label{display:block;font-size:11px;font-weight:600;color:var(--text-muted,#707090);margin-bottom:4px;text-transform:uppercase}",
    ".dev-input{",
    "  width:100%;padding:8px 10px;font-size:13px;",
    "  background:var(--bg-input,#1a1a3e);color:var(--text-primary,#e8e8f0);",
    "  border:1px solid var(--border-color,#2a2a4a);border-radius:6px;outline:none;",
    "}",
    ".dev-input:focus{border-color:var(--accent,#6c63ff)}",
    ".dev-textarea{",
    "  width:100%;padding:8px 10px;font-size:13px;line-height:1.5;resize:vertical;",
    "  background:var(--bg-input,#1a1a3e);color:var(--text-primary,#e8e8f0);",
    "  border:1px solid var(--border-color,#2a2a4a);border-radius:6px;outline:none;",
    "  font-family:var(--font-mono,'SF Mono',monospace);",
    "}",
    ".dev-textarea:focus{border-color:var(--accent,#6c63ff)}",
    "@media(max-width:600px){#dev-panel{width:100%}}",
  ].join("\n");
  document.head.appendChild(style);
}

/* --- Inject HTML --- */
function injectDevPanel(){
  var panel = document.createElement("div");
  panel.id = "dev-panel";
  panel.innerHTML = [
    '<div id="dev-panel-header">',
    '  <h3>Dev Tools <span class="dev-shortcut">Ctrl+Shift+D</span></h3>',
    '  <button id="dev-panel-close" title="Close">&#10005;</button>',
    '</div>',
    '<div id="dev-panel-body"></div>',
  ].join("");
  document.body.appendChild(panel);

  document.getElementById("dev-panel-close").addEventListener("click", function(){
    devState.visible = false;
    renderDevPanel();
  });
}

/* --- Keyboard shortcut --- */
function bindDevKeyboard(){
  document.addEventListener("keydown", function(e){
    if(e.ctrlKey && e.shiftKey && e.key === "D"){
      e.preventDefault();
      devState.visible = !devState.visible;
      if(devState.visible){
        fetchInspect();
      }
      renderDevPanel();
    }
  });
}

/* --- Init --- */
function initDevPanel(){
  injectDevStyles();
  injectDevPanel();
  bindDevKeyboard();
  renderDevPanel();
}

// Wait for DOM
if(document.readyState === "loading"){
  document.addEventListener("DOMContentLoaded", initDevPanel);
} else {
  initDevPanel();
}

})();
