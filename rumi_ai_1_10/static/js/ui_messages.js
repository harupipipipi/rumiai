// static/js/ui_messages.js

import { dom } from './ui_dom.js';
import { escapeHtml, getAIIconSrc } from './utils.js';

/**
 * attachmentsをfiles形式に変換（ローカル版）
 */
function convertAttachmentsToFilesLocal(attachments) {
    if (!attachments) return [];
    
    return attachments.map(att => ({
        name: att.name || 'file',
        path: att.url || '',
        type: att.mime_type || 'application/octet-stream'
    }));
}

/**
 * ファイル要素を作成
 */
function createFileElement(file) {
    const element = document.createElement('div');
    element.className = 'flex items-center gap-2 p-2 bg-gray-200 dark:bg-gray-600 rounded-lg text-sm';
    const fileType = (file.type || '').split('/')[0];
    let content = '';

    switch (fileType) {
        case 'image':
            content = `<img src="${file.path}" alt="${escapeHtml(file.name)}" class="max-w-[100px] h-auto rounded-md cursor-pointer" onclick="window.open('${file.path}', '_blank')"><span>${escapeHtml(file.name)}</span>`;
            break;
        case 'video':
            content = `<video src="${file.path}" controls class="max-w-[200px] rounded-md"></video><span>${escapeHtml(file.name)}</span>`;
            break;
        case 'audio':
            content = `<audio src="${file.path}" controls class="w-full"></audio>`;
            break;
        default:
            content = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" class="flex-shrink-0"><path d="M14 14V4.5L9.5 0H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2zM9.5 3A1.5 1.5 0 0 0 11 4.5h2V14a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1h5.5v2z"/></svg><a href="${file.path}" target="_blank" class="truncate hover:underline">${escapeHtml(file.name)}</a>`;
            break;
    }
    element.innerHTML = content;
    return element;
}

/**
 * toolメッセージを折りたたみ可能な形式で表示
 */
function addToolMessageToDOM(message) {
    const wrapper = document.createElement('div');
    wrapper.className = 'w-full flex justify-start animate-fadeIn py-2';
    
    // ツール結果をパース
    let resultData = {};
    let isSuccess = true;
    try {
        resultData = JSON.parse(message.content);
        isSuccess = resultData.success !== false;
    } catch {
        resultData = { output: message.content };
    }
    
    const statusIcon = isSuccess ? '✓' : '✗';
    const statusColor = isSuccess ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400';
    
    wrapper.innerHTML = `
        <div class="flex items-start gap-3 max-w-3xl w-full">
            <div class="w-8 h-8 flex-shrink-0"></div>
            <div class="flex-1">
                <details class="bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                    <summary class="px-3 py-2 cursor-pointer flex items-center gap-2 text-sm ${statusColor}">
                        <span>${statusIcon}</span>
                        <span class="font-medium">ツール実行結果</span>
                        <span class="text-xs text-gray-500">(クリックで展開)</span>
                    </summary>
                    <div class="px-3 py-2 border-t border-gray-200 dark:border-gray-700">
                        <pre class="text-xs overflow-x-auto whitespace-pre-wrap text-gray-600 dark:text-gray-400">${escapeHtml(JSON.stringify(resultData, null, 2))}</pre>
                    </div>
                </details>
            </div>
        </div>
    `;
    
    dom.messagesContainer.appendChild(wrapper);
    return wrapper;
}

/**
 * メッセージをDOMに追加
 */
