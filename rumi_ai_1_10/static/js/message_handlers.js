// static/js/message_handlers.js

import { state } from './state.js';
import { sendMessageToServer, createMessageObject, sendMessageToServerStream, sendContinueMessageStream } from './api.js';
import {
    addMessageToDOM, createTypingIndicator, updateSendButtonState,
    createContinueButton, removeAbortIndicators, showAbortedIndicator,
    handleRealtimeToolLog, showToolUIPanel, showToolUIOnStart, dom
} from './ui.js';
import { escapeHtml, getAIIconSrc } from './utils.js';

// --- メッセージ送受信ハンドラ ---
export async function handleSendMessage() {
    // 強制停止モードの場合
    if (state.isAwaitingAIResponse || state.isStreaming) {
        handleAbortRequest();
        return;
    }
    
    const messageText = dom.chatInput.value.trim();
    if (messageText === '' && state.filesToUpload.length === 0) return;

    // 新規チャットの場合のみ、ここでチャットを作成
    if (state.currentChatId === null) {
        try {
            state.isCreatingChat = true;
            const { createNewChatOnServer } = await import('./api.js');
            const { loadChatList } = await import('./main.js');
            
            const newChat = await createNewChatOnServer();
            state.currentChatId = newChat.id;
            await loadChatList();
            
            history.replaceState({ path: `/chats/${newChat.id}` }, '', `/chats/${newChat.id}`);
            
            dom.chatWindow.classList.add('chat-active');
            dom.messagesContainer.innerHTML = '';
        } catch (error) {
            console.error('Failed to create new chat before sending:', error);
            state.isCreatingChat = false;
            return;
        } finally {
            state.isCreatingChat = false;
        }
    }

    const messageObject = await createMessageObject(messageText, state.filesToUpload);
    addMessageToDOM(messageObject);
    resetInputArea();
    getAIResponse(state.currentChatId, messageObject);
}

export async function handleAbortRequest() {
    console.log('Aborting current request...');
    
    if (state.abortController) {
        state.abortController.abort();
        state.wasAborted = true;
    }
    
    try {
        await fetch('/api/stream/abort', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
    } catch (error) {
        console.error('Failed to abort on server:', error);
    }
    
    if (state.isStreaming) {
        const streamingContent = document.querySelector('.streaming-content');
        if (streamingContent) {
            state.lastAbortedText = streamingContent.textContent || '';
        }
    }
    
    stopStreamingAnimations();
    
    state.isAwaitingAIResponse = false;
    state.isStreaming = false;
    
    updateSendButtonState();
    showAbortedMessage();
}

function stopStreamingAnimations() {
    const streamingMessages = document.querySelectorAll('.streaming-message');
    streamingMessages.forEach(msg => {
        msg.classList.remove('streaming-message');
        msg.classList.add('aborted-message');
    });
    
    const streamingContents = document.querySelectorAll('.streaming-content');
    streamingContents.forEach(content => {
        content.classList.remove('streaming-content');
        content.classList.add('complete');
    });
    
    const spinningIcons = document.querySelectorAll('.animate-spin');
    spinningIcons.forEach(icon => {
        icon.classList.remove('animate-spin');
        
        if (icon.innerHTML.includes('M10.325 4.317')) {
            icon.innerHTML = `
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" 
                      d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2"></path>
            `;
            icon.classList.add('text-yellow-600', 'dark:text-yellow-400');
        }
    });
    
    const toolExecutionContainers = document.querySelectorAll('.bg-blue-50.dark\\:bg-blue-900\\/20');
    toolExecutionContainers.forEach(container => {
        const statusText = container.querySelector('span.font-medium');
        if (statusText && statusText.textContent.includes('実行中')) {
            const toolName = statusText.textContent.replace('を実行中...', '');
            statusText.textContent = `${toolName}が中断されました`;
            
            const parentDiv = statusText.parentElement;
            if (parentDiv) {
                parentDiv.className = 'flex items-center gap-2 text-sm text-yellow-700 dark:text-yellow-300';
            }
            
            container.className = 'mt-3 p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg border border-yellow-200 dark:border-yellow-800';
        }
    });
}

function showAbortedMessage() {
    const abortedMessage = document.querySelector('.aborted-message');
    if (abortedMessage) {
        showAbortedIndicator(abortedMessage);
    }
    
    const continueButton = createContinueButton();
    dom.messagesContainer.appendChild(continueButton);
    
    document.getElementById('continue-response-btn')?.addEventListener('click', handleContinueMessage);
    
    dom.messagesContainer.scrollTop = dom.messagesContainer.scrollHeight;
    
    saveAbortedState();
}

export async function handleContinueMessage() {
    removeAbortIndicators();
    
    const continueUserMessage = {
        type: 'user',
        text: '続けてください',
        files: []
    };
    
    addMessageToDOM(continueUserMessage);
    
    dom.messagesContainer.scrollTop = dom.messagesContainer.scrollHeight;
    
    state.isAwaitingAIResponse = true;
    updateSendButtonState();
    
    try {
        if (state.userSettings.streaming_on) {
            const typingIndicator = createTypingIndicator();
            dom.messagesContainer.appendChild(typingIndicator);
            
            handleStreamingResponse(state.currentChatId, continueUserMessage, typingIndicator);
        } else {
            getAIResponse(state.currentChatId, continueUserMessage);
        }
    } catch (error) {
        console.error('Failed to continue:', error);
        showErrorMessage('続きの生成に失敗しました');
        state.isAwaitingAIResponse = false;
        updateSendButtonState();
    }
}

async function saveAbortedState() {
    try {
        const response = await fetch(`/api/chats/${state.currentChatId}/add_system_message`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                type: 'system',
                event: 'force_stop',
                text: state.lastAbortedText,
                timestamp: Date.now()
            })
        });
    } catch (error) {
        console.error('Failed to save aborted state:', error);
    }
}

