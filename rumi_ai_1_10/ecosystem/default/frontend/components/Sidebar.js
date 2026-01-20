/**
 * Sidebar
 */

import * as api from '../api.js';
import { getState, setChats, setChatsLoading, setSidebarOpen, subscribe } from '../store.js';
import { navigate } from '../router.js';
import { showContextMenu } from './ContextMenu.js';
import { showPromptModal, showConfirmModal, showSelectModal } from './Modal.js';
import { openSettings } from './SettingsModal.js';
import { showError } from './Toast.js';

let sidebarEl = null;
let collapsedFolders = new Set();

try {
  const saved = localStorage.getItem('rumi_collapsed_folders');
  if (saved) collapsedFolders = new Set(JSON.parse(saved));
} catch (e) {}

function saveCollapsedState() {
  try { localStorage.setItem('rumi_collapsed_folders', JSON.stringify([...collapsedFolders])); } catch (e) {}
}

export function initSidebar(container) {
  sidebarEl = container;
  render();
  subscribe(render);
  loadChats();
}

export async function loadChats() {
  setChatsLoading(true);
  try { const chats = await api.fetchChats(); setChats(chats); }
  catch (e) { showError('チャット一覧の読み込みに失敗しました'); setChatsLoading(false); }
}

function render() {
  const { chats, currentChatId, isChatsLoading, isSidebarOpen, isMobile } = getState();
  if (isMobile) sidebarEl.classList.toggle('open', isSidebarOpen);
  else sidebarEl.classList.remove('open');
  
  const escapeHtml = (t) => { if (!t) return ''; const d = document.createElement('div'); d.textContent = t; return d.innerHTML; };
  const escapeAttr = (t) => (t || '').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  
  const renderChatItem = (chat) => {
    const isActive = chat.id === currentChatId;
    const isEmpty = chat.is_empty;
    const isPinned = chat.is_pinned;
    return `<div class="chat-item ${isActive ? 'active' : ''} ${isEmpty ? 'empty' : ''}" data-chat-id="${chat.id}" data-pinned="${isPinned}" data-folder="${escapeAttr(chat.folder || '')}" role="listitem" tabindex="0"><div class="chat-item-content"><div class="chat-title">${escapeHtml(chat.title || '新しいチャット')}</div></div><button class="btn-icon btn-chat-menu" data-chat-id="${chat.id}" title="メニュー"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="1"></circle><circle cx="12" cy="5" r="1"></circle><circle cx="12" cy="19" r="1"></circle></svg></button></div>`;
  };
  
  const renderPinned = (pinned) => {
    if (!pinned?.length) return '';
    return `<div class="sidebar-section"><div class="section-header"><span class="section-icon">📌</span><span class="section-title">ピン留め</span></div><div class="chat-list" role="list">${pinned.map(renderChatItem).join('')}</div></div>`;
  };
  
  const renderFolders = (folders) => {
    if (!folders || !Object.keys(folders).length) return '';
    return Object.entries(folders).map(([name, items]) => {
      const isCollapsed = collapsedFolders.has(name);
      return `<div class="sidebar-section folder-section" data-folder="${escapeAttr(name)}"><div class="section-header folder-header" data-folder="${escapeAttr(name)}"><button class="folder-toggle ${isCollapsed ? 'collapsed' : ''}" data-folder="${escapeAttr(name)}"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg></button><span class="section-icon">📁</span><span class="section-title folder-name">${escapeHtml(name)}</span><span class="folder-count">${items.length}</span></div><div class="chat-list folder-content ${isCollapsed ? 'collapsed' : ''}" role="list">${items.map(renderChatItem).join('')}</div></div>`;
    }).join('');
  };
  
  const renderUncategorized = (list) => {
    if (!list?.length) return `<div class="sidebar-section"><div class="sidebar-empty"><p>チャットがありません</p><p class="sidebar-empty-hint">「+」ボタンで新しいチャットを開始</p></div></div>`;
    return `<div class="sidebar-section"><div class="chat-list" role="list">${list.map(renderChatItem).join('')}</div></div>`;
  };
  
  sidebarEl.innerHTML = `
    <div class="sidebar-header">
      <h2>チャット</h2>
      <div class="sidebar-header-actions">
        <button class="btn-icon btn-settings" title="設定"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg></button>
        <button class="btn-icon btn-new-folder" title="新規フォルダ"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path><line x1="12" y1="11" x2="12" y2="17"></line><line x1="9" y1="14" x2="15" y2="14"></line></svg></button>
        <button class="btn-icon btn-new-chat" title="新規チャット"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg></button>
      </div>
    </div>
    <div class="sidebar-content">
      ${isChatsLoading ? '<div class="sidebar-skeleton">' + '<div class="skeleton-item"><div class="skeleton-line"></div></div>'.repeat(5) + '</div>' : renderPinned(chats.pinned) + renderFolders(chats.folders) + renderUncategorized(chats.uncategorized)}
    </div>
  `;
  
  bindEvents();
}