export function addMessageToDOM(message) {
    if (!dom.chatWindow.classList.contains('chat-active')) {
        dom.messagesContainer.innerHTML = '';
        dom.chatWindow.classList.add('chat-active');
    }
    
    // role ベースの判定（標準形式対応）
    const role = message.role || message.type;
    const isUser = role === 'user';
    const isAssistant = role === 'assistant' || role === 'ai';
    const isTool = role === 'tool';
    const isSystem = role === 'system';
    
    // systemメッセージは非表示
    if (isSystem) {
        return null;
    }
    
    // toolメッセージは折りたたみ表示
    if (isTool) {
        return addToolMessageToDOM(message);
    }
    
    const messageWrapper = document.createElement('div');
    messageWrapper.className = `w-full flex animate-fadeIn py-4 ${isUser ? 'justify-end' : 'justify-start'}`;
    
    const messageContent = document.createElement('div');
    messageContent.className = 'flex items-start gap-3 max-w-3xl';
    
    if (isAssistant) {
        const avatar = document.createElement('div');
        avatar.className = 'w-8 h-8 flex-shrink-0';
        avatar.innerHTML = `<img src="${getAIIconSrc()}" class="w-full h-full ai-avatar-icon">`;
        messageContent.appendChild(avatar);
    }
    
    const messageBubble = document.createElement('div');
    messageBubble.className = `flex flex-col gap-3 ${isUser ? 'p-4 bg-gray-800 dark:bg-gray-100 text-white dark:text-black rounded-xl' : 'ai-message-bubble'}`;
    
    if (isUser) {
        // ユーザーメッセージ
        const text = message.content || message.text;
        if (text) {
            const p = document.createElement('p');
            p.className = 'whitespace-pre-wrap';
            p.textContent = text;
            messageBubble.appendChild(p);
        }
        
        // ファイル（attachments または files）
        const files = message.files || convertAttachmentsToFilesLocal(message.attachments);
        if (files && files.length > 0) {
            const filesContainer = document.createElement('div');
            filesContainer.className = 'mt-2 space-y-2';
            files.forEach(fileInfo => {
                filesContainer.appendChild(createFileElement(fileInfo));
            });
            messageBubble.appendChild(filesContainer);
        }
    } else if (isAssistant) {
        // AIメッセージ
        const text = message.content || message.text;
        if (text) {
            const textContainer = document.createElement('div');
            textContainer.className = 'p-4 rounded-xl bg-gray-100 dark:bg-gray-700';
            textContainer.innerHTML = marked.parse(text);
            
            // コードブロックの処理
            textContainer.querySelectorAll('pre').forEach(preElement => {
                const wrapper = document.createElement('div');
                wrapper.className = 'my-2 bg-black/80 rounded-lg code-block-wrapper';
                const header = document.createElement('div');
                header.className = 'flex justify-between items-center px-4 py-2 text-xs text-gray-300';
                const lang = preElement.querySelector('code')?.className.replace('language-', '') || 'code';
                header.innerHTML = `<span class="font-semibold">${lang}</span><button class="copy-code-btn text-xs font-semibold">コピー</button>`;
                wrapper.appendChild(header);
                preElement.parentNode.insertBefore(wrapper, preElement);
                wrapper.appendChild(preElement);
            });
            
            messageBubble.appendChild(textContainer);
        }
        
        // 中断されたメッセージの表示
        if (message.status === 'aborted') {
            showAbortedIndicator(messageBubble);
        }
    }
    
    messageContent.appendChild(messageBubble);
    messageWrapper.appendChild(messageContent);
    dom.messagesContainer.appendChild(messageWrapper);
    dom.messagesContainer.scrollTop = dom.messagesContainer.scrollHeight;
    return messageWrapper;
}

/**
 * タイピングインジケーターを作成
 */
