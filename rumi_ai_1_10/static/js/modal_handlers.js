// static/js/modal_handlers.js

import { state } from './state.js';
import { updateChatMetaOnServer, deleteChatOnServer } from './api.js';
import { dom } from './ui.js';
import { loadChatList, navigateTo } from './main.js';

// モーダル操作関数
export function openRenameModal(chatId, currentTitle) {
    state.chatToInteractId = chatId;
    dom.renameInput.value = currentTitle;
    dom.renameModalOverlay.classList.remove('opacity-0', 'pointer-events-none');
    dom.renameInput.focus();
}

export function closeRenameModal() {
    dom.renameModalOverlay.classList.add('opacity-0', 'pointer-events-none');
}

export function openMoveFolderModal(chatId, currentFolder) {
    state.chatToInteractId = chatId;
    dom.moveFolderSelect.innerHTML = '<option value="">(未分類)</option>';
    const allFolderNames = Object.keys(state.chatListData.folders);
    allFolderNames.forEach(folder => {
        const option = document.createElement('option');
        option.value = folder;
        option.textContent = folder;
        if (folder === currentFolder) option.selected = true;
        dom.moveFolderSelect.appendChild(option);
    });
    dom.newFolderInput.value = '';
    dom.moveFolderModalOverlay.classList.remove('opacity-0', 'pointer-events-none');
}

export function closeMoveFolderModal() {
    dom.moveFolderModalOverlay.classList.add('opacity-0', 'pointer-events-none');
}

export function openDeleteConfirmModal(chatId) {
    state.chatToInteractId = chatId;
    dom.deleteConfirmModalOverlay.classList.remove('opacity-0', 'pointer-events-none');
}

export function closeDeleteConfirmModal() {
    dom.deleteConfirmModalOverlay.classList.add('opacity-0', 'pointer-events-none');
}

export function openSettingsModal() {
    import('./ui.js').then(({ updateSettingsModalUI }) => {
        updateSettingsModalUI();
    });
    dom.settingsModalOverlay.classList.remove('opacity-0', 'pointer-events-none');
}

export function closeSettingsModal() {
    dom.settingsModalOverlay.classList.add('opacity-0', 'pointer-events-none');
}

// モーダル関連ハンドラ
export async function handleSaveRename() {
    const newTitle = dom.renameInput.value.trim();
    if (newTitle && state.chatToInteractId) {
        await updateChatMetaOnServer(state.chatToInteractId, { title: newTitle });
        closeRenameModal();
        await loadChatList();
        if (state.currentChatId === state.chatToInteractId) {
            dom.chatHeaderTitle.textContent = newTitle;
        }
    }
}

export async function handleSaveFolder() {
    let targetFolder = dom.newFolderInput.value.trim() || dom.moveFolderSelect.value;
    if (state.chatToInteractId) {
        await updateChatMetaOnServer(state.chatToInteractId, { folder: targetFolder || null });
        closeMoveFolderModal();
        await loadChatList();
    }
}

export async function handleConfirmDelete() {
    if (!state.chatToInteractId) return;
    const wasCurrentChat = state.currentChatId === state.chatToInteractId;
    const deletedChatId = state.chatToInteractId;
    
    try {
        await deleteChatOnServer(deletedChatId);
        await loadChatList();
        if (wasCurrentChat) {
            navigateTo('/');
        }
    } catch (error) {
        console.error('Error deleting chat:', error);
        alert('チャットの削除に失敗しました。');
    } finally {
        closeDeleteConfirmModal();
        state.chatToInteractId = null;
    }
}
