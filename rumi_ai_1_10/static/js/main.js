// static/js/main.js

import { state } from './state.js';
import { 
    loadUserSettingsFromServer, 
    loadChatListFromServer, 
    loadPromptsFromServer, 
    loadChatHistoryFromServer, 
    loadAvailableModels, 
    loadFavoriteModels 
} from './api.js';
import { setupEventListeners } from './handlers.js';
import { 
    renderChatList, 
    initializeNewChatView, 
    addMessageToDOM, 
    updateActiveChatSelection, 
    dom, 
    updateAllUI 
} from './ui.js';
import { escapeHtml, getAIIconSrc } from './utils.js';
import { 
    createToolLogContainer, 
    appendToolLogEntry 
} from './ui_messages.js';
import { renderSupportersTab, saveSupportersSettings, handleReloadSupporters } from './ui_settings.js';
import { initSettingsTabs } from './settings_handlers.js';

// --- チャットリスト読み込み ---
export async function loadChatList() {
    try {
        const data = await loadChatListFromServer();
        state.chatListData = data;
        renderChatList();
    } catch (error) {
        console.error('Failed to load chat list:', error);
    }
}

// --- URLとルーティング ---
export function navigateTo(path) {
    if (window.location.pathname === path && path === '/') {
        // すでにホームにいる場合はビューをリセットするだけ
        initializeNewChatView();
        return;
    }
    if (window.location.pathname === path) return;
    
    history.pushState({ path }, '', path);
    handleLocationChange();
}

async function handleLocationChange() {
    const path = window.location.pathname;
    const match = path.match(/^\/chats\/([a-f0-9-]+)/);
    
    if (match) {
        const chatId = match[1];
        if (state.currentChatId !== chatId) {
            state.currentChatId = chatId;
            try {
                const data = await loadChatHistoryFromServer(chatId);
                dom.messagesContainer.innerHTML = '';
                
                console.log('Loading chat history for:', chatId);
                
                // 標準形式（2.0）かどうかを判定
                const isStandardFormat = data.schema_version === "2.0";
                
                if (isStandardFormat) {
                    // 標準形式の処理
                    await handleStandardFormatHistory(data, chatId);
                } else {
                    // 旧形式の処理（後方互換性）
                    await handleLegacyFormatHistory(data, chatId);
                }
                
                // ヘッダータイトルを更新
                const title = isStandardFormat ? data.title : data.metadata?.title;
                dom.chatHeaderTitle.textContent = title || '新しいチャット';
                updateActiveChatSelection();
                
            } catch (error) {
                console.error('Failed to load chat history:', error);
                navigateTo('/');
            }
        }
    } else {
        initializeNewChatView();
    }
}

/**
 * 標準形式（2.0）の履歴を処理して表示
 */
async function handleStandardFormatHistory(data, chatId) {
    // mappingからcurrent_nodeまでの線形スレッドを取得
    const thread = getConversationThread(data);
    
    if (thread.length === 0) {
        dom.chatWindow.classList.remove('chat-active');
        return;
    }
    
    dom.chatWindow.classList.add('chat-active');
    
    // UI履歴からツールログを読み込み
    const toolLogs = await loadToolLogsFromHistory(chatId);
    
    // 実行IDごとにツールログをグループ化
    const toolLogsByExecution = {};
    toolLogs.forEach(log => {
        const execId = log.execution_id || 'unknown';
        if (!toolLogsByExecution[execId]) {
            toolLogsByExecution[execId] = [];
        }
        toolLogsByExecution[execId].push(log);
    });
    
    // メッセージを順番に表示
    let pendingToolResults = [];
    
    for (const msg of thread) {
        const role = msg.role;
        
        // systemメッセージは非表示
        if (role === 'system') {
            continue;
        }
        
        // userメッセージ
        if (role === 'user') {
            // 保留中のツール結果があれば先に表示
            if (pendingToolResults.length > 0) {
                displayToolResults(pendingToolResults, toolLogsByExecution);
                pendingToolResults = [];
            }
            
            addMessageToDOM({
                type: 'user',
                role: 'user',
                text: msg.content,
                content: msg.content,
                files: convertAttachmentsToFiles(msg.attachments)
            });
        }
        
        // assistantメッセージ
        else if (role === 'assistant') {
            // tool_callsを含む場合
            if (msg.tool_calls && msg.tool_calls.length > 0) {
                // ツール呼び出しの説明テキストがあれば表示
                if (msg.content) {
                    addMessageToDOM({
                        type: 'ai',
                        role: 'assistant',
                        text: msg.content,
                        content: msg.content,
                        files: []
                    });
                }
            } else {
                // 保留中のツール結果があれば先に表示
                if (pendingToolResults.length > 0) {
                    displayToolResults(pendingToolResults, toolLogsByExecution);
                    pendingToolResults = [];
                }
                
                // 通常のテキスト応答
                if (msg.content) {
                    addMessageToDOM({
                        type: 'ai',
                        role: 'assistant',
                        text: msg.content,
                        content: msg.content,
                        files: [],
                        status: msg.status
                    });
                }
            }
        }
        
        // toolメッセージ
        else if (role === 'tool') {
            pendingToolResults.push(msg);
        }
    }
    
    // 残りのツール結果を表示
    if (pendingToolResults.length > 0) {
        displayToolResults(pendingToolResults, toolLogsByExecution);
    }
    
    // 最後のメッセージが中断されていた場合
    const lastMsg = thread[thread.length - 1];
    if (lastMsg && lastMsg.status === 'aborted') {
        showContinueButton();
    }
}

