/**
 * UIHistoryPanel
 */

import * as api from '../api.js';
import { formatRelativeTime } from '../utils.js';

let panelEl = null;
let isVisible = false;
let uiHistory = null;

export function initUIHistoryPanel(container) { panelEl = container; }

export async function loadUIHistory(chatId) {
  if (!chatId) { uiHistory = null; return; }
  try { uiHistory = await api.getUIHistory(chatId); }
  catch (e) { uiHistory = { tool_logs: [], ui_state: {} }; }
}

export function toggleUIHistoryPanel() { isVisible = !isVisible; renderPanel(); return isVisible; }
export function showUIHistoryPanel() { isVisible = true; renderPanel(); }
export function hideUIHistoryPanel() { isVisible = false; renderPanel(); }
export function isUIHistoryVisible() { return isVisible; }

function renderPanel() {
  if (!panelEl) return;
  if (!isVisible) { panelEl.innerHTML = ''; panelEl.classList.remove('visible'); return; }
  panelEl.classList.add('visible');
  const logs = uiHistory?.tool_logs || [];
  
  const escapeHtml = (t) => { if (!t) return ''; const d = document.createElement('div'); d.textContent = t; return d.innerHTML; };
  
  panelEl.innerHTML = `
    <div class="ui-history-panel">
      <div class="ui-history-header">
        <h3>実行ログ</h3>
        <button class="btn-icon btn-close-panel" title="閉じる">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
      <div class="ui-history-content">
        ${logs.length === 0 ? '<div class="ui-history-empty"><p>実行ログはありません</p></div>' : `<div class="ui-history-logs">${logs.map(log => {
          const type = log.type || 'unknown';
          const timestamp = log.timestamp ? formatRelativeTime(new Date(log.timestamp * 1000).toISOString()) : '';
          const status = log.status || 'unknown';
          const statusClass = status === 'success' ? 'success' : status === 'error' ? 'error' : '';
          let icon = '📋';
          if (type === 'tool_call') icon = '🔧';
          if (type === 'tool_result') icon = '📤';
          if (type === 'error') icon = '❌';
          const details = log.details || log.result || log.args || null;
          const detailsJson = details ? JSON.stringify(details, null, 2) : null;
          return `<div class="log-entry ${statusClass}"><div class="log-entry-header"><span class="log-icon">${icon}</span><span class="log-type">${escapeHtml(log.function_name || type)}</span><span class="log-time">${timestamp}</span><span class="log-status ${statusClass}">${status}</span></div>${detailsJson ? `<div class="log-entry-details"><pre class="log-details-pre">${escapeHtml(detailsJson)}</pre></div>` : ''}</div>`;
        }).join('')}</div>`}
      </div>
    </div>
  `;
  
  panelEl.querySelector('.btn-close-panel')?.addEventListener('click', hideUIHistoryPanel);
  panelEl.querySelectorAll('.log-entry-header').forEach(el => {
    el.addEventListener('click', () => el.closest('.log-entry')?.classList.toggle('expanded'));
  });
}