async function getAIResponse(chatId, userMessage) {
    const typingIndicator = createTypingIndicator();
    dom.messagesContainer.appendChild(typingIndicator);
    dom.messagesContainer.scrollTop = dom.messagesContainer.scrollHeight;
    state.isAwaitingAIResponse = true;
    updateSendButtonState();
    
    let retryIndicator = null;
    
    if (state.userSettings.streaming_on) {
        handleStreamingResponse(chatId, userMessage, typingIndicator);
        return;
    }
    
    async function attemptRequest(retryCount = 0) {
        try {
            const eventSource = new EventSource('/api/tools/messages/stream');
            
            eventSource.onmessage = (event) => {
                const msg = JSON.parse(event.data);
                
                if (typingIndicator.parentElement) typingIndicator.remove();
                if (retryIndicator && retryIndicator.parentElement) retryIndicator.remove();
                
                handleRealtimeToolLog(msg);
                
                dom.messagesContainer.scrollTop = dom.messagesContainer.scrollHeight;
            };
            
            const data = await sendMessageToServer(chatId, userMessage);
            
            eventSource.close();
            
            if (retryIndicator && retryIndicator.parentElement) {
                retryIndicator.remove();
            }
            
            const aiMessageObject = { 
                type: 'ai', 
                text: data.response, 
                files: [],
                tool_executions: data.tool_executions || []
            };
            addMessageToDOM(aiMessageObject);
            
            if (dom.chatHeaderTitle.textContent !== data.metadata.title) {
                dom.chatHeaderTitle.textContent = data.metadata.title;
                const { loadChatList } = await import('./main.js');
                await loadChatList();
            }
            
            return true;
            
        } catch (error) {
            console.error("API request failed:", error);
            
            if (typingIndicator.parentElement) typingIndicator.remove();
            
            if (error.message && (error.message.includes('500') || error.message.includes('503') || error.message.includes('INTERNAL'))) {
                if (retryCount < 3) {
                    if (retryIndicator && retryIndicator.parentElement) {
                        retryIndicator.remove();
                    }
                    
                    retryIndicator = createRetryIndicatorWithCountdown(
                        retryCount + 1,
                        async () => {
                            return await attemptRequest(retryCount + 1);
                        },
                        () => {
                            if (retryIndicator && retryIndicator.parentElement) {
                                retryIndicator.remove();
                            }
                            attemptRequest(retryCount + 1);
                        }
                    );
                    
                    dom.messagesContainer.appendChild(retryIndicator);
                    dom.messagesContainer.scrollTop = dom.messagesContainer.scrollHeight;
                    
                    return false;
                } else {
                    throw error;
                }
            } else {
                throw error;
            }
        }
    }

    try {
        await attemptRequest(0);
    } catch (error) {
        console.error("Failed to get AI response after all retries:", error);
        
        const errorMessage = createFinalErrorMessage(error.message);
        dom.messagesContainer.appendChild(errorMessage);
        dom.messagesContainer.scrollTop = dom.messagesContainer.scrollHeight;
    } finally {
        if (typingIndicator.parentElement) {
            typingIndicator.remove();
        }
        state.isAwaitingAIResponse = false;
        updateSendButtonState();
    }
}

