/* ============================================================
   rumiai defaults — Dev Panel (P2-2)
   Ctrl+Shift+D でトグル表示
   /api/dev/inspect, /api/dev/edit-prompt, /api/dev/replay を使用
   ============================================================ */
(function(){
"use strict";

/* ---- CSS 注入 ---- */
var style = document.createElement("style");
style.textContent = [
  "#dev-panel-overlay{display:none;position:fixed;inset:0;z-index:3000;background:rgba(0,0,0,0.5);align-items:center;justify-content:center}",
  "#dev-panel-overlay.visible{display:flex}",
  "#dev-panel{background:var(--bg-secondary,#16213e);border:1px solid var(--border-color,#2a2a4a);border-radius:12px;padding:20px;width:600px;max-height:80vh;overflow-y:auto;color:var(--text-primary,#e8e8f0);font-family:inherit}",
  "#dev-panel h2{font-size:16px;margin-bottom:14px;display:flex;align-items:center;justify-content:space-between}",
  "#dev-panel .dp-close{width:28px;height:28px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px;cursor:pointer;border:none;background:none;color:inherit}",
  "#dev-panel .dp-close:hover{background:var(--bg-hover,#252550)}",
  ".dp-section{margin-bottom:16px;padding:12px;background:var(--bg-primary,#1a1a2e);border-radius:8px;border:1px solid var(--border-color,#2a2a4a)}",
  ".dp-section-title{font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:var(--text-muted,#707090);margin-bottom:8px;font-weight:600}",
  ".dp-row{display:flex;justify-content:space-between;padding:3px 0;font-size:13px}",
  ".dp-row-label{color:var(--text-muted,#707090)}",
  ".dp-row-value{color:var(--text-primary,#e8e8f0);font-weight:500;max-width:350px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}",
  ".dp-textarea{width:100%;min-height:100px;resize:vertical;padding:8px;font-size:13px;font-family:var(--font-mono,monospace);background:var(--bg-input,#1a1a3e);border:1px solid var(--border-color,#2a2a4a);border-radius:8px;color:var(--text-primary,#e8e8f0);outline:none}",
  ".dp-textarea:focus{border-color:var(--accent,#6c63ff)}",
  ".dp-btn{padding:6px 14px;border-radius:8px;font-size:12px;font-weight:600;cursor:pointer;border:none;transition:background 0.15s}",
  ".dp-btn-primary{background:var(--accent,#6c63ff);color:#fff}",
  ".dp-btn-primary:hover{background:var(--accent-hover,#7b73ff)}",
  ".dp-btn-secondary{background:var(--bg-active,#2a2a5a);color:var(--text-secondary,#a0a0c0)}",
  ".dp-btn-secondary:hover{background:var(--bg-hover,#252550)}",
  ".dp-actions{display:flex;gap:8px;margin-top:8px}",
  ".dp-status{font-size:11px;color:var(--text-muted,#707090);margin-top:6px}",
  ".dp-kbd{display:inline-block;padding:1px 5px;border-radius:3px;background:var(--bg-active,#2a2a5a);font-size:10px;font-family:var(--font-mono,monospace);color:var(--text-muted,#707090);margin-left:8px}"
].join("\n");
document.head.appendChild(style);

/* ---- HTML 注入 ---- */
var overlay = document.createElement("div");
overlay.id = "dev-panel-overlay";
overlay.innerHTML = [
  '<div id="dev-panel">',
  '  <h2>Dev Panel<span class="dp-kbd">Ctrl+Shift+D</span><button class="dp-close" id="dp-close">&#10005;</button></h2>',
  '  <div class="dp-section" id="dp-inspect-section">',
  '    <div class="dp-section-title">Last Request</div>',
  '    <div id="dp-inspect-body"><span style="color:var(--text-muted)">Loading...</span></div>',
  '    <div class="dp-actions"><button class="dp-btn dp-btn-secondary" id="dp-refresh">Refresh</button></div>',
  '  </div>',
  '  <div class="dp-section">',
  '    <div class="dp-section-title">Edit System Prompt</div>',
  '    <textarea class="dp-textarea" id="dp-prompt-input" placeholder="System prompt..."></textarea>',
  '    <div class="dp-actions">',
  '      <button class="dp-btn dp-btn-primary" id="dp-prompt-save">Save</button>',
  '      <button class="dp-btn dp-btn-secondary" id="dp-prompt-load">Load Current</button>',
  '    </div>',
  '    <div class="dp-status" id="dp-prompt-status"></div>',
  '  </div>',
  '  <div class="dp-section">',
  '    <div class="dp-section-title">Replay Last Request</div>',
  '    <div class="dp-actions">',
  '      <button class="dp-btn dp-btn-primary" id="dp-replay">Replay</button>',
  '      <button class="dp-btn dp-btn-secondary" id="dp-replay-edited">Replay with edited prompt</button>',
  '    </div>',
  '    <div class="dp-status" id="dp-replay-status"></div>',
  '  </div>',
  '</div>'
].join("\n");
document.body.appendChild(overlay);

/* ---- State ---- */
var lastInspect = null;

/* ---- API helpers ---- */
function apiFetch(url, opts){
  opts = opts || {};
  var fetchOpts = {method: opts.method || "GET", headers:{"Content-Type":"application/json"}};
  if(opts.body !== undefined) fetchOpts.body = JSON.stringify(opts.body);
  return fetch(url, fetchOpts).then(function(r){ return r.json(); }).then(function(d){
    if(d.status === "error") throw new Error((d.error && d.error.message) || "Unknown error");
    return d.data;
  });
}

/* ---- Inspect ---- */
function loadInspect(){
  var body = document.getElementById("dp-inspect-body");
  body.innerHTML = '<span style="color:var(--text-muted)">Loading...</span>';
  apiFetch("/api/dev/inspect").then(function(data){
    lastInspect = data;
    if(!data || !data.request_id){
      body.innerHTML = '<span style="color:var(--text-muted)">No requests logged yet</span>';
      return;
    }
    body.innerHTML = [
      '<div class="dp-row"><span class="dp-row-label">Request ID</span><span class="dp-row-value">' + esc(data.request_id) + '</span></div>',
      '<div class="dp-row"><span class="dp-row-label">Model</span><span class="dp-row-value">' + esc(data.model) + '</span></div>',
      '<div class="dp-row"><span class="dp-row-label">Conversation</span><span class="dp-row-value">' + esc(data.conversation_id || "-") + '</span></div>',
      '<div class="dp-row"><span class="dp-row-label">Prompt</span><span class="dp-row-value" title="' + esc(data.prompt_used) + '">' + esc((data.prompt_used || "").substring(0, 80)) + '</span></div>',
      '<div class="dp-row"><span class="dp-row-label">Tools</span><span class="dp-row-value">' + esc(JSON.stringify(data.tools_called || [])) + '</span></div>',
      '<div class="dp-row"><span class="dp-row-label">Timestamp</span><span class="dp-row-value">' + esc(data.timestamp) + '</span></div>'
    ].join("");
    // プロンプトテキストエリアにも反映
    var ta = document.getElementById("dp-prompt-input");
    if(ta && !ta.value) ta.value = data.prompt_used || "";
  }).catch(function(e){
    body.innerHTML = '<span style="color:var(--danger,#e74c3c)">Error: ' + esc(e.message) + '</span>';
  });
}

/* ---- Prompt edit ---- */
function savePrompt(){
  var ta = document.getElementById("dp-prompt-input");
  var status = document.getElementById("dp-prompt-status");
  var body = ta.value;
  status.textContent = "Saving...";
  apiFetch("/api/dev/edit-prompt", {method:"POST", body:{prompt_name:"system", new_body: body}}).then(function(){
    status.textContent = "Saved!";
    setTimeout(function(){ status.textContent = ""; }, 2000);
  }).catch(function(e){
    status.textContent = "Error: " + e.message;
  });
}

function loadCurrentPrompt(){
  var ta = document.getElementById("dp-prompt-input");
  var status = document.getElementById("dp-prompt-status");
  status.textContent = "Loading...";
  apiFetch("/api/dev/inspect").then(function(data){
    ta.value = (data && data.prompt_used) ? data.prompt_used : "";
    status.textContent = "Loaded";
    setTimeout(function(){ status.textContent = ""; }, 2000);
  }).catch(function(e){
    status.textContent = "Error: " + e.message;
  });
}

/* ---- Replay ---- */
function doReplay(useEditedPrompt){
  var status = document.getElementById("dp-replay-status");
  if(!lastInspect || !lastInspect.request_id){
    status.textContent = "No request to replay";
    return;
  }
  var overrides = {};
  if(useEditedPrompt){
    var ta = document.getElementById("dp-prompt-input");
    overrides.system_prompt = ta.value;
  }
  status.textContent = "Replaying...";
  apiFetch("/api/dev/replay", {method:"POST", body:{request_id: lastInspect.request_id, overrides: overrides}}).then(function(data){
    status.textContent = "Replay complete! ID: " + (data.replay_request_id || "?");
    loadInspect();
  }).catch(function(e){
    status.textContent = "Error: " + e.message;
  });
}

function esc(s){
  if(!s) return "";
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

/* ---- Toggle ---- */
function toggleDevPanel(){
  var el = document.getElementById("dev-panel-overlay");
  if(el.classList.contains("visible")){
    el.classList.remove("visible");
  } else {
    el.classList.add("visible");
    loadInspect();
  }
}

/* ---- Event bindings ---- */
document.addEventListener("keydown", function(e){
  if(e.ctrlKey && e.shiftKey && e.key === "D"){
    e.preventDefault();
    toggleDevPanel();
  }
});

document.getElementById("dp-close").addEventListener("click", function(){
  document.getElementById("dev-panel-overlay").classList.remove("visible");
});

document.getElementById("dev-panel-overlay").addEventListener("click", function(e){
  if(e.target === this) this.classList.remove("visible");
});

document.getElementById("dp-refresh").addEventListener("click", loadInspect);
document.getElementById("dp-prompt-save").addEventListener("click", savePrompt);
document.getElementById("dp-prompt-load").addEventListener("click", loadCurrentPrompt);
document.getElementById("dp-replay").addEventListener("click", function(){ doReplay(false); });
document.getElementById("dp-replay-edited").addEventListener("click", function(){ doReplay(true); });

})();
