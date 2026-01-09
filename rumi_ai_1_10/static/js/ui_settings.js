// static/js/ui_settings.js

import { state } from './state.js';
import { loadChatSupporters, saveChatSupporters, loadAllSupporters, reloadSupporters } from './api.js';
import { escapeHtml } from './utils.js';

/**
 * サポータータブを描画
 */
export async function renderSupportersTab() {
    const container = document.getElementById('supporters-list');
    if (!container) return;
    
    try {
        // 現在のチャットIDを取得
        const chatId = state.currentChatId;
        
        if (!chatId) {
            container.innerHTML = `
                <div class="text-center text-gray-500 dark:text-gray-400 py-8">
                    チャットを選択してください
                </div>
            `;
            return;
        }
        
        // サポーター情報を取得
        const data = await loadChatSupporters(chatId);
        const allSupporters = data.all_supporters || [];
        const activeSupporters = data.active_supporters || [];
        
        if (allSupporters.length === 0) {
            container.innerHTML = `
                <div class="text-center text-gray-500 dark:text-gray-400 py-8">
                    <p>利用可能なサポーターがありません</p>
                    <p class="text-xs mt-2">supporter/ フォルダにサポーターを追加してください</p>
                </div>
            `;
            return;
        }
        
        // サポーターをソート: アクティブなものを先に、その順序を維持
        const sortedSupporters = [...allSupporters].sort((a, b) => {
            const aIndex = activeSupporters.indexOf(a.id);
            const bIndex = activeSupporters.indexOf(b.id);
            
            if (aIndex !== -1 && bIndex !== -1) {
                return aIndex - bIndex;
            }
            if (aIndex !== -1) return -1;
            if (bIndex !== -1) return 1;
            return 0;
        });
        
        // カードを描画
        container.innerHTML = sortedSupporters.map((supporter, index) => {
            const isActive = activeSupporters.includes(supporter.id);
            return createSupporterCard(supporter, index, isActive, sortedSupporters.length);
        }).join('');
        
        // イベントリスナーを設定
        setupSupporterCardEvents(container);
        
    } catch (error) {
        console.error('Failed to render supporters tab:', error);
        container.innerHTML = `
            <div class="text-center text-red-500 py-8">
                サポーターの読み込みに失敗しました: ${escapeHtml(error.message)}
            </div>
        `;
    }
}

/**
 * サポーターカードを作成
 * @param {object} supporter サポーター情報
 * @param {number} index インデックス
 * @param {boolean} isActive 有効かどうか
 * @param {number} totalCount 総数
 * @returns {string} HTML文字列
 */
function createSupporterCard(supporter, index, isActive, totalCount) {
    const timingBadge = {
        'pre': '<span class="px-2 py-0.5 text-xs rounded bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-300">Pre</span>',
        'post': '<span class="px-2 py-0.5 text-xs rounded bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300">Post</span>',
        'both': '<span class="px-2 py-0.5 text-xs rounded bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-300">Both</span>'
    }[supporter.timing] || '';
    
    const scopeBadge = {
        'permanent': '<span class="px-2 py-0.5 text-xs rounded bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300">Permanent</span>',
        'turn': '<span class="px-2 py-0.5 text-xs rounded bg-yellow-100 dark:bg-yellow-900 text-yellow-700 dark:text-yellow-300">Turn</span>',
        'temporary': '<span class="px-2 py-0.5 text-xs rounded bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300">Temporary</span>'
    }[supporter.output_scope] || '';
    
    const aiBadge = supporter.has_ai ? 
        '<span class="px-2 py-0.5 text-xs rounded bg-indigo-100 dark:bg-indigo-900 text-indigo-700 dark:text-indigo-300">AI</span>' : '';
    
    return `
        <div class="supporter-card p-4 border border-gray-200 dark:border-gray-700 rounded-lg ${isActive ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-300 dark:border-blue-700' : ''}" 
             data-supporter-id="${escapeHtml(supporter.id)}"
             data-active="${isActive}">
            <div class="flex items-start justify-between">
                <div class="flex items-center gap-3">
                    <span class="text-2xl">${supporter.icon || '🔧'}</span>
                    <div>
                        <h5 class="font-semibold text-gray-800 dark:text-gray-200">${escapeHtml(supporter.name)}</h5>
                        <p class="text-xs text-gray-600 dark:text-gray-400">${escapeHtml(supporter.description || '')}</p>
                        <div class="flex gap-1 mt-1">
                            ${timingBadge}
                            ${scopeBadge}
                            ${aiBadge}
                        </div>
                    </div>
                </div>
                <div class="flex items-center gap-2">
                    <!-- 順序変更ボタン -->
                    <div class="flex flex-col gap-1">
                        <button class="move-up-btn p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-600 ${index === 0 ? 'opacity-30 cursor-not-allowed' : ''}" 
                                ${index === 0 ? 'disabled' : ''} title="上に移動">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 15l7-7 7 7"></path>
                            </svg>
                        </button>
                        <button class="move-down-btn p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-600 ${index === totalCount - 1 ? 'opacity-30 cursor-not-allowed' : ''}" 
                                ${index === totalCount - 1 ? 'disabled' : ''} title="下に移動">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
                            </svg>
                        </button>
                    </div>
                    <!-- 有効/無効トグル -->
                    <label class="toggle-switch">
                        <input type="checkbox" class="supporter-toggle" ${isActive ? 'checked' : ''}>
                        <span class="slider"></span>
                    </label>
                </div>
            </div>
        </div>
    `;
}