/**
 * mappingを辿ってcurrent_nodeまでの線形スレッドを取得
 */
function getConversationThread(historyData) {
    const currentNode = historyData.current_node;
    const mapping = historyData.mapping || {};
    const messages = historyData.messages || [];
    
    if (!currentNode || !mapping[currentNode]) {
        // mappingがない場合はmessages配列をそのまま返す
        return messages;
    }
    
    // current_nodeからルートまで遡る
    const path = [];
    let current = currentNode;
    
    while (current) {
        path.push(current);
        const entry = mapping[current];
        if (!entry) break;
        current = entry.parent;
    }
    
    // 逆順にしてルートから順番にする
    path.reverse();
    
    // メッセージIDからメッセージを取得
    const messagesById = {};
    messages.forEach(msg => {
        messagesById[msg.message_id] = msg;
    });
    
    return path.map(id => messagesById[id]).filter(Boolean);
}

/**
 * ツール結果を表示
 */
function displayToolResults(toolResults, toolLogsByExecution) {
    // ツール結果をグループ化して表示
    const executionIds = new Set();
    
    toolResults.forEach(result => {
        // tool_call_idから対応するexecution_idを探す
        Object.keys(toolLogsByExecution).forEach(execId => {
            const logs = toolLogsByExecution[execId];
            if (logs.some(log => log.tool_call_id === result.tool_call_id)) {
                executionIds.add(execId);
            }
        });
    });
    
    // 実行IDごとにログコンテナを作成
    executionIds.forEach(execId => {
        if (toolLogsByExecution[execId]) {
            const container = createToolLogContainer(execId);
            dom.messagesContainer.appendChild(container);
            
            const contentDiv = container.querySelector('.tool-log-content-area');
            if (contentDiv) {
                toolLogsByExecution[execId].forEach(log => {
                    appendToolLogEntry(contentDiv, log);
                });
            }
            
            // 使用済みとしてマーク
            delete toolLogsByExecution[execId];
        }
    });
    
    // ログがない場合はシンプルな表示
    if (executionIds.size === 0) {
        toolResults.forEach(result => {
            const toolResultElement = createSimpleToolResultElement(result);
            dom.messagesContainer.appendChild(toolResultElement);
        });
    }
}

/**
 * シンプルなツール結果要素を作成
 */
function createSimpleToolResultElement(toolResult) {
    const wrapper = document.createElement('div');
    wrapper.className = 'w-full flex justify-start animate-fadeIn py-2';
    
    let resultContent = '';
    try {
        const parsed = JSON.parse(toolResult.content);
        resultContent = parsed.success !== false ? '✓ 完了' : '✗ エラー';
    } catch {
        resultContent = toolResult.content?.substring(0, 50) || '完了';
    }
    
    wrapper.innerHTML = `
        <div class="flex items-start gap-3 max-w-3xl">
            <div class="w-8 h-8 flex-shrink-0"></div>
            <div class="text-sm text-gray-500 dark:text-gray-400 italic">
                🔧 ツール実行結果: ${escapeHtml(resultContent)}
            </div>
        </div>
    `;
    
    return wrapper;
}

/**
 * attachmentsをfiles形式に変換
 */
function convertAttachmentsToFiles(attachments) {
    if (!attachments) return [];
    
    return attachments.map(att => ({
        name: att.name || 'file',
        path: att.url || '',
        type: att.mime_type || 'application/octet-stream'
    }));
}

