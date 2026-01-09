// static/js/handlers.js

// このファイルは分割されたハンドラをエクスポートするインデックスファイルとして残します

// 各ハンドラモジュールからエクスポート
export * from './message_handlers.js';
export * from './chat_handlers.js';
export * from './modal_handlers.js';
export * from './settings_handlers.js';

import { dom } from './ui.js';
import { saveUserSettingsToServer } from './api.js';
import { state } from './state.js';
import { 
    handleSendMessage, 
    handleFileSelect, 
    handlePaste 
} from './message_handlers.js';
import { 
    handleNewChat, 
    handleNewFolder,
    handleMultiSelectToggle,
    handleMultiDelete,
    handleMultiMove,
    handleSaveMultiMove
} from './chat_handlers.js';
import {
    openSettingsModal,
    closeSettingsModal,
    handleSaveRename,
    closeRenameModal,
    handleSaveFolder,
    closeMoveFolderModal,
    handleConfirmDelete,
    closeDeleteConfirmModal
} from './modal_handlers.js';
import {
    handleThemeToggle,
    handleModelChange,
    handleThinkingToggle,
    handlePromptChange,
    loadToolsSettings
} from './settings_handlers.js';

// イベントリスナー設定
export function setupEventListeners() {
    // メッセージ入力
    dom.sendBtn.addEventListener('click', handleSendMessage);
    dom.chatInput.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSendMessage(); } });
    dom.chatInput.addEventListener('input', () => {
        import('./ui.js').then(({ updateSendButtonState }) => {
            updateSendButtonState();
        });
        dom.chatInput.style.height = 'auto';
        dom.chatInput.style.height = `${dom.chatInput.scrollHeight}px`;
    });
    dom.chatInput.addEventListener('paste', handlePaste);
    document.getElementById('file-upload').addEventListener('change', handleFileSelect);

    // サイドバー
    document.getElementById('menu-toggle').addEventListener('click', () => dom.sidebar.classList.toggle('open'));
    dom.themeToggleBtn.addEventListener('click', handleThemeToggle);
    document.getElementById('settings-btn').addEventListener('click', openSettingsModal);
    document.getElementById('new-chat-btn').addEventListener('click', handleNewChat);
    document.getElementById('new-folder-btn').addEventListener('click', handleNewFolder);

    // モデル・プロンプト選択
    dom.modelSelectBtn.addEventListener('click', (e) => { e.stopPropagation(); dom.modelSelectMenu.classList.toggle('visible'); });
    document.addEventListener('click', () => { if (dom.modelSelectMenu.classList.contains('visible')) dom.modelSelectMenu.classList.remove('visible'); });
    dom.modelOptions.forEach(option => { option.addEventListener('click', (e) => { e.stopPropagation(); handleModelChange(option.dataset.model); }); });
    dom.promptSelectContainer.addEventListener('click', (e) => {
        const btn = e.target.closest('button');
        if (!btn) return;
        if (btn.id === 'prompt-select-btn') {
            e.stopPropagation();
            document.getElementById('prompt-select-menu').classList.toggle('visible');
        } else if (btn.classList.contains('prompt-option')) {
            e.stopPropagation();
            handlePromptChange(btn.dataset.promptId);
        }
    });
    document.addEventListener('click', () => {
        const menu = document.getElementById('prompt-select-menu');
        if (menu && menu.classList.contains('visible')) menu.classList.remove('visible');
    });

    // 思考ボタン
    dom.thinkingBtn.addEventListener('click', handleThinkingToggle);

    // モーダル
    document.getElementById('save-rename-btn').addEventListener('click', handleSaveRename);
    document.getElementById('cancel-rename-btn').addEventListener('click', closeRenameModal);
    dom.renameModalOverlay.addEventListener('click', (e) => { if (e.target === dom.renameModalOverlay) closeRenameModal(); });

    document.getElementById('save-move-folder-btn').addEventListener('click', handleSaveFolder);
    document.getElementById('cancel-move-folder-btn').addEventListener('click', closeMoveFolderModal);
    dom.moveFolderModalOverlay.addEventListener('click', (e) => { if (e.target === dom.moveFolderModalOverlay) closeMoveFolderModal(); });

    document.getElementById('confirm-delete-btn').addEventListener('click', handleConfirmDelete);
    document.getElementById('cancel-delete-btn').addEventListener('click', closeDeleteConfirmModal);
    dom.deleteConfirmModalOverlay.addEventListener('click', (e) => { if (e.target === dom.deleteConfirmModalOverlay) closeDeleteConfirmModal(); });
    
    document.getElementById('close-settings-btn').addEventListener('click', closeSettingsModal);
    dom.settingsModalOverlay.addEventListener('click', (e) => { if (e.target === dom.settingsModalOverlay) closeSettingsModal(); });

    // ストリーミング設定
    document.getElementById('streaming-toggle')?.addEventListener('change', (e) => {
        state.userSettings.streaming_on = e.target.checked;
        saveUserSettingsToServer(state.userSettings);
    });

    // デバッグモード設定
    document.getElementById('debug-toggle')?.addEventListener('change', (e) => {
        state.userSettings.debug_mode = e.target.checked;
        saveUserSettingsToServer(state.userSettings);
        
        // デバッグステータスの表示切り替え
        const debugStatus = document.getElementById('debug-status');
        if (debugStatus) {
            if (e.target.checked) {
                debugStatus.classList.remove('hidden');
            } else {
                debugStatus.classList.add('hidden');
            }
        }
    });

    // 複数選択モーダル
    document.getElementById('save-multi-move-btn')?.addEventListener('click', handleSaveMultiMove);
    document.getElementById('cancel-multi-move-btn')?.addEventListener('click', () => {
        document.getElementById('multi-move-modal-overlay').classList.add('opacity-0', 'pointer-events-none');
    });

    // 予算スライダー
    const budgetSliders = [dom.budgetProSlider, dom.budgetFlashSlider, dom.budgetLiteSlider];
    budgetSliders.forEach(slider => {
        slider.addEventListener('change', () => {
            state.userSettings.thinking_budget_pro = dom.budgetProSlider.value;
            state.userSettings.thinking_budget_flash = dom.budgetFlashSlider.value;
            state.userSettings.thinking_budget_lite = dom.budgetLiteSlider.value;
            import('./ui.js').then(({ updateAllUI }) => {
                updateAllUI();
            });
            saveUserSettingsToServer(state.userSettings);
        });
    });

    // 動的に追加されるボタンのイベントリスナー
    document.addEventListener('click', async (e) => {
        if (e.target.id === 'refresh-chats-btn' || e.target.closest('#refresh-chats-btn')) {
            const btn = document.getElementById('refresh-chats-btn');
            const originalContent = btn.innerHTML;
            btn.innerHTML = '<svg class="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg><span class="text-sm font-medium">更新中...</span>';
            btn.disabled = true;
            
            try {
                const { loadChatList } = await import('./main.js');
                await loadChatList();
            } finally {
                btn.innerHTML = originalContent;
                btn.disabled = false;
            }
        } else if (e.target.id === 'multi-select-toggle') {
            handleMultiSelectToggle();
        } else if (e.target.id === 'multi-delete-btn') {
            handleMultiDelete();
        } else if (e.target.id === 'multi-move-btn') {
            handleMultiMove();
        }
    });

    // タブ切り替え
    document.querySelectorAll('.settings-tab').forEach(tab => {
        tab.addEventListener('click', async (e) => {
            const targetTab = e.target.dataset.tab;
            
            document.querySelectorAll('.settings-tab').forEach(t => {
                t.classList.remove('border-b-2', 'border-blue-500', 'text-blue-600', 'dark:text-blue-400');
                t.classList.add('text-gray-600', 'dark:text-gray-400');
            });
            e.target.classList.add('border-b-2', 'border-blue-500', 'text-blue-600', 'dark:text-blue-400');
            e.target.classList.remove('text-gray-600', 'dark:text-gray-400');
            
            document.querySelectorAll('.settings-tab-content').forEach(content => {
                content.classList.add('hidden');
            });
            document.getElementById(`${targetTab}-tab`).classList.remove('hidden');
            
            // タブごとの初期化処理
            if (targetTab === 'tools') {
                loadToolsSettings();
            } else if (targetTab === 'models') {
                const { updateModelsTabUI } = await import('./ui_models.js');
                await updateModelsTabUI();
            }
        });
    });

    // ツール再読み込みボタン
    document.getElementById('reload-tools-btn')?.addEventListener('click', async () => {
        const btn = document.getElementById('reload-tools-btn');
        const status = document.getElementById('tools-status');
        
        btn.disabled = true;
        btn.innerHTML = '<svg class="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg><span>読み込み中...</span>';
        
        try {
            const response = await fetch('/api/tools/reload', { method: 'POST' });
            const data = await response.json();
            
            if (data.success) {
                status.textContent = `✓ ${data.loaded_count}個のツールを読み込みました`;
                status.className = 'mt-2 text-sm text-green-600 dark:text-green-400';
            } else {
                status.textContent = `✗ エラー: ${data.error}`;
                status.className = 'mt-2 text-sm text-red-600 dark:text-red-400';
            }
        } catch (error) {
            status.textContent = `✗ エラー: ${error.message}`;
            status.className = 'mt-2 text-sm text-red-600 dark:text-red-400';
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg><span>ツールを再読み込み</span>';
            
            setTimeout(() => {
                status.textContent = '';
            }, 3000);
        }
    });
}
