/**
 * SettingsModal
 */

import * as api from '../api.js';
import { getState, setState } from '../store.js';
import { showModal, hideModal } from './Modal.js';

export async function openSettings() {
  let settings = {};
  try { settings = await api.getSettings(); } catch (e) { settings = {}; }
  setState({ settings });
  
  const theme = settings.theme || 'dark';
  const displayName = settings.display_name || '';
  const streamingEnabled = settings.streaming_enabled !== false;
  const enableNotifications = settings.enable_notifications !== false;
  
  const escapeAttr = (t) => (t || '').replace(/"/g, '&quot;');
  
  const content = `
    <div class="settings-form">
      <div class="settings-section">
        <h4 class="settings-section-title">表示</h4>
        <div class="settings-field">
          <label class="settings-label" for="setting-display-name">表示名</label>
          <input type="text" id="setting-display-name" class="settings-input" value="${escapeAttr(displayName)}" placeholder="名前を入力">
        </div>
        <div class="settings-field">
          <label class="settings-label" for="setting-theme">テーマ</label>
          <select id="setting-theme" class="settings-select">
            <option value="dark" ${theme === 'dark' ? 'selected' : ''}>ダーク</option>
            <option value="light" ${theme === 'light' ? 'selected' : ''}>ライト</option>
            <option value="system" ${theme === 'system' ? 'selected' : ''}>システム設定に従う</option>
          </select>
        </div>
      </div>
      <div class="settings-section">
        <h4 class="settings-section-title">動作</h4>
        <div class="settings-field">
          <label class="settings-checkbox-label">
            <input type="checkbox" id="setting-streaming" class="settings-checkbox" ${streamingEnabled ? 'checked' : ''}>
            <span class="settings-checkbox-text">ストリーミング応答を有効にする</span>
          </label>
        </div>
        <div class="settings-field">
          <label class="settings-checkbox-label">
            <input type="checkbox" id="setting-notifications" class="settings-checkbox" ${enableNotifications ? 'checked' : ''}>
            <span class="settings-checkbox-text">通知を有効にする</span>
          </label>
        </div>
      </div>
      <div class="settings-section">
        <h4 class="settings-section-title">システム情報</h4>
        <button type="button" class="settings-btn-link" id="btn-show-diagnostics">診断情報を表示</button>
      </div>
    </div>
  `;
  
  showModal({
    title: '設定',
    content,
    buttons: [
      { label: 'キャンセル', action: () => hideModal() },
      { label: '保存', primary: true, action: handleSave }
    ]
  });
  
  document.getElementById('setting-theme')?.addEventListener('change', (e) => applyTheme(e.target.value));
  document.getElementById('btn-show-diagnostics')?.addEventListener('click', handleShowDiagnostics);
}

async function handleSave() {
  const newSettings = {
    display_name: document.getElementById('setting-display-name')?.value?.trim() || '',
    theme: document.getElementById('setting-theme')?.value || 'dark',
    streaming_enabled: document.getElementById('setting-streaming')?.checked ?? true,
    enable_notifications: document.getElementById('setting-notifications')?.checked ?? true
  };
  try {
    await api.saveSettings(newSettings);
    setState({ settings: newSettings });
    applyTheme(newSettings.theme);
    hideModal();
  } catch (e) { alert('設定の保存に失敗しました: ' + e.message); }
}

export function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === 'system') theme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  if (theme === 'light') root.setAttribute('data-theme', 'light');
  else root.removeAttribute('data-theme');
}

async function handleShowDiagnostics() {
  try {
    const diagnostics = await api.getDiagnostics();
    const escapeHtml = (t) => { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; };
    hideModal();
    showModal({
      title: '診断情報',
      content: `<div class="diagnostics-content"><pre class="diagnostics-pre">${escapeHtml(JSON.stringify(diagnostics, null, 2))}</pre></div>`,
      buttons: [
        { label: '閉じる', action: () => { hideModal(); openSettings(); } },
        { label: 'コピー', primary: true, action: () => { navigator.clipboard.writeText(JSON.stringify(diagnostics, null, 2)); alert('コピーしました'); } }
      ]
    });
  } catch (e) { alert('診断情報の取得に失敗しました'); }
}

export async function initSettings() {
  try {
    const settings = await api.getSettings();
    setState({ settings });
    applyTheme(settings.theme || 'dark');
  } catch (e) {}
}