/**
 * 続きを生成ボタンを表示
 */
function showContinueButton() {
    const existingBtn = document.getElementById('continue-button-container');
    if (existingBtn) return;
    
    const continueButton = document.createElement('div');
    continueButton.id = 'continue-button-container';
    continueButton.className = 'w-full flex justify-center py-3 animate-fadeIn';
    continueButton.innerHTML = `
        <button id="continue-response-btn" class="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors shadow-lg">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"></path>
            </svg>
            <span>続きを生成</span>
        </button>
    `;
    dom.messagesContainer.appendChild(continueButton);
    
    setTimeout(() => {
        const btn = document.getElementById('continue-response-btn');
        if (btn) {
            btn.addEventListener('click', () => {
                const event = new CustomEvent('continueMessage');
                window.dispatchEvent(event);
            });
        }
    }, 100);
}

/**
 * 旧形式の履歴を処理して表示（後方互換性）
 */
async function handleLegacyFormatHistory(data, chatId) {
    const messages = data.messages || [];
    
    if (messages.length === 0) {
        dom.chatWindow.classList.remove('chat-active');
        return;
    }
    
    dom.chatWindow.classList.add('chat-active');
    
    // ツールログを読み込み
    const toolLogs = await loadToolLogsFromHistory(chatId);
    const executionMap = new Map();
    const messageOrder = [];
    
    for (const msg of messages) {
        if (msg.type === 'system') continue;
        
        if (msg.file && !msg.files) {
            msg.files = [msg.file];
            delete msg.file;
        }
        
        if (msg.tool_executions && msg.tool_executions.length > 0) {
            msg.tool_executions.forEach(exec => {
                if (exec.execution_id) {
                    executionMap.set(exec.execution_id, {
                        messageIndex: messageOrder.length,
                        toolName: exec.tool_name,
                        timestamp: exec.timestamp || Date.now()
                    });
                }
            });
        }
        
        messageOrder.push({
            type: 'message',
            data: msg,
            element: null
        });
    }
    
    const mergedOrder = mergeMessagesWithToolLogs(messageOrder, toolLogs, executionMap);
    
    for (const item of mergedOrder) {
        if (item.type === 'message') {
            addMessageToDOM(item.data);
        } else if (item.type === 'toolLog') {
            const container = createToolLogContainer(item.executionId);
            dom.messagesContainer.appendChild(container);
            
            const contentDiv = container.querySelector('.tool-log-content-area');
            if (contentDiv) {
                item.logs.forEach(log => {
                    appendToolLogEntry(contentDiv, log);
                });
            }
        }
    }
    
    // 最後のメッセージが中断されていた場合
    const lastMessage = messages[messages.length - 1];
    if (lastMessage && lastMessage.type === 'system' && lastMessage.event === 'force_stop') {
        showContinueButton();
    }
}

// ツールログを履歴から読み込む
async function loadToolLogsFromHistory(chatId) {
    try {
        const response = await fetch(`/api/chats/${chatId}/ui_history/logs`);
        if (!response.ok) {
            console.error('Response not ok:', response.status);
            return [];
        }
        
        const data = await response.json();
        return data.logs || [];
    } catch (error) {
        console.error('Failed to load tool logs:', error);
        return [];
    }
}

// メッセージとツールログをマージして正しい順序を作成
function mergeMessagesWithToolLogs(messageOrder, toolLogs, executionMap) {
    const result = [];
    
    // 実行IDごとにツールログをグループ化
    const executionGroups = {};
    toolLogs.forEach(log => {
        const execId = log.execution_id || 'unknown';
        if (!executionGroups[execId]) {
            executionGroups[execId] = [];
        }
        executionGroups[execId].push(log);
    });
    
    // 各実行グループをタイムスタンプでソート
    Object.keys(executionGroups).forEach(execId => {
        executionGroups[execId].sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));
    });
    
    // メッセージを順番に処理
    for (let i = 0; i < messageOrder.length; i++) {
        const item = messageOrder[i];
        
        // AIメッセージでツール実行を含む場合
        if (item.data.type === 'ai' && item.data.tool_executions && item.data.tool_executions.length > 0) {
            // まずツールログを追加
            item.data.tool_executions.forEach(exec => {
                if (exec.execution_id && executionGroups[exec.execution_id]) {
                    result.push({
                        type: 'toolLog',
                        executionId: exec.execution_id,
                        logs: executionGroups[exec.execution_id]
                    });
                    // 処理済みとしてマーク
                    delete executionGroups[exec.execution_id];
                }
            });
            
            // その後AIメッセージを追加
            result.push(item);
        } else {
            // 通常のメッセージはそのまま追加
            result.push(item);
        }
    }
    
    // 未処理のツールログがあれば最後に追加
    Object.entries(executionGroups).forEach(([execId, logs]) => {
        result.push({
            type: 'toolLog',
            executionId: execId,
            logs: logs
        });
    });
    
    return result;
}