function handleStreamingResponse(chatId, userMessage, typingIndicator) {
    state.abortController = new AbortController();
    state.wasAborted = false;

    let messageWrapper = null;
    let aiTextContainer = null;
    let aiTextElement = null;
    let toolExecutionsContainer = null;
    let fullText = '';
    let toolEventSource = null;

    const startToolMessageListener = () => {
        if (toolEventSource) {
            toolEventSource.close();
        }
        toolEventSource = new EventSource('/api/tools/messages/stream');
        
        toolEventSource.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            const details = document.getElementById(`details-${msg.tool}`);
            if (details) {
                let content = details.querySelector('.tool-log-content');
                if (content && msg.type === 'tool_progress') {
                    const logEntry = document.createElement('div');
                    logEntry.className = 'tool-log-realtime-entry';
                    logEntry.innerHTML = `<span>${escapeHtml(msg.message)}</span>`;
                    content.appendChild(logEntry);
                    content.scrollTop = content.scrollHeight;
                }
            }
        };

        toolEventSource.onerror = () => {
            toolEventSource.close();
        };
    };

    const onChunk = (data) => {
        if (!messageWrapper) {
            if (typingIndicator.parentElement) typingIndicator.remove();
            messageWrapper = document.createElement('div');
            messageWrapper.className = 'w-full flex animate-fadeIn py-4 justify-start';
            const messageContent = document.createElement('div');
            messageContent.className = 'flex items-start gap-3 max-w-3xl';
            const avatar = document.createElement('div');
            avatar.className = 'w-8 h-8 flex-shrink-0';
            avatar.innerHTML = `<img src="${getAIIconSrc()}" class="w-full h-full ai-avatar-icon">`;
            const messageBubble = document.createElement('div');
            messageBubble.className = 'flex flex-col gap-3 ai-message-bubble';
            messageContent.appendChild(avatar);
            messageContent.appendChild(messageBubble);
            messageWrapper.appendChild(messageContent);
            dom.messagesContainer.appendChild(messageWrapper);
        }

        const messageBubble = messageWrapper.querySelector('.ai-message-bubble');

        switch (data.type) {
            case 'chunk':
                if (!aiTextContainer) {
                    aiTextContainer = document.createElement('div');
                    aiTextContainer.className = 'p-4 rounded-xl bg-gray-100 dark:bg-gray-700 streaming-message';
                    aiTextElement = document.createElement('div');
                    aiTextElement.className = 'streaming-content';
                    aiTextContainer.appendChild(aiTextElement);
                    messageBubble.appendChild(aiTextContainer);
                }
                fullText += data.text;
                aiTextElement.innerHTML = marked.parse(fullText);
                break;

            case 'function_call_start':
                if (!toolExecutionsContainer) {
                    toolExecutionsContainer = document.createElement('div');
                    toolExecutionsContainer.className = 'tool-executions-container space-y-2';
                    messageBubble.prepend(toolExecutionsContainer);
                }
                
                startToolMessageListener();

                const details = document.createElement('details');
                details.className = 'tool-log-details';
                details.id = `details-${data.function_name}`;
                details.open = true;

                const summary = document.createElement('summary');
                summary.className = 'tool-log-summary';
                summary.innerHTML = `
                    <span class="tool-log-icon animate-spin">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                    </span>
                    <span class="tool-log-name">${escapeHtml(data.tool_name)}</span>
                    <span class="tool-log-status running">実行中</span>
                `;
                const content = document.createElement('div');
                content.className = 'tool-log-content';
                content.innerHTML = `<div class="tool-log-section"><span class="tool-log-section-title">引数:</span><pre>${JSON.stringify(data.args || {}, null, 2)}</pre></div>`;
                details.appendChild(summary);
                details.appendChild(content);
                toolExecutionsContainer.appendChild(details);

                if (data.ui_info && data.ui_info.ui_available) {
                    showToolUIOnStart(data.function_name, data.tool_name, data.ui_info);
                }
                break;

            case 'function_execution_complete':
                const completedDetails = document.getElementById(`details-${data.execution.function_name}`);
                if (completedDetails) {
                    const summaryEl = completedDetails.querySelector('.tool-log-summary');
                    const icon = summaryEl.querySelector('.tool-log-icon');
                    const status = summaryEl.querySelector('.tool-log-status');
                    icon.classList.remove('animate-spin');
                    icon.innerHTML = data.execution.result?.success === false ? '❌' : '✅';
                    status.textContent = data.execution.result?.success === false ? 'エラー' : '完了';
                    status.className = `tool-log-status ${data.execution.result?.success === false ? 'error' : 'success'}`;
                    
                    const contentEl = completedDetails.querySelector('.tool-log-content');
                    let resultToShow = data.execution.result;
                    if (typeof resultToShow === 'object' && resultToShow !== null) {
                        resultToShow = { ...resultToShow };
                        delete resultToShow.files;
                    }
                    contentEl.innerHTML += `<div class="tool-log-section"><span class="tool-log-section-title">結果:</span><pre>${JSON.stringify(resultToShow, null, 2)}</pre></div>`;
                    
                    setTimeout(() => { completedDetails.open = false; }, 500);
                }
                break;

            case 'tool_progress':
                if (state.currentChatId) {
                    fetch(`/api/chats/${state.currentChatId}/ui_history/append_log`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            type: 'tool_progress',
                            tool: data.tool,
                            tool_name: data.tool_name,
                            message: data.message,
                            execution_id: data.execution_id
                        })
                    }).catch(console.error);
                }
                break;
        }
        dom.messagesContainer.scrollTop = dom.messagesContainer.scrollHeight;
    };

    const onComplete = async (finalText, metadata, wasAborted = false) => {
        if (toolEventSource) toolEventSource.close();
        
        state.isAwaitingAIResponse = false;
        state.isStreaming = false;
        state.abortController = null;
        updateSendButtonState();

        if (wasAborted || state.wasAborted) {
            state.lastAbortedText = finalText;
            stopStreamingAnimations();
            showAbortedMessage();
            return;
        }

        if (aiTextElement) {
            aiTextElement.innerHTML = marked.parse(finalText);
            
            aiTextElement.querySelectorAll('pre').forEach(preElement => {
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
            
            if (aiTextContainer) {
                aiTextContainer.classList.remove('streaming-message');
                aiTextContainer.classList.add('streaming-complete');
            }
            
            aiTextElement.classList.remove('streaming-content');
            aiTextElement.classList.add('complete');
        }

        if (metadata && metadata.title && dom.chatHeaderTitle.textContent !== metadata.title) {
            dom.chatHeaderTitle.textContent = metadata.title;
            const { loadChatList } = await import('./main.js');
            await loadChatList();
        }
    };

    const onError = (error) => {
        if (toolEventSource) toolEventSource.close();
        
        console.error("Streaming error:", error);
        
        if (typingIndicator.parentElement) {
            typingIndicator.remove();
        }
        
        const errorMessage = createFinalErrorMessage(error.message);
        dom.messagesContainer.appendChild(errorMessage);
        dom.messagesContainer.scrollTop = dom.messagesContainer.scrollHeight;
        
        state.isAwaitingAIResponse = false;
        state.isStreaming = false;
        updateSendButtonState();
    };
    
    state.isStreaming = true;
    sendMessageToServerStream(
        chatId,
        userMessage,
        state.abortController.signal,
        onChunk,
        onComplete,
        onError
    );
}

function createRetryIndicatorWithCountdown(retryCount, onCountdownComplete, onManualRetry) {
    const wrapper = document.createElement('div');
    wrapper.className = 'w-full flex justify-start animate-fadeIn py-4';
    wrapper.id = 'retry-indicator-wrapper';
    
    const totalSeconds = 60;
    let remainingSeconds = totalSeconds;
    let countdownInterval = null;
    let isRetrying = false;
    
    wrapper.innerHTML = `
        <div class="flex items-start gap-3 max-w-3xl w-full">
            <div class="w-8 h-8 flex-shrink-0">
                <img src="${getAIIconSrc()}" class="w-full h-full ai-avatar-icon">
            </div>
            <div class="flex-1 p-4 rounded-xl bg-yellow-100 dark:bg-yellow-900/30 border border-yellow-300 dark:border-yellow-700">
                <div class="flex items-center gap-2 mb-3">
                    <svg class="w-5 h-5 animate-spin text-yellow-600 dark:text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
                    </svg>
                    <div class="flex-1">
                        <div class="text-sm font-medium text-yellow-700 dark:text-yellow-300">
                            エラーが発生しました
                        </div>
                        <div class="text-xs text-yellow-600 dark:text-yellow-400">
                            <span id="retry-countdown">${remainingSeconds}</span>秒後に再リクエストします... (試行 ${retryCount}/3)
                        </div>
                    </div>
                </div>
                
                <div class="mb-3">
                    <div class="w-full bg-yellow-200 dark:bg-yellow-800 rounded-full h-2 overflow-hidden">
                        <div id="retry-progress-bar" class="bg-yellow-600 dark:bg-yellow-500 h-2 rounded-full transition-all duration-1000 ease-linear" style="width: 100%;"></div>
                    </div>
                </div>
                
                <div class="flex items-center justify-center mb-3">
                    <div class="relative w-16 h-16">
                        <svg class="w-16 h-16 transform -rotate-90">
                            <circle cx="32" cy="32" r="28" stroke="currentColor" stroke-width="4" fill="none" class="text-yellow-200 dark:text-yellow-800"></circle>
                            <circle id="retry-circle-progress" cx="32" cy="32" r="28" stroke="currentColor" stroke-width="4" fill="none" 
                                class="text-yellow-600 dark:text-yellow-400 transition-all duration-1000 ease-linear"
                                stroke-dasharray="176"
                                stroke-dashoffset="0"></circle>
                        </svg>
                        <div class="absolute inset-0 flex items-center justify-center">
                            <span id="retry-circle-text" class="text-lg font-bold text-yellow-700 dark:text-yellow-300">${remainingSeconds}</span>
                        </div>
                    </div>
                </div>
                
                <div class="flex gap-2">
                    <button id="retry-now-btn" class="flex-1 px-3 py-2 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg text-sm font-medium transition-colors">
                        今すぐ再試行
                    </button>
                    <button id="cancel-retry-btn" class="px-3 py-2 bg-gray-500 hover:bg-gray-600 text-white rounded-lg text-sm font-medium transition-colors">
                        キャンセル
                    </button>
                </div>
            </div>
        </div>
    `;
    
    const startCountdown = () => {
        const countdownText = wrapper.querySelector('#retry-countdown');
        const circleText = wrapper.querySelector('#retry-circle-text');
        const progressBar = wrapper.querySelector('#retry-progress-bar');
        const circleProgress = wrapper.querySelector('#retry-circle-progress');
        
        countdownInterval = setInterval(() => {
            remainingSeconds--;
            
            if (countdownText) countdownText.textContent = remainingSeconds;
            if (circleText) circleText.textContent = remainingSeconds;
            
            const progressPercent = (remainingSeconds / totalSeconds) * 100;
            if (progressBar) progressBar.style.width = `${progressPercent}%`;
            
            const circumference = 2 * Math.PI * 28;
            const offset = circumference - (progressPercent / 100) * circumference;
            if (circleProgress) circleProgress.style.strokeDashoffset = offset;
            
            if (remainingSeconds <= 0 && !isRetrying) {
                isRetrying = true;
                clearInterval(countdownInterval);
                
                wrapper.querySelector('.flex-1.p-4').innerHTML = `
                    <div class="flex items-center gap-2">
                        <svg class="w-5 h-5 animate-spin text-yellow-600 dark:text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
                        </svg>
                        <span class="text-sm font-medium text-yellow-700 dark:text-yellow-300">
                            再リクエスト中...
                        </span>
                    </div>
                `;
                
                if (onCountdownComplete) {
                    onCountdownComplete();
                }
            }
        }, 1000);
    };
    
    setTimeout(() => {
        const retryNowBtn = wrapper.querySelector('#retry-now-btn');
        const cancelBtn = wrapper.querySelector('#cancel-retry-btn');
        
        if (retryNowBtn) {
            retryNowBtn.addEventListener('click', () => {
                if (!isRetrying) {
                    isRetrying = true;
                    clearInterval(countdownInterval);
                    if (onManualRetry) onManualRetry();
                }
            });
        }
        
        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => {
                clearInterval(countdownInterval);
                wrapper.remove();
                state.isAwaitingAIResponse = false;
                updateSendButtonState();
            });
        }
        
        startCountdown();
    }, 0);
    
    return wrapper;
}