export function createTypingIndicator(isToolExecution = false) {
    const wrapper = document.createElement('div');
    wrapper.className = 'w-full flex justify-start animate-fadeIn py-4';
    wrapper.id = 'typing-indicator-wrapper';
    
    if (isToolExecution) {
        wrapper.innerHTML = `
            <div class="flex items-start gap-3 max-w-3xl">
                <div class="w-8 h-8 flex-shrink-0 animate-spin">
                    <img src="${getAIIconSrc()}" class="w-full h-full ai-avatar-icon">
                </div>
                <div class="p-4 rounded-xl bg-blue-100 dark:bg-blue-900/30 border border-blue-300 dark:border-blue-700">
                    <div class="flex items-center gap-2">
                        <svg class="w-5 h-5 animate-spin text-blue-600 dark:text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path>
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                        </svg>
                        <span class="text-sm font-medium text-blue-700 dark:text-blue-300">ツールを実行中...</span>
                    </div>
                </div>
            </div>`;
    } else {
        wrapper.innerHTML = `
            <div class="flex items-start gap-3 max-w-3xl">
                <div class="w-8 h-8 flex-shrink-0">
                    <img src="${getAIIconSrc()}" class="w-full h-full ai-avatar-icon">
                </div>
                <div class="p-4 rounded-xl bg-gray-100 dark:bg-gray-700">
                    <div class="animate-bob">
                        <span class="w-2 h-2 inline-block bg-gray-400 rounded-full"></span>
                        <span class="w-2 h-2 inline-block bg-gray-400 rounded-full"></span>
                        <span class="w-2 h-2 inline-block bg-gray-400 rounded-full"></span>
                    </div>
                </div>
            </div>`;
    }
    return wrapper;
}

/**
 * 続きを生成ボタンを作成
 */
export function createContinueButton() {
    const buttonContainer = document.createElement('div');
    buttonContainer.id = 'continue-button-container';
    buttonContainer.className = 'w-full flex justify-center py-3 animate-fadeIn';
    buttonContainer.innerHTML = `
        <button id="continue-response-btn" class="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors shadow-lg">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14 5l7 7m0 0l-7 7m7-7H3"></path>
            </svg>
            <span>続きを生成</span>
        </button>
    `;
    return buttonContainer;
}

/**
 * 中断インジケーターを削除
 */
export function removeAbortIndicators() {
    const abortedMessages = document.querySelectorAll('.aborted-message');
    abortedMessages.forEach(msg => {
        msg.classList.remove('aborted-message');
    });
    
    const continueContainer = document.getElementById('continue-button-container');
    if (continueContainer) {
        continueContainer.remove();
    }
    
    const systemMessages = document.querySelectorAll('.system-message-abort');
    systemMessages.forEach(msg => msg.remove());
}

/**
 * 中断インジケーターを表示
 */
export function showAbortedIndicator(element) {
    if (!element) return;
    
    const indicator = document.createElement('div');
    indicator.className = 'abort-indicator mt-2 flex items-center gap-2 text-xs text-yellow-600 dark:text-yellow-400';
    indicator.innerHTML = `
        <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path>
        </svg>
        <span>応答が中断されました</span>
    `;
    
    element.appendChild(indicator);
}

/**
 * 過去のツールログを読み込んで表示
 */
export async function loadAndDisplayToolLogs(chatId) {
    try {
        const response = await fetch(`/api/chats/${chatId}/ui_history/logs`);
        if (!response.ok) return;
        
        const data = await response.json();
        const logs = data.logs || [];
        
        if (logs.length === 0) return;
        
        // 実行IDごとにグループ化
        const executionGroups = {};
        logs.forEach(log => {
            const execId = log.execution_id || 'unknown';
            if (!executionGroups[execId]) {
                executionGroups[execId] = [];
            }
            executionGroups[execId].push(log);
        });
        
        // 各実行グループごとにコンテナを作成
        Object.entries(executionGroups).forEach(([execId, execLogs]) => {
            let container = document.getElementById(`tool-execution-${execId}`);
            if (!container) {
                container = createToolLogContainer(execId);
                dom.messagesContainer.appendChild(container);
            }
            
            const contentDiv = container.querySelector('.tool-log-content-area');
            if (contentDiv) {
                execLogs.forEach(log => {
                    appendToolLogEntry(contentDiv, log);
                });
            }
        });
        
    } catch (error) {
        console.error('Failed to load tool logs:', error);
    }
}

/**
 * ツールログコンテナを作成
 */