// --- ツールアイコンバー関連 ---
async function loadToolsIconBar() {
    try {
        const response = await fetch('/api/tools/settings');
        const toolsData = await response.json();
        
        const iconBar = document.getElementById('tools-icon-bar');
        iconBar.innerHTML = '';
        
        // 読み込まれているツールのみ表示
        Object.entries(toolsData).forEach(([toolName, toolInfo]) => {
            if (toolInfo.is_loaded) {
                const iconButton = createToolIconButton(toolName, toolInfo);
                iconBar.appendChild(iconButton);
            }
        });
        
        // セパレータを追加
        const separator = document.createElement('div');
        separator.className = 'w-8 h-px bg-gray-300 dark:bg-gray-600 my-2';
        iconBar.appendChild(separator);
        
        // リロードボタンを追加
        const reloadButton = document.createElement('button');
        reloadButton.className = 'tool-icon-button';
        reloadButton.innerHTML = `
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
            </svg>
            <span class="tooltip">ツールを再読み込み</span>
        `;
        reloadButton.onclick = reloadTools;
        iconBar.appendChild(reloadButton);
        
    } catch (error) {
        console.error('Failed to load tools icon bar:', error);
    }
}

function createToolIconButton(toolName, toolInfo) {
    const button = document.createElement('button');
    button.className = 'tool-icon-button';
    button.dataset.toolName = toolName;
    
    // アイコンまたは絵文字を表示
    if (toolInfo.icon) {
        if (toolInfo.icon.startsWith('<svg')) {
            button.innerHTML = toolInfo.icon;
        } else {
            button.innerHTML = `<span class="text-lg">${toolInfo.icon}</span>`;
        }
    } else {
        button.innerHTML = `<span class="text-lg">🔧</span>`;
    }
    
    // ツールチップを追加
    const tooltip = document.createElement('span');
    tooltip.className = 'tooltip';
    tooltip.textContent = toolInfo.name;
    button.appendChild(tooltip);
    
    // クリックイベント
    button.onclick = () => openToolDetail(toolName, toolInfo);
    
    return button;
}

function openToolDetail(toolName, toolInfo) {
    const panel = document.getElementById('tool-detail-panel');
    const content = document.getElementById('tool-detail-content');
    const chatWindow = document.getElementById('chat-window');
    
    // アクティブ状態を更新
    document.querySelectorAll('.tool-icon-button').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelector(`.tool-icon-button[data-tool-name="${toolName}"]`)?.classList.add('active');
    
    // 仮想環境ステータスを取得
    fetch(`/api/tools/${toolName}/venv-status`)
        .then(response => response.json())
        .then(venvStatus => {
            // 詳細パネルの内容を更新
            content.innerHTML = `
                <div class="space-y-4">
                    <!-- ツール情報 -->
                    <div class="flex items-start gap-3">
                        <div class="text-2xl">${toolInfo.icon || '🔧'}</div>
                        <div class="flex-1">
                            <h4 class="font-semibold text-lg text-gray-800 dark:text-gray-200">${toolInfo.name}</h4>
                            <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">${toolInfo.description}</p>
                        </div>
                    </div>
                    
                    <!-- 仮想環境情報 -->
                    ${venvStatus.has_venv ? `
                        <div class="p-3 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
                            <div class="flex items-center gap-2 text-sm text-green-700 dark:text-green-300">
                                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path>
                                </svg>
                                <span class="font-medium">専用仮想環境が有効</span>
                            </div>
                            ${venvStatus.packages && venvStatus.packages.length > 0 ? `
                                <details class="mt-2">
                                    <summary class="text-xs text-gray-600 dark:text-gray-400 cursor-pointer hover:text-gray-800 dark:hover:text-gray-200">
                                        インストール済みパッケージ (${venvStatus.packages.length}個)
                                    </summary>
                                    <div class="mt-2 max-h-32 overflow-y-auto">
                                        <ul class="text-xs space-y-1">
                                            ${venvStatus.packages.map(pkg => 
                                                `<li class="text-gray-600 dark:text-gray-400">${pkg.name} ${pkg.version}</li>`
                                            ).join('')}
                                        </ul>
                                    </div>
                                </details>
                            ` : ''}
                        </div>
                    ` : venvStatus.has_requirements ? `
                        <div class="p-3 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
                            <div class="flex items-center gap-2 text-sm text-yellow-700 dark:text-yellow-300">
                                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                                    <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
                                </svg>
                                <span class="font-medium">requirements.txt が検出されました</span>
                            </div>
                            <p class="text-xs text-gray-600 dark:text-gray-400 mt-1">
                                ツールを再読み込みすると仮想環境が作成されます
                            </p>
                        </div>
                    ` : ''}
                    
                    <!-- 設定セクション -->
                    <div class="border-t border-gray-200 dark:border-gray-700 pt-4">
                        <h5 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">設定</h5>
                        <div id="tool-settings-form" class="space-y-3">
                            ${generateToolSettingsForm(toolName, toolInfo)}
                        </div>
                    </div>
                    
                    <!-- アクションボタン -->
                    <div class="flex gap-2 pt-4 border-t border-gray-200 dark:border-gray-700">
                        <button onclick="saveToolSettingsFromPanel('${toolName}')" 
                                class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
                            設定を保存
                        </button>
                        <button onclick="resetToolSettingsFromPanel('${toolName}')" 
                                class="px-4 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors">
                            リセット
                        </button>
                    </div>
                </div>
            `;
        })
        .catch(error => {
            console.error('Failed to get venv status:', error);
            // エラー時は仮想環境情報なしで表示
            content.innerHTML = generateBasicToolDetail(toolName, toolInfo);
        });
    
    // パネルを表示
    panel.classList.remove('hidden');
    chatWindow.classList.add('tool-panel-open');
}

