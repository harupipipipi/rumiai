// static/js/ui_chat_list.js

import { dom } from './ui_dom.js';
import { escapeHtml } from './utils.js';
import { state } from './state.js';
import { addDragAndDropListeners, addDropTargetListeners } from './dnd.js';

export function renderChatList() {
    dom.chatHistoryList.innerHTML = '';
    const { pinned, folders, uncategorized } = state.chatListData;

    // 更新ボタンと複数選択モードのコンテナ
    const controlsContainer = document.createElement('div');
    controlsContainer.className = 'px-2 py-2 mb-2 border-b border-gray-200 dark:border-gray-800 space-y-2';
    
    controlsContainer.innerHTML = `
        <button id="refresh-chats-btn" class="w-full flex items-center justify-center gap-2 p-2 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
            </svg>
            <span class="text-sm font-medium">履歴を更新</span>
        </button>
        <button id="multi-select-toggle" class="w-full flex items-center justify-between p-2 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors">
            <span class="text-sm font-medium">複数選択モード</span>
            <svg class="w-4 h-4 ${state.isMultiSelectMode ? 'rotate-90' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path>
            </svg>
        </button>
        <div id="multi-select-actions" class="${state.isMultiSelectMode ? '' : 'hidden'} space-y-2">
            <button id="multi-delete-btn" class="w-full p-2 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed">
                選択したチャットを削除
            </button>
            <button id="multi-move-btn" class="w-full p-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed">
                選択したチャットを移動
            </button>
        </div>
    `;
    dom.chatHistoryList.appendChild(controlsContainer);

    const createSection = (title, dropTargetName) => {
        const section = document.createElement('div');
        section.className = 'space-y-1';
        if (title) {
            const header = document.createElement('h3');
            header.className = 'px-2 text-xs font-semibold text-gray-500 uppercase tracking-wider my-2';
            header.textContent = title;
            section.appendChild(header);
        }
        const container = document.createElement('div');
        container.className = 'space-y-1';
        if (dropTargetName) {
            container.classList.add('drop-target');
            container.dataset.dropTarget = dropTargetName;
            addDropTargetListeners(container);
        }
        section.appendChild(container);
        return { section, container };
    };

    if (pinned && pinned.length > 0) {
        const { section, container } = createSection('ピン留め済み', null);
        pinned.forEach(chat => container.appendChild(createChatItem(chat)));
        dom.chatHistoryList.appendChild(section);
    }

    const { section: foldersSection, container: foldersContainer } = createSection('フォルダ', null);
    const allFolders = Object.keys(folders || {}).sort();
    if (allFolders.length > 0) {
        allFolders.forEach(folderName => {
            const details = document.createElement('details');
            details.className = 'folder-item drop-target';
            details.dataset.dropTarget = 'folder';
            details.dataset.folderName = folderName;
            addDropTargetListeners(details);

            const summary = document.createElement('summary');
            summary.className = 'list-none flex items-center justify-between gap-2 p-2 rounded-lg cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-700/60';
            summary.innerHTML = `<div class="flex items-center gap-2 truncate"><svg class="w-4 h-4 text-gray-500 transition-transform folder-arrow" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg><span class="font-medium text-sm truncate">${escapeHtml(folderName)}</span></div>`;
            
            const folderContent = document.createElement('div');
            folderContent.className = 'folder-chat-list pt-1 space-y-1';
            (folders[folderName] || []).forEach(chat => folderContent.appendChild(createChatItem(chat)));

            details.appendChild(summary);
            details.appendChild(folderContent);
            foldersContainer.appendChild(details);
        });
    }
    dom.chatHistoryList.appendChild(foldersSection);

    if (uncategorized && uncategorized.length > 0) {
        const { section, container } = createSection('最近のチャット', 'uncategorized');
        uncategorized.forEach(chat => container.appendChild(createChatItem(chat)));
        dom.chatHistoryList.appendChild(section);
    }
    updateActiveChatSelection();
}

function createChatItem(chat) {
    const item = document.createElement('div');
    item.className = 'group flex justify-between items-center p-2 rounded-lg cursor-pointer hover:bg-gray-200 dark:hover:bg-gray-700/60 chat-history-item relative';
    item.dataset.chatId = chat.id;

    if (state.isMultiSelectMode) {
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'mr-2 flex-shrink-0 pointer-events-none';
        checkbox.checked = state.selectedChats.includes(chat.id);
        checkbox.id = `checkbox-${chat.id}`;
        item.prepend(checkbox);
        
        item.onclick = (e) => {
            e.stopPropagation();
            checkbox.checked = !checkbox.checked;
            import('./chat_handlers.js').then(({ handleChatSelection }) => {
                handleChatSelection(chat.id, checkbox.checked);
            });
        };
    } else {
        if (!chat.is_pinned) {
            addDragAndDropListeners(item, chat.id);
        }

        item.onclick = (e) => {
            if (!e.target.closest('.chat-options-btn')) {
                const navigateEvent = new CustomEvent('navigate', { detail: { path: `/chats/${chat.id}` } });
                window.dispatchEvent(navigateEvent);
            }
        };
    }

    const titleContainer = document.createElement('div');
    titleContainer.className = 'flex items-center gap-2 truncate flex-1';
    titleContainer.innerHTML = `<span class="truncate text-sm font-medium">${escapeHtml(chat.title)}</span>`;
    
    const optionsButton = document.createElement('button');
    optionsButton.className = 'chat-options-btn p-1 rounded-full text-gray-500 hover:bg-gray-300 dark:hover:bg-gray-600 transition-opacity flex-shrink-0';
    optionsButton.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16"><path d="M9.5 13a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0zm0-5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0zm0-5a1.5 1.5 0 1 1-3 0 1.5 1.5 0 0 1 3 0z"/></svg>`;
    
    if (!state.isMultiSelectMode) {
        optionsButton.onclick = (e) => {
            e.stopPropagation();
            import('./chat_handlers.js').then(({ openContextMenu }) => {
                openContextMenu(e.currentTarget, chat);
            });
        };
        item.appendChild(titleContainer);
        item.appendChild(optionsButton);
    } else {
        item.appendChild(titleContainer);
    }

    return item;
}

export function updateActiveChatSelection() {
    document.querySelectorAll('.chat-history-item').forEach(item => {
        const isActive = item.dataset.chatId === state.currentChatId;
        item.classList.toggle('bg-gray-200', isActive);
        item.classList.toggle('dark:bg-gray-700/60', isActive);
    });
}
