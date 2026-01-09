// static/js/settings_handlers.js

import { state } from './state.js';
import { saveUserSettingsToServer } from './api.js';
import { applyTheme, updateAllUI, updatePromptSelectionUI, dom } from './ui.js';
import { escapeHtml } from './utils.js';
import { renderSupportersTab, saveSupportersSettings, handleReloadSupporters } from './ui_settings.js';

// 設定関連ハンドラ
export function handleThemeToggle() {
    state.userSettings.theme = document.documentElement.classList.contains('dark') ? 'light' : 'dark';
    applyTheme(state.userSettings.theme);
    saveUserSettingsToServer(state.userSettings);
}

export function handleModelChange(newModel) {
    console.log(`[DEBUG] モデル変更: ${state.userSettings.model} → ${newModel}`);
    
    state.userSettings.model = newModel;
    updateAllUI();
    saveUserSettingsToServer(state.userSettings);
    dom.modelSelectMenu.classList.remove('visible');
    
    // 変更通知を表示
    showModelChangeNotification(newModel);
}

/**
 * モデル変更通知を表示
 */
function showModelChangeNotification(modelId) {
    // モデル情報を取得
    const modelInfo = state.availableModels.find(m => m.id === modelId) || 
                     state.favoriteModels.find(m => m.id === modelId);
    
    if (!modelInfo) return;
    
    const notification = document.createElement('div');
    notification.className = 'fixed bottom-4 right-4 p-4 rounded-lg shadow-lg bg-blue-500 text-white z-50 animate-fadeIn';
    notification.innerHTML = `
        <div class="flex items-center gap-2">
            <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
            </svg>
            <div>
                <div class="font-semibold">${escapeHtml(modelInfo.name)}</div>
                <div class="text-xs opacity-90">${modelInfo.provider}</div>
            </div>
        </div>
    `;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

export function handleThinkingToggle() {
    if (dom.thinkingBtn.disabled) return;
    state.userSettings.thinking_on = !state.userSettings.thinking_on;
    updateAllUI();
    saveUserSettingsToServer(state.userSettings);
}

export function handlePromptChange(promptId) {
    state.currentPromptId = promptId;
    updatePromptSelectionUI();
    document.getElementById('prompt-select-menu').classList.remove('visible');
}

/**
 * 設定タブの切り替えを初期化
 */
export function initSettingsTabs() {
    document.querySelectorAll('.settings-tab').forEach(tab => {
        tab.addEventListener('click', async (e) => {
            const tabName = e.target.dataset.tab;
            
            // 全タブのスタイルをリセット
            document.querySelectorAll('.settings-tab').forEach(t => {
                t.classList.remove('border-b-2', 'border-blue-500', 'text-blue-600', 'dark:text-blue-400');
                t.classList.add('text-gray-600', 'dark:text-gray-400');
            });
            
            // クリックされたタブをアクティブに
            e.target.classList.add('border-b-2', 'border-blue-500', 'text-blue-600', 'dark:text-blue-400');
            e.target.classList.remove('text-gray-600', 'dark:text-gray-400');
            
            // 全コンテンツを非表示
            document.querySelectorAll('.settings-tab-content').forEach(content => {
                content.classList.add('hidden');
            });
            
            // 対応するコンテンツを表示
            const content = document.getElementById(`${tabName}-tab`);
            if (content) {
                content.classList.remove('hidden');
            }
            
            // サポータータブの場合は描画
            if (tabName === 'supporters') {
                await renderSupportersTab();
            }
            
            // ツールタブの場合
            if (tabName === 'tools') {
                loadToolsSettings();
            }
        });
    });
    
    // サポーター関連ボタンのイベント
    const reloadSupportersBtn = document.getElementById('reload-supporters-btn');
    if (reloadSupportersBtn) {
        reloadSupportersBtn.addEventListener('click', handleReloadSupporters);
    }
    
    const saveSupportersBtn = document.getElementById('save-supporters-btn');
    if (saveSupportersBtn) {
        saveSupportersBtn.addEventListener('click', saveSupportersSettings);
    }
}

// ツール設定関連の関数
export async function loadToolsSettings() {
    try {
        const response = await fetch('/api/tools/settings');
        const toolsData = await response.json();
        
        const container = document.getElementById('tools-settings-list');
        container.innerHTML = '';
        
        Object.entries(toolsData).forEach(([toolName, toolInfo]) => {
            const toolCard = createToolSettingsCard(toolName, toolInfo);
            container.appendChild(toolCard);
        });
    } catch (error) {
        console.error('Failed to load tool settings:', error);
    }
}

function createToolSettingsCard(toolName, toolInfo) {
    const card = document.createElement('div');
    card.className = `p-4 border border-gray-200 dark:border-gray-700 rounded-lg ${!toolInfo.is_loaded ? 'opacity-60' : ''}`;
    
    let settingsHtml = '';
    if (toolInfo.settings_schema) {
        settingsHtml = '<div class="mt-3 space-y-3">';
        
        Object.entries(toolInfo.settings_schema).forEach(([key, schema]) => {
            const currentValue = toolInfo.current_settings[key] ?? schema.default;
            const inputId = `${toolName}_${key}`;
            
            settingsHtml += `<div class="flex flex-col">
                <label for="${inputId}" class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    ${schema.label || key}
                    ${schema.description ? `<span class="text-xs text-gray-500 dark:text-gray-400 block">${schema.description}</span>` : ''}
                </label>`;
            
            switch (schema.type) {
                case 'boolean':
                    settingsHtml += `
                        <label class="toggle-switch">
                            <input type="checkbox" id="${inputId}" data-tool="${toolName}" data-key="${key}" 
                                   class="tool-setting-input" ${currentValue ? 'checked' : ''}>
                            <span class="slider"></span>
                        </label>`;
                    break;
                case 'number':
                    settingsHtml += `
                        <input type="number" id="${inputId}" data-tool="${toolName}" data-key="${key}"
                               class="tool-setting-input p-2 rounded bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600"
                               value="${currentValue}" min="${schema.min}" max="${schema.max}" step="${schema.step || 1}">`;
                    break;
                case 'select':
                    settingsHtml += `
                        <select id="${inputId}" data-tool="${toolName}" data-key="${key}"
                                class="tool-setting-input p-2 rounded bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600">
                            ${schema.options.map(opt => 
                                `<option value="${opt.value}" ${currentValue === opt.value ? 'selected' : ''}>${opt.label}</option>`
                            ).join('')}
                        </select>`;
                    break;
                default:
                    settingsHtml += `
                        <input type="text" id="${inputId}" data-tool="${toolName}" data-key="${key}"
                               class="tool-setting-input p-2 rounded bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600"
                               value="${currentValue || ''}" placeholder="${schema.placeholder || ''}">`;
            }
            
            settingsHtml += '</div>';
        });
        
        settingsHtml += `
            <div class="flex gap-2 mt-4">
                <button onclick="saveToolSettings('${toolName}')" 
                        class="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700">
                    保存
                </button>
                <button onclick="resetToolSettings('${toolName}')" 
                        class="px-3 py-1 bg-gray-500 text-white text-sm rounded hover:bg-gray-600">
                    リセット
                </button>
            </div>
        </div>`;
    } else if (!toolInfo.is_loaded) {
        settingsHtml = '<p class="text-sm text-gray-500 dark:text-gray-400 mt-2">このツールは現在読み込まれていません</p>';
    } else {
        settingsHtml = '<p class="text-sm text-gray-500 dark:text-gray-400 mt-2">このツールには設定項目がありません</p>';
    }
    
    card.innerHTML = `
        <div class="flex items-start justify-between">
            <div class="flex items-center gap-2">
                <span class="text-lg">${toolInfo.icon || '🔧'}</span>
                <div>
                    <h5 class="font-semibold text-gray-800 dark:text-gray-200">${toolInfo.name}</h5>
                    <p class="text-xs text-gray-600 dark:text-gray-400">${toolInfo.description}</p>
                </div>
            </div>
            ${!toolInfo.is_loaded ? '<span class="text-xs bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200 px-2 py-1 rounded">未読込</span>' : ''}
        </div>
        ${settingsHtml}
    `;
    
    return card;
}

// 通知を表示
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `fixed bottom-4 right-4 p-4 rounded-lg shadow-lg ${
        type === 'success' ? 'bg-green-500' : 
        type === 'error' ? 'bg-red-500' : 
        'bg-blue-500'
    } text-white z-50 animate-fadeIn`;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// グローバル関数
window.saveToolSettings = async function(toolName) {
    const settings = {};
    document.querySelectorAll(`.tool-setting-input[data-tool="${toolName}"]`).forEach(input => {
        const key = input.dataset.key;
        let value;
        
        if (input.type === 'checkbox') {
            value = input.checked;
        } else if (input.type === 'number') {
            value = parseFloat(input.value);
        } else {
            value = input.value;
        }
        
        settings[key] = value;
    });
    
    try {
        const response = await fetch(`/api/tools/settings/${toolName}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        if (response.ok) {
            showNotification(`${toolName}の設定を保存しました`, 'success');
        } else {
            showNotification('設定の保存に失敗しました', 'error');
        }
    } catch (error) {
        console.error('Failed to save settings:', error);
        showNotification('設定の保存に失敗しました', 'error');
    }
}

window.resetToolSettings = async function(toolName) {
    if (!confirm(`${toolName}の設定をリセットしますか？`)) return;
    
    try {
        const response = await fetch(`/api/tools/settings/${toolName}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            loadToolsSettings();
            showNotification(`${toolName}の設定をリセットしました`, 'success');
        }
    } catch (error) {
        console.error('Failed to reset settings:', error);
        showNotification('設定のリセットに失敗しました', 'error');
    }
}