export function createToolLogContainer(executionId) {
    const container = document.createElement('div');
    container.id = `tool-execution-${executionId}`;
    container.className = 'w-full flex justify-start animate-fadeIn py-4';
    container.innerHTML = `
        <div class="flex items-start gap-3 max-w-3xl w-full">
            <div class="w-8 h-8 flex-shrink-0">
                <img src="${getAIIconSrc()}" class="w-full h-full ai-avatar-icon">
            </div>
            <div class="flex-1 space-y-2">
                <div class="bg-gray-100 dark:bg-gray-700 rounded-xl p-4 space-y-3">
                    <div class="tool-log-content-area space-y-2">
                        <!-- ツールログがここに追加される -->
                    </div>
                </div>
            </div>
        </div>
    `;
    return container;
}

/**
 * ツールログエントリを追加
 */
export function appendToolLogEntry(contentDiv, log) {
    const logDiv = document.createElement('div');
    logDiv.className = 'tool-log-entry';
    logDiv.dataset.messageId = log.message_id || '';
    logDiv.dataset.timestamp = log.timestamp || '';
    
    switch (log.type) {
        case 'ai_explanation':
            logDiv.className += ' text-sm text-gray-800 dark:text-gray-200 font-medium';
            logDiv.innerHTML = `📋 ${escapeHtml(log.message)}`;
            break;
            
        case 'tool_start':
            logDiv.className += ' flex items-center gap-2 text-sm text-blue-600 dark:text-blue-400';
            logDiv.innerHTML = `
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
                <span>${escapeHtml(log.tool_name || log.tool)}を実行開始</span>
            `;
            break;
            
        case 'tool_progress':
            logDiv.className += ' ml-6 text-xs text-gray-600 dark:text-gray-400 italic';
            logDiv.innerHTML = `→ ${escapeHtml(log.message)}`;
            break;
            
        case 'tool_complete':
            logDiv.className += ' flex items-center gap-2 text-sm text-green-600 dark:text-green-400';
            const success = log.result?.success !== false;
            logDiv.innerHTML = `
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
                <span>${escapeHtml(log.tool_name || log.tool)}が${success ? '完了' : 'エラー'}</span>
            `;
            
            if (log.result) {
                const resultDiv = document.createElement('div');
                resultDiv.className = 'ml-6 text-xs text-gray-600 dark:text-gray-400 mt-1';
                const resultText = typeof log.result === 'object' ? 
                    (log.result.result || log.result.error || JSON.stringify(log.result)) : 
                    String(log.result);
                const truncatedResult = resultText.length > 100 ? 
                    resultText.substring(0, 100) + '...' : resultText;
                resultDiv.innerHTML = success ? 
                    `✓ ${escapeHtml(truncatedResult)}` : 
                    `✗ ${escapeHtml(truncatedResult)}`;
                logDiv.appendChild(resultDiv);
            }
            break;
            
        default:
            logDiv.className += ' text-xs text-gray-500';
            logDiv.textContent = JSON.stringify(log);
    }
    
    contentDiv.appendChild(logDiv);
}

/**
 * リアルタイムのツールログを処理
 */
export function handleRealtimeToolLog(log) {
    const execId = log.execution_id || 'current';
    let container = document.getElementById(`tool-execution-${execId}`);
    
    if (!container) {
        container = createToolLogContainer(execId);
        dom.messagesContainer.appendChild(container);
    }
    
    const contentDiv = container.querySelector('.tool-log-content-area');
    if (contentDiv) {
        // 重複チェック
        if (log.message_id && !contentDiv.querySelector(`[data-message-id="${log.message_id}"]`)) {
            appendToolLogEntry(contentDiv, log);
            
            // スクロール
            dom.messagesContainer.scrollTop = dom.messagesContainer.scrollHeight;
        }
    }
}

/**
 * ツールメッセージ表示を更新
 */
export function updateToolMessageDisplay(container, msg) {
    handleRealtimeToolLog(msg);
}
