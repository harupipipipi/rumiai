/**
 * ChatView
 */

import * as api from '../api.js';
import { getState, setCurrentChat, setLoading, setStreaming, appendStreamingText, setStreamError, clearStreamError, subscribe } from '../store.js';
import { getLinearThread, renderMarkdown } from '../utils.js';
import { showPromptModal } from './Modal.js';
import { loadUIHistory, toggleUIHistoryPanel, isUIHistoryVisible } from './UIHistoryPanel.js';

let containerEl = null;
let streamController = null;
let lastMessageText = '';
let loadChatsFunc = null;

export function setLoadChatsFunc(fn) { loadChatsFunc = fn; }
function reloadChatList() { if (loadChatsFunc) loadChatsFunc(); }

export function initChatView(container) { containerEl = container; subscribe(render); }

export async function loadChat(chatId) {
  setLoading(true);
  try {
    const chatData = await api.getChat(chatId);
    setCurrentChat(chatId, chatData);
    await loadUIHistory(chatId);
  } catch (e) { setCurrentChat(chatId, null); }
  finally { setLoading(false); }
}

export function clearChat() { setCurrentChat(null, null); }

function render() {
  const { currentChatId, currentChat, isLoading, isStreaming, streamingText, streamError } = getState();
  if (!currentChatId) { renderWelcome(); return; }
  if (isLoading) { renderLoading(); return; }
  renderChat(currentChat, isStreaming, streamingText, streamError);
}

function renderWelcome() {
  containerEl.innerHTML = '<div class="welcome"><h1>Rumi AI</h1><p>チャットを選択するか、新しいチャットを開始してください</p></div>';
}

function renderLoading() {
  containerEl.innerHTML = '<div class="loading"><div class="loading-spinner"></div><p>読み込み中...</p></div>';
}

function renderChat(chat, isStreaming, streamingText, streamError) {
  const messages = chat ? getLinearThread(chat) : [];
  const chatId = chat?.conversation_id || '';
  const chatTitle = chat?.title || '新しいチャット';
  const isPinned = chat?.is_pinned || false;
  const logsActive = isUIHistoryVisible();
  
  const escapeHtml = (t) => { if (!t) return ''; const d = document.createElement('div'); d.textContent = t; return d.innerHTML; };
  
  const renderMessage = (msg) => {
    const isUser = msg.role === 'user';
    const isAssistant = msg.role === 'assistant';
    let content = msg.content || '';
    if (isAssistant) content = renderMarkdown(content);
    else content = escapeHtml(content).replace(/\n/g, '<br>');
    return `<div class="message ${msg.role}"><div class="message-avatar">${isUser ? '👤' : isAssistant ? '🤖' : '🔧'}</div><div class="message-content">${content}</div></div>`;
  };
  
  containerEl.innerHTML = `
    <div class="chat-header">
      <div class="chat-header-title">
        <h2 class="chat-title">${escapeHtml(chatTitle)}</h2>
        <button class="btn-icon btn-edit-title" title="名前を変更"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg></button>
      </div>
      <div class="chat-header-actions">
        <button class="btn-icon btn-toggle-logs ${logsActive ? 'active' : ''}" title="実行ログ"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg></button>
        <button class="btn-icon btn-toggle-pin ${isPinned ? 'pinned' : ''}" title="${isPinned ? 'ピン留め解除' : 'ピン留め'}">${isPinned ? '📌' : '📍'}</button>
      </div>
    </div>
    <div class="messages-container" id="messages">
      ${messages.map(renderMessage).join('')}
      ${isStreaming ? `<div class="message assistant streaming"><div class="message-avatar">🤖</div><div class="message-content">${renderMarkdown(streamingText)}<span class="cursor">▌</span></div></div>` : ''}
      ${streamError ? `<div class="message error"><div class="message-avatar">⚠️</div><div class="message-content error-content"><p>${escapeHtml(streamError?.message || 'エラーが発生しました')}</p><button class="btn-retry">再試行</button></div></div>` : ''}
    </div>
    <div class="input-container">
      <form id="message-form" class="message-form">
        <textarea id="message-input" class="message-input" placeholder="メッセージを入力..." rows="1" ${isStreaming ? 'disabled' : ''}></textarea>
        ${isStreaming ? '<button type="button" class="btn-abort"><span class="abort-icon">■</span> 停止</button>' : '<button type="submit" class="btn-send">送信</button>'}
      </form>
    </div>
  `;
  
  const form = containerEl.querySelector('#message-form');
  const input = containerEl.querySelector('#message-input');
  form?.addEventListener('submit', handleSubmit);
  input?.addEventListener('keydown', handleKeydown);
  input?.addEventListener('input', autoResize);
  containerEl.querySelector('.btn-abort')?.addEventListener('click', handleAbort);
  containerEl.querySelector('.btn-edit-title')?.addEventListener('click', handleEditTitle);
  containerEl.querySelector('.btn-toggle-pin')?.addEventListener('click', handleTogglePin);
  containerEl.querySelector('.btn-toggle-logs')?.addEventListener('click', handleToggleLogs);
  
  if (!isStreaming) input?.focus();
  scrollToBottom();
}

async function handleSubmit(e) {
  e.preventDefault();
  const input = containerEl.querySelector('#message-input');
  const text = input.value.trim();
  if (!text) return;
  const { currentChatId } = getState();
  if (!currentChatId) return;
  lastMessageText = text;
  input.value = '';
  autoResize.call(input);
  clearStreamError();
  setStreaming(true, '');
  
  streamController = api.sendMessageStream(currentChatId, text, {
    onChunk: (chunk) => { appendStreamingText(chunk); scrollToBottom(); },
    onComplete: async () => { setStreaming(false); await loadChat(currentChatId); reloadChatList(); },
    onError: (err) => { setStreamError(err); }
  });
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); containerEl.querySelector('#message-form')?.dispatchEvent(new Event('submit')); }
}

function autoResize() { this.style.height = 'auto'; this.style.height = Math.min(this.scrollHeight, 200) + 'px'; }

async function handleAbort() {
  if (streamController) { streamController.abort(); streamController = null; }
  try { await api.abortStream(); } catch (e) {}
  setStreaming(false);
  const { currentChatId } = getState();
  if (currentChatId) await loadChat(currentChatId);
}

function scrollToBottom() {
  requestAnimationFrame(() => {
    const messages = containerEl.querySelector('#messages');
    if (messages) messages.scrollTo({ top: messages.scrollHeight, behavior: 'smooth' });
  });
}

async function handleEditTitle() {
  const { currentChatId, currentChat } = getState();
  if (!currentChatId) return;
  const currentTitle = currentChat?.title || '新しいチャット';
  showPromptModal({
    title: 'チャット名を変更',
    placeholder: '新しい名前',
    defaultValue: currentTitle,
    onConfirm: async (newTitle) => {
      if (!newTitle || newTitle === currentTitle) return;
      try { await api.updateChat(currentChatId, { title: newTitle }); await loadChat(currentChatId); reloadChatList(); } catch (e) {}
    }
  });
}

async function handleTogglePin() {
  const { currentChatId, currentChat } = getState();
  if (!currentChatId) return;
  try { await api.updateChat(currentChatId, { is_pinned: !currentChat?.is_pinned }); await loadChat(currentChatId); reloadChatList(); } catch (e) {}
}

function handleToggleLogs() { toggleUIHistoryPanel(); render(); }

document.addEventListener('click', (e) => {
  if (e.target.closest('.btn-retry')) {
    const input = containerEl?.querySelector('#message-input');
    if (input && lastMessageText) { input.value = lastMessageText; clearStreamError(); input.focus(); }
  }
});
