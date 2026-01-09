// static/js/dnd.js

import { updateChatMetaOnServer } from './api.js';
import { loadChatList } from './main.js'; // main.jsからチャットリスト更新関数をインポート

function handleDragStart(e, chatId) {
    e.dataTransfer.setData('text/plain', chatId);
    e.dataTransfer.effectAllowed = 'move';
    e.currentTarget.classList.add('dragging');
}

function handleDragEnd(e) {
    e.currentTarget.classList.remove('dragging');
    // すべてのドロップターゲットのハイライトを削除
    document.querySelectorAll('.drop-target').forEach(el => el.classList.remove('drag-over'));
}

function handleDragOver(e) {
    e.preventDefault();
    const dropTarget = e.currentTarget.closest('.drop-target');
    if (dropTarget) {
        dropTarget.classList.add('drag-over');
    }
}

function handleDragLeave(e) {
    const dropTarget = e.currentTarget.closest('.drop-target');
    if (dropTarget) {
        dropTarget.classList.remove('drag-over');
    }
}

async function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    const dropTarget = e.currentTarget.closest('.drop-target');
    dropTarget.classList.remove('drag-over');
    
    const chatId = e.dataTransfer.getData('text/plain');
    if (!chatId) return;

    let targetFolder = null;
    
    // ドロップターゲットの判定
    if (dropTarget.dataset.dropTarget === 'folder') {
        targetFolder = dropTarget.dataset.folderName;
    } else if (dropTarget.dataset.dropTarget === 'uncategorized') {
        targetFolder = null; // 未分類はnull
    }

    // targetFolderがundefinedでない場合のみ処理
    if (targetFolder !== undefined) {
        try {
            await updateChatMetaOnServer(chatId, { folder: targetFolder || null });
            await loadChatList(); // 変更を反映するためにリストを再読み込み
        } catch (error) {
            console.error('Failed to move chat:', error);
        }
    }
}

export function addDragAndDropListeners(element, chatId) {
    element.draggable = true;
    element.addEventListener('dragstart', (e) => handleDragStart(e, chatId));
    element.addEventListener('dragend', handleDragEnd);
}

export function addDropTargetListeners(element) {
    element.addEventListener('dragover', handleDragOver);
    element.addEventListener('dragleave', handleDragLeave);
    element.addEventListener('drop', handleDrop);
}