/**
 * サポーターカードのイベントリスナーを設定
 * @param {HTMLElement} container コンテナ要素
 */
function setupSupporterCardEvents(container) {
    // トグルイベント
    container.querySelectorAll('.supporter-toggle').forEach(toggle => {
        toggle.addEventListener('change', (e) => {
            const card = e.target.closest('.supporter-card');
            const isActive = e.target.checked;
            card.dataset.active = isActive;
            
            if (isActive) {
                card.classList.add('bg-blue-50', 'dark:bg-blue-900/20', 'border-blue-300', 'dark:border-blue-700');
            } else {
                card.classList.remove('bg-blue-50', 'dark:bg-blue-900/20', 'border-blue-300', 'dark:border-blue-700');
            }
        });
    });
    
    // 上へ移動ボタン
    container.querySelectorAll('.move-up-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const card = e.target.closest('.supporter-card');
            const prevCard = card.previousElementSibling;
            if (prevCard && prevCard.classList.contains('supporter-card')) {
                card.parentNode.insertBefore(card, prevCard);
                updateMoveButtons(container);
            }
        });
    });
    
    // 下へ移動ボタン
    container.querySelectorAll('.move-down-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const card = e.target.closest('.supporter-card');
            const nextCard = card.nextElementSibling;
            if (nextCard && nextCard.classList.contains('supporter-card')) {
                card.parentNode.insertBefore(nextCard, card);
                updateMoveButtons(container);
            }
        });
    });
}

/**
 * 移動ボタンの状態を更新
 * @param {HTMLElement} container コンテナ要素
 */
function updateMoveButtons(container) {
    const cards = container.querySelectorAll('.supporter-card');
    cards.forEach((card, index) => {
        const upBtn = card.querySelector('.move-up-btn');
        const downBtn = card.querySelector('.move-down-btn');
        
        if (upBtn) {
            upBtn.disabled = index === 0;
            upBtn.classList.toggle('opacity-30', index === 0);
            upBtn.classList.toggle('cursor-not-allowed', index === 0);
        }
        
        if (downBtn) {
            downBtn.disabled = index === cards.length - 1;
            downBtn.classList.toggle('opacity-30', index === cards.length - 1);
            downBtn.classList.toggle('cursor-not-allowed', index === cards.length - 1);
        }
    });
}

/**
 * 現在のサポーター設定を取得（UI上の順序から）
 * @returns {Array<string>} 有効なサポーターIDの順序付きリスト
 */
export function getCurrentSupportersOrder() {
    const container = document.getElementById('supporters-list');
    if (!container) return [];
    
    const activeSupporters = [];
    container.querySelectorAll('.supporter-card').forEach(card => {
        if (card.dataset.active === 'true') {
            activeSupporters.push(card.dataset.supporterId);
        }
    });
    
    return activeSupporters;
}

/**
 * サポーター設定を保存
 */
export async function saveSupportersSettings() {
    const chatId = state.currentChatId;
    if (!chatId) {
        showNotification('チャットが選択されていません', 'error');
        return;
    }
    
    const supportersList = getCurrentSupportersOrder();
    
    try {
        await saveChatSupporters(chatId, supportersList);
        showNotification('サポーター設定を保存しました', 'success');
    } catch (error) {
        console.error('Failed to save supporters:', error);
        showNotification('サポーター設定の保存に失敗しました', 'error');
    }
}

/**
 * 通知を表示
 * @param {string} message メッセージ
 * @param {string} type 通知タイプ ('info', 'success', 'error')
 */
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

/**
 * サポーター再読み込みボタンのハンドラ
 */
export async function handleReloadSupporters() {
    try {
        const result = await reloadSupporters();
        showNotification(`${result.loaded_count}個のサポーターを再読み込みしました`, 'success');
        await renderSupportersTab();
    } catch (error) {
        console.error('Failed to reload supporters:', error);
        showNotification('サポーターの再読み込みに失敗しました', 'error');
    }
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