function createFinalErrorMessage(errorMessage) {
    const wrapper = document.createElement('div');
    wrapper.className = 'w-full flex justify-start animate-fadeIn py-4';
    
    wrapper.innerHTML = `
        <div class="flex items-start gap-3 max-w-3xl w-full">
            <div class="w-8 h-8 flex-shrink-0">
                <img src="${getAIIconSrc()}" class="w-full h-full ai-avatar-icon">
            </div>
            <div class="flex-1 p-4 rounded-xl bg-red-100 dark:bg-red-900/30 border border-red-300 dark:border-red-700">
                <div class="flex items-start gap-2">
                    <svg class="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    <div class="flex-1">
                        <div class="text-sm font-medium text-red-700 dark:text-red-300 mb-1">
                            リクエストに失敗しました
                        </div>
                        <div class="text-xs text-red-600 dark:text-red-400 mb-3">
                            ${escapeHtml(errorMessage || 'Unknown error')}
                        </div>
                        <button onclick="location.reload()" class="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-medium transition-colors">
                            ページを再読み込み
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    return wrapper;
}

function showErrorMessage(message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'w-full flex justify-center py-2 animate-fadeIn';
    errorDiv.innerHTML = `
        <div class="inline-flex items-center gap-2 px-4 py-2 bg-red-100 dark:bg-red-900/20 rounded-lg text-sm text-red-600 dark:text-red-400">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
            <span>${escapeHtml(message)}</span>
        </div>
    `;
    dom.messagesContainer.appendChild(errorDiv);
    dom.messagesContainer.scrollTop = dom.messagesContainer.scrollHeight;
}

function resetInputArea() {
    dom.chatInput.value = '';
    dom.chatInput.style.height = 'auto';
    state.filesToUpload = [];
    import('./ui.js').then(({ updateFilePreview, updateSendButtonState }) => {
        updateFilePreview();
        updateSendButtonState();
    }).catch(err => {
        console.error('Failed to update UI after reset:', err);
    });
}

// ファイル・ペーストハンドラ
export function handleFileSelect(event) {
    console.log('[DEBUG] handleFileSelect triggered');
    console.log('[DEBUG] event.target:', event.target);
    console.log('[DEBUG] event.target.files:', event.target.files);
    console.log('[DEBUG] Files count:', event.target.files?.length);
    
    const files = event.target.files;
    
    if (files && files.length > 0) {
        // ファイルを配列にコピー（inputリセット前に）
        const fileArray = Array.from(files);
        console.log('[DEBUG] File array:', fileArray.map(f => f.name));
        
        // stateに追加
        state.filesToUpload.push(...fileArray);
        console.log('[DEBUG] State files:', state.filesToUpload.length);
        
        // UIを更新
        import('./ui.js').then(({ updateFilePreview, updateSendButtonState }) => {
            updateFilePreview();
            updateSendButtonState();
            console.log('[DEBUG] UI updated');
        }).catch(err => {
            console.error('[DEBUG] UI update error:', err);
        });
    } else {
        console.log('[DEBUG] No files selected or files is null/undefined');
    }
    
    // inputをリセット（最後に実行）
    event.target.value = '';
}

export function handleFileRemove(event) {
    const indexToRemove = parseInt(event.currentTarget.dataset.fileIndex, 10);
    state.filesToUpload.splice(indexToRemove, 1);
    import('./ui.js').then(({ updateFilePreview, updateSendButtonState }) => {
        updateFilePreview();
        updateSendButtonState();
    }).catch(err => {
        console.error('Failed to update UI after file remove:', err);
    });
}

export function handlePaste(event) {
    const items = event.clipboardData?.items;
    
    // 画像のペーストをチェック
    if (items) {
        for (let i = 0; i < items.length; i++) {
            if (items[i].type.startsWith('image/')) {
                event.preventDefault();
                const file = items[i].getAsFile();
                if (file) {
                    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
                    const newFile = new File([file], `pasted_image_${timestamp}.png`, { type: file.type });
                    state.filesToUpload.push(newFile);
                    import('./ui.js').then(({ updateFilePreview, updateSendButtonState }) => {
                        updateFilePreview();
                        updateSendButtonState();
                    });
                }
                return;
            }
        }
    }
    
    // テキストのペースト（長いテキストはファイルとして扱う）
    const pastedText = (event.clipboardData || window.clipboardData).getData('text');
    if (pastedText.length >= 500) {
        event.preventDefault();
        const blob = new Blob([pastedText], { type: 'text/plain' });
        const fileCount = state.filesToUpload.filter(f => f.name.startsWith('paste_')).length + 1;
        const file = new File([blob], `paste_${fileCount}.txt`, { type: 'text/plain' });
        state.filesToUpload.push(file);
        import('./ui.js').then(({ updateFilePreview, updateSendButtonState }) => {
            updateFilePreview();
            updateSendButtonState();
        });
    }
}