function generateBasicToolDetail(toolName, toolInfo) {
    return `
        <div class="space-y-4">
            <!-- ツール情報 -->
            <div class="flex items-start gap-3">
                <div class="text-2xl">${toolInfo.icon || '🔧'}</div>
                <div class="flex-1">
                    <h4 class="font-semibold text-lg text-gray-800 dark:text-gray-200">${toolInfo.name}</h4>
                    <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">${toolInfo.description}</p>
                </div>
            </div>
            
            <!-- 設定セクション -->
            <div class="border-t border-gray-200 dark:border-gray-700 pt-4">
                <h5 class="font-semibold text-gray-800 dark:text-gray-200 mb-3">設定</h5>
                <div id="tool-settings-form" class="space-y-3">
                    ${generateToolSettingsForm(toolName, toolInfo)}
                </div>
            </div>
            
            <!-- アクションボタン -->
            <div class="flex gap-2 pt-4 border-t border-gray-200 dark:border-gray-700">
                <button onclick="saveToolSettingsFromPanel('${toolName}')" 
                        class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors">
                    設定を保存
                </button>
                <button onclick="resetToolSettingsFromPanel('${toolName}')" 
                        class="px-4 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors">
                    リセット
                </button>
            </div>
        </div>
    `;
}

function generateToolSettingsForm(toolName, toolInfo) {
    if (!toolInfo.settings_schema) {
        return '<p class="text-sm text-gray-500 dark:text-gray-400">このツールには設定項目がありません</p>';
    }
    
    let html = '';
    Object.entries(toolInfo.settings_schema).forEach(([key, schema]) => {
        const currentValue = toolInfo.current_settings[key] ?? schema.default;
        const inputId = `panel_${toolName}_${key}`;
        
        html += '<div class="tool-setting-group">';
        html += `<label for="${inputId}" class="tool-setting-label">${schema.label || key}</label>`;
        
        if (schema.description) {
            html += `<p class="tool-setting-description">${schema.description}</p>`;
        }
        
        switch (schema.type) {
            case 'boolean':
                html += `
                    <label class="toggle-switch">
                        <input type="checkbox" id="${inputId}" data-tool="${toolName}" data-key="${key}" 
                               class="panel-tool-setting" ${currentValue ? 'checked' : ''}>
                        <span class="slider"></span>
                    </label>`;
                break;
            case 'number':
                html += `
                    <input type="number" id="${inputId}" data-tool="${toolName}" data-key="${key}"
                           class="panel-tool-setting w-full p-2 rounded bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600"
                           value="${currentValue}" min="${schema.min}" max="${schema.max}" step="${schema.step || 1}">`;
                break;
            case 'select':
                html += `
                    <select id="${inputId}" data-tool="${toolName}" data-key="${key}"
                            class="panel-tool-setting w-full p-2 rounded bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600">
                        ${schema.options.map(opt => 
                            `<option value="${opt.value}" ${currentValue === opt.value ? 'selected' : ''}>${opt.label}</option>`
                        ).join('')}
                    </select>`;
                break;
            default: // text
                html += `
                    <input type="text" id="${inputId}" data-tool="${toolName}" data-key="${key}"
                           class="panel-tool-setting w-full p-2 rounded bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600"
                           value="${currentValue || ''}" placeholder="${schema.placeholder || ''}">`;
        }
        
        html += '</div>';
    });
    
    return html;
}