function bindEvents() {
  sidebarEl.querySelector('.btn-settings')?.addEventListener('click', openSettings);
  sidebarEl.querySelector('.btn-new-chat')?.addEventListener('click', handleNewChat);
  sidebarEl.querySelector('.btn-new-folder')?.addEventListener('click', handleNewFolder);
  
  sidebarEl.querySelectorAll('.chat-item').forEach(el => {
    el.addEventListener('click', (e) => { if (!e.target.closest('.btn-chat-menu')) handleChatClick(el.dataset.chatId); });
    el.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleChatClick(el.dataset.chatId); } });
    el.addEventListener('contextmenu', (e) => { e.preventDefault(); showChatContextMenu(el.dataset.chatId, e.clientX, e.clientY); });
  });
  
  sidebarEl.querySelectorAll('.btn-chat-menu').forEach(el => {
    el.addEventListener('click', (e) => { e.stopPropagation(); const rect = el.getBoundingClientRect(); showChatContextMenu(el.dataset.chatId, rect.right, rect.bottom); });
  });
  
  sidebarEl.querySelectorAll('.folder-toggle').forEach(el => {
    el.addEventListener('click', (e) => { e.stopPropagation(); toggleFolder(el.dataset.folder); });
  });
  
  sidebarEl.querySelectorAll('.folder-header').forEach(el => {
    el.addEventListener('click', () => toggleFolder(el.dataset.folder));
  });
}

function toggleFolder(name) {
  if (collapsedFolders.has(name)) collapsedFolders.delete(name);
  else collapsedFolders.add(name);
  saveCollapsedState();
  render();
}

function showChatContextMenu(chatId, x, y) {
  const chatEl = sidebarEl.querySelector(`.chat-item[data-chat-id="${chatId}"]`);
  const isPinned = chatEl?.dataset.pinned === 'true';
  const currentFolder = chatEl?.dataset.folder || null;
  const { chats } = getState();
  const folderNames = Object.keys(chats.folders || {});
  
  showContextMenu({ x, y, items: [
    { icon: '✏️', label: '名前を変更', action: () => handleRename(chatId) },
    { icon: isPinned ? '📌' : '📍', label: isPinned ? 'ピン留め解除' : 'ピン留め', action: () => handleTogglePin(chatId, !isPinned) },
    { icon: '📋', label: 'コピーを作成', action: () => handleCopy(chatId) },
    { separator: true },
    { icon: '📁', label: 'フォルダに移動', action: () => handleMoveToFolder(chatId, currentFolder, folderNames) },
    { separator: true },
    { icon: '🗑️', label: '削除', danger: true, action: () => handleDelete(chatId) }
  ]});
}

async function handleNewChat() {
  try {
    const chat = await api.createChat();
    await loadChats();
    navigate(`/chats/${chat.id}`);
    const { isMobile } = getState();
    if (isMobile) setSidebarOpen(false);
  } catch (e) { showError('チャットの作成に失敗しました'); }
}

async function handleNewFolder() {
  showPromptModal({
    title: '新規フォルダ',
    placeholder: 'フォルダ名を入力',
    onConfirm: async (name) => {
      if (!name) return;
      try { await api.createFolder(name); await loadChats(); }
      catch (e) { showError('フォルダの作成に失敗しました'); }
    }
  });
}

function handleChatClick(chatId) {
  navigate(`/chats/${chatId}`);
  const { isMobile } = getState();
  if (isMobile) setSidebarOpen(false);
}

async function handleRename(chatId) {
  const { chats } = getState();
  let currentTitle = '新しいチャット';
  const all = [...(chats.pinned || []), ...(chats.uncategorized || []), ...Object.values(chats.folders || {}).flat()];
  const chat = all.find(c => c.id === chatId);
  if (chat) currentTitle = chat.title || currentTitle;
  
  showPromptModal({
    title: 'チャット名を変更',
    placeholder: '新しい名前',
    defaultValue: currentTitle,
    onConfirm: async (newTitle) => {
      if (!newTitle || newTitle === currentTitle) return;
      try { await api.updateChat(chatId, { title: newTitle }); await loadChats(); }
      catch (e) { showError('名前の変更に失敗しました'); }
    }
  });
}

async function handleTogglePin(chatId, shouldPin) {
  try { await api.updateChat(chatId, { is_pinned: shouldPin }); await loadChats(); }
  catch (e) { showError('ピン留めの変更に失敗しました'); }
}

async function handleCopy(chatId) {
  try { const result = await api.copyChat(chatId); await loadChats(); navigate(`/chats/${result.new_chat_id}`); }
  catch (e) { showError('コピーに失敗しました'); }
}

async function handleMoveToFolder(chatId, currentFolder, folderNames) {
  const items = [{ icon: '📄', label: 'フォルダなし（ルート）', value: '' }, ...folderNames.map(n => ({ icon: n === currentFolder ? '📂' : '📁', label: n, value: n }))];
  showSelectModal({
    title: '移動先フォルダを選択',
    items,
    onSelect: async (folder) => {
      try { await api.updateChat(chatId, { folder: folder || null }); await loadChats(); }
      catch (e) { showError('移動に失敗しました'); }
    }
  });
}

async function handleDelete(chatId) {
  showConfirmModal({
    title: 'チャットを削除',
    message: 'このチャットを削除しますか？この操作は取り消せません。',
    confirmLabel: '削除',
    danger: true,
    onConfirm: async () => {
      try {
        await api.deleteChat(chatId);
        await loadChats();
        const { currentChatId } = getState();
        if (currentChatId === chatId) navigate('/');
      } catch (e) { showError('削除に失敗しました'); }
    }
  });
}
