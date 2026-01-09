// static/js/chat_handlers.js

import { state } from './state.js';
import { createNewChatOnServer, updateChatMetaOnServer, copyChatOnServer, deleteChatOnServer, createFolderOnServer } from './api.js';
import { renderChatList, dom } from './ui.js';
import { loadChatList, navigateTo } from './main.js';

// 新規チャット・フォルダ作成ハンドラー
export async function handleNewChat() {
    if (state.currentChatId === null) {
        return;
    }
    navigateTo('/');
}

export async function handleNewFolder() {
    const folderName = prompt('新しいフォルダの名前を入力してください:');
    if (!folderName || !folderName.trim()) return;
    
    try {
        await createFolderOnServer(folderName.trim());
        await loadChatList();
    } catch (error) {
        console.error('Failed to create folder:', error);
        alert('フォルダの作成に失敗しました。');
    }
}

// コンテキストメニュー
export function openContextMenu(button, chat) {
    const existingMenu = document.getElementById('chat-context-menu');
    if (existingMenu) existingMenu.remove();
    const menu = document.createElement('div');
    menu.id = 'chat-context-menu';
    menu.className = 'absolute right-0 top-full mt-1 z-20 w-48 bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 p-2';
    
    const createMenuItem = (text, action, isDestructive = false) => {
        const item = document.createElement('button');
        item.className = `w-full text-left px-3 py-2 text-sm rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2 ${isDestructive ? 'text-red-600 dark:text-red-500' : ''}`;
        item.innerHTML = `<span>${text}</span>`;
        item.onclick = (e) => { e.stopPropagation(); action(); menu.remove(); };
        return item;
    };
    
    menu.appendChild(createMenuItem(chat.is_pinned ? 'ピン留め解除' : 'ピン留め', () => togglePin(chat.id, !chat.is_pinned)));
    menu.appendChild(createMenuItem('名前を変更', () => {
        import('./modal_handlers.js').then(({ openRenameModal }) => {
            openRenameModal(chat.id, chat.title);
        });
    }));
    menu.appendChild(createMenuItem('フォルダへ移動...', () => {
        import('./modal_handlers.js').then(({ openMoveFolderModal }) => {
            openMoveFolderModal(chat.id, chat.folder);
        });
    }));
    menu.appendChild(createMenuItem('コピー', () => handleCopyChat(chat.id)));
    menu.appendChild(createMenuItem('削除', () => {
        import('./modal_handlers.js').then(({ openDeleteConfirmModal }) => {
            openDeleteConfirmModal(chat.id);
        });
    }, true));
    
    button.parentElement.appendChild(menu);
    document.addEventListener('click', () => menu.remove(), { once: true });
}

// チャット操作ハンドラ
async function togglePin(chatId, is_pinned) {
    await updateChatMetaOnServer(chatId, { is_pinned });
    await loadChatList();
}

async function handleCopyChat(chatId) {
    await copyChatOnServer(chatId);
    await loadChatList();
}

// 複数選択関連ハンドラ
export function handleMultiSelectToggle() {
    state.isMultiSelectMode = !state.isMultiSelectMode;
    state.selectedChats = [];
    renderChatList();
}

export function handleChatSelection(chatId, isSelected) {
    if (isSelected) {
        if (!state.selectedChats.includes(chatId)) {
            state.selectedChats.push(chatId);
        }
    } else {
        state.selectedChats = state.selectedChats.filter(id => id !== chatId);
    }
    updateMultiSelectButtons();
}

function updateMultiSelectButtons() {
    const hasSelection = state.selectedChats.length > 0;
    const deleteBtn = document.getElementById('multi-delete-btn');
    const moveBtn = document.getElementById('multi-move-btn');
    
    if (deleteBtn) {
        deleteBtn.disabled = !hasSelection;
        deleteBtn.textContent = hasSelection 
            ? `選択したチャット(${state.selectedChats.length}個)を削除` 
            : '選択したチャットを削除';
    }
    if (moveBtn) {
        moveBtn.disabled = !hasSelection;
        moveBtn.textContent = hasSelection 
            ? `選択したチャット(${state.selectedChats.length}個)を移動` 
            : '選択したチャットを移動';
    }
}

export async function handleMultiDelete() {
    if (state.selectedChats.length === 0) return;
    
    const count = state.selectedChats.length;
    if (!confirm(`${count}個のチャットを削除しますか？この操作は取り消せません。`)) {
        return;
    }
    
    try {
        for (const chatId of state.selectedChats) {
            await deleteChatOnServer(chatId);
        }
        
        if (state.selectedChats.includes(state.currentChatId)) {
            navigateTo('/');
        }
        
        state.selectedChats = [];
        await loadChatList();
    } catch (error) {
        console.error('Failed to delete chats:', error);
        alert('一部のチャットの削除に失敗しました。');
    }
}

export async function handleMultiMove() {
    if (state.selectedChats.length === 0) return;
    openMultiMoveFolderModal();
}

function openMultiMoveFolderModal() {
    const modal = document.getElementById('multi-move-modal-overlay');
    const folderSelect = document.getElementById('multi-move-folder-select');
    const selectedCount = document.getElementById('selected-count');
    
    selectedCount.textContent = state.selectedChats.length;
    
    folderSelect.innerHTML = '<option value="">(未分類)</option>';
    const allFolderNames = Object.keys(state.chatListData.folders);
    allFolderNames.forEach(folder => {
        const option = document.createElement('option');
        option.value = folder;
        option.textContent = folder;
        folderSelect.appendChild(option);
    });
    
    document.getElementById('multi-new-folder-input').value = '';
    modal.classList.remove('opacity-0', 'pointer-events-none');
}

export async function handleSaveMultiMove() {
    const folderSelect = document.getElementById('multi-move-folder-select');
    const newFolderInput = document.getElementById('multi-new-folder-input');
    let targetFolder = newFolderInput.value.trim() || folderSelect.value;
    
    if (targetFolder === '' && folderSelect.value === '') {
        targetFolder = null;
    }
    
    try {
        for (const chatId of state.selectedChats) {
            await updateChatMetaOnServer(chatId, { folder: targetFolder });
        }
        
        state.selectedChats = [];
        state.isMultiSelectMode = false;
        await loadChatList();
        
        document.getElementById('multi-move-modal-overlay').classList.add('opacity-0', 'pointer-events-none');
    } catch (error) {
        console.error('Failed to move chats:', error);
        alert('一部のチャットの移動に失敗しました。');
    }
}