// 設定保存関数（パネル用）
window.saveToolSettingsFromPanel = async function(toolName) {
    const settings = {};
    document.querySelectorAll(`.panel-tool-setting[data-tool="${toolName}"]`).forEach(input => {
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
            // アイコンバーを更新
            await loadToolsIconBar();
        } else {
            showNotification('設定の保存に失敗しました', 'error');
        }
    } catch (error) {
        console.error('Failed to save settings:', error);
        showNotification('設定の保存に失敗しました', 'error');
    }
};

// 設定リセット関数（パネル用）
window.resetToolSettingsFromPanel = async function(toolName) {
    if (!confirm(`${toolName}の設定をリセットしますか？`)) return;
    
    try {
        const response = await fetch(`/api/tools/settings/${toolName}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showNotification(`${toolName}の設定をリセットしました`, 'success');
            // パネルを再読み込み
            const response2 = await fetch('/api/tools/settings');
            const toolsData = await response2.json();
            openToolDetail(toolName, toolsData[toolName]);
        }
    } catch (error) {
        console.error('Failed to reset settings:', error);
        showNotification('設定のリセットに失敗しました', 'error');
    }
};

// ツール再読み込み関数
async function reloadTools() {
    const btn = event.currentTarget;
    btn.disabled = true;
    btn.querySelector('svg').classList.add('animate-spin');
    
    try {
        const response = await fetch('/api/tools/reload', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            showNotification(`${data.loaded_count}個のツールを読み込みました`, 'success');
            await loadToolsIconBar();
        } else {
            showNotification(`エラー: ${data.error}`, 'error');
        }
    } catch (error) {
        showNotification(`エラー: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.querySelector('svg').classList.remove('animate-spin');
    }
}

// 通知表示関数
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

// --- 初期化 ---
async function initialize() {
    try {
        const settings = await loadUserSettingsFromServer();
        Object.assign(state.userSettings, settings);

        const prompts = await loadPromptsFromServer();
        state.availablePrompts = prompts;
        if (prompts.length > 0) {
            const normalPrompt = prompts.find(p => p.id === 'normal_prompt');
            state.currentPromptId = normalPrompt ? normalPrompt.id : prompts[0].id;
        }

        // AIモデル情報を読み込み
        try {
            state.availableModels = await loadAvailableModels();
            state.favoriteModels = await loadFavoriteModels();
            console.log(`読み込まれたモデル数: ${state.availableModels.length}`);
            console.log(`お気に入りモデル数: ${state.favoriteModels.length}`);
        } catch (error) {
            console.error('Failed to load AI models:', error);
        }

        await loadChatList();
        
        // ツールアイコンバーを初期化
        await loadToolsIconBar();
        
        setupEventListeners();
        
        // 設定タブの初期化
        initSettingsTabs();
        
        window.addEventListener('popstate', (e) => {
            handleLocationChange();
        });
        window.addEventListener('navigate', (e) => navigateTo(e.detail.path));
        window.addEventListener('continueMessage', async () => {
            const event = new CustomEvent('triggerContinue');
            window.dispatchEvent(event);
        });

        handleLocationChange();
        
        updateAllUI();
        
        // 詳細パネルを閉じるイベントリスナー
        document.getElementById('close-tool-detail')?.addEventListener('click', () => {
            const panel = document.getElementById('tool-detail-panel');
            const chatWindow = document.getElementById('chat-window');
            
            panel.classList.add('hidden');
            chatWindow.classList.remove('tool-panel-open');
            
            document.querySelectorAll('.tool-icon-button').forEach(btn => {
                btn.classList.remove('active');
            });
        });

    } catch (error) {
        console.error("Initialization failed:", error);
        document.body.innerHTML = '<div style="color: red; padding: 20px;">アプリケーションの初期化に失敗しました。コンソールを確認してください。</div>';
    }
}

// --- アプリケーション開始 ---
document.addEventListener('DOMContentLoaded', initialize);
