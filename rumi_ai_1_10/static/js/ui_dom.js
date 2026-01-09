// static/js/ui_dom.js

// DOM要素のキャッシュ
export const dom = {
    sidebar: document.getElementById('sidebar'),
    chatHistoryList: document.getElementById('chat-history-list'),
    chatHeaderTitle: document.getElementById('chat-header-title'),
    messagesContainer: document.getElementById('messages-container'),
    chatWindow: document.getElementById('chat-window'),
    filePreviewContainer: document.getElementById('file-preview-container'),
    sendBtn: document.getElementById('send-btn'),
    chatInput: document.getElementById('chat-input'),
    themeToggleBtn: document.getElementById('theme-toggle-btn'),
    themeText: document.querySelector('.theme-text'),
    aiAvatarIcons: () => document.querySelectorAll('.ai-avatar-icon'),
    promptSelectContainer: document.getElementById('prompt-select-container'),
    modelSelectBtn: document.getElementById('model-select-btn'),
    modelSelectMenu: document.getElementById('model-select-menu'),
    modelOptions: document.querySelectorAll('.model-option'),
    thinkingBtn: document.getElementById('thinking-btn'),
    // モーダル関連
    renameModalOverlay: document.getElementById('rename-modal-overlay'),
    renameInput: document.getElementById('rename-input'),
    moveFolderModalOverlay: document.getElementById('move-folder-modal-overlay'),
    moveFolderSelect: document.getElementById('move-folder-select'),
    newFolderInput: document.getElementById('new-folder-input'),
    deleteConfirmModalOverlay: document.getElementById('delete-confirm-modal-overlay'),
    settingsModalOverlay: document.getElementById('settings-modal-overlay'),
    // 設定モーダル内の要素
    budgetProSlider: document.getElementById('budget-pro'),
    budgetProValue: document.getElementById('budget-pro-value'),
    budgetFlashSlider: document.getElementById('budget-flash'),
    budgetFlashValue: document.getElementById('budget-flash-value'),
    budgetLiteSlider: document.getElementById('budget-lite'),
    budgetLiteValue: document.getElementById('budget-lite-value'),
};

// 基本的なUI操作
export function updateSendButtonState() {
    import('./state.js').then(({ state }) => {
        const hasInput = dom.chatInput.value.trim() !== '' || state.filesToUpload.length > 0;
        const isProcessing = state.isAwaitingAIResponse || state.isStreaming;
        
        if (isProcessing) {
            dom.sendBtn.disabled = false;
            dom.sendBtn.innerHTML = `
                <svg class="w-5 h-5 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
                </svg>
            `;
            dom.sendBtn.title = '停止';
            dom.sendBtn.classList.add('stop-button');
        } else {
            dom.sendBtn.disabled = !hasInput;
            dom.sendBtn.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M15.854.146a.5.5 0 0 1 .11.54l-5.819 14.547a.75.75 0 0 1-1.329.124l-3.178-4.995L.643 7.184a.75.75 0 0 1 .124-1.33L15.314.037a.5.5 0 0 1 .54.11ZM6.636 10.07l2.761 4.338L14.13 2.576 6.636 10.07Zm6.787-8.201L1.591 6.602l4.339 2.76 7.494-7.493Z"/>
                </svg>
            `;
            dom.sendBtn.title = '送信';
            dom.sendBtn.classList.remove('stop-button');
        }
    });
}

export function updateFilePreview() {
    import('./state.js').then(({ state }) => {
        dom.filePreviewContainer.innerHTML = '';
        if (state.filesToUpload.length === 0) {
            dom.filePreviewContainer.classList.add('hidden');
            return;
        }
        dom.filePreviewContainer.classList.remove('hidden');

        state.filesToUpload.forEach((file, index) => {
            const previewElement = document.createElement('div');
            previewElement.className = 'flex items-center justify-between p-2 bg-gray-100 dark:bg-gray-700 rounded-lg animate-fadeIn';
            
            const fileNameSpan = document.createElement('span');
            fileNameSpan.className = 'text-sm text-gray-600 dark:text-gray-300 truncate';
            fileNameSpan.textContent = file.name;
            
            const removeBtn = document.createElement('button');
            removeBtn.className = 'p-1 text-gray-500 hover:text-red-500 flex-shrink-0 ml-2';
            removeBtn.innerHTML = '×';
            removeBtn.dataset.fileIndex = index;
            removeBtn.onclick = () => {
                import('./message_handlers.js').then(({ handleFileRemove }) => {
                    handleFileRemove({ currentTarget: removeBtn });
                });
            };

            previewElement.appendChild(fileNameSpan);
            previewElement.appendChild(removeBtn);
            dom.filePreviewContainer.appendChild(previewElement);
        });
    });
}

export function initializeNewChatView() {
    import('./state.js').then(({ state }) => {
        import('./utils.js').then(({ getAIIconSrc }) => {
            state.currentChatId = null;
            dom.chatWindow.classList.remove('chat-active');
            dom.messagesContainer.innerHTML = `<div class="flex-grow flex flex-col items-center justify-center"><div class="w-20 h-20 mb-4"><img src="${getAIIconSrc()}" class="w-full h-full ai-avatar-icon"></div><div class="text-3xl font-bold">rumi ai</div></div>`;
            dom.chatHeaderTitle.textContent = '新しいチャット';
            import('./ui_chat_list.js').then(({ updateActiveChatSelection }) => {
                updateActiveChatSelection();
            });
        });
    });
}

// テーマ適用（darkMode: 'class' を前提）
export function applyTheme(theme) {
    const isDark = theme === 'dark';
    document.documentElement.classList.toggle('dark', isDark);

    // テーマボタンの文言更新（存在する場合のみ）
    if (dom.themeText) {
        dom.themeText.textContent = isDark ? 'ダークモード' : 'ライトモード';
    }

    // 既存のAIアイコン（チャット内のアバター）もテーマに合わせて差し替え
    // ※ getAIIconSrc() は utils.js に定義済み
    import('./utils.js').then(({ getAIIconSrc }) => {
        const src = getAIIconSrc();
        dom.aiAvatarIcons()?.forEach(img => {
            if (img && img.tagName === 'IMG') img.src = src;
        });
    });
}

/**
 * UI全体を state.userSettings に合わせて更新
 */
export function updateAllUI() {
    import('./state.js').then(({ state }) => {
        // テーマ
        if (state.userSettings?.theme) {
            applyTheme(state.userSettings.theme);
        }

        // 送信ボタン / 添付プレビュー
        updateSendButtonState();
        updateFilePreview();

        // 思考ボタンの見た目
        if (dom.thinkingBtn) {
            dom.thinkingBtn.classList.toggle('active', !!state.userSettings.thinking_on);
            dom.thinkingBtn.title = state.userSettings.thinking_on ? '思考: ON' : '思考: OFF';
        }

        // 予算スライダー値と表示
        if (dom.budgetProSlider) dom.budgetProSlider.value = state.userSettings.thinking_budget_pro ?? dom.budgetProSlider.value;
        if (dom.budgetFlashSlider) dom.budgetFlashSlider.value = state.userSettings.thinking_budget_flash ?? dom.budgetFlashSlider.value;
        if (dom.budgetLiteSlider) dom.budgetLiteSlider.value = state.userSettings.thinking_budget_lite ?? dom.budgetLiteSlider.value;

        if (dom.budgetProValue) dom.budgetProValue.textContent = String(dom.budgetProSlider?.value ?? '');
        if (dom.budgetFlashValue) dom.budgetFlashValue.textContent = String(dom.budgetFlashSlider?.value ?? '');
        if (dom.budgetLiteValue) dom.budgetLiteValue.textContent = String(dom.budgetLiteSlider?.value ?? '');

        // ストリーミングトグル（設定モーダル内）
        const streamingToggle = document.getElementById('streaming-toggle');
        if (streamingToggle) {
            streamingToggle.checked = !!state.userSettings.streaming_on;
        }

        // モデル選択（存在する option があれば active 付与）
        // ※ あなたの実装では model menu は動的生成のため、ここは “できる範囲で”
        if (dom.modelOptions && dom.modelOptions.length > 0) {
            dom.modelOptions.forEach(opt => {
                opt.classList.toggle('active', opt.dataset.model === state.userSettings.model);
            });
        }

        // プロンプト選択UI（存在する場合のみ更新）
        updatePromptSelectionUI();
    });
}

/**
 * プロンプト選択UIを更新（最低限：無ければ何もしない）
 * ※ 既に別ファイルで実装するなら、そちらに寄せてOK
 */
export function updatePromptSelectionUI() {
    // このプロジェクトでは prompt UI が動的生成っぽいので、
    // ここでは「無ければ何もしない」安全実装にしておく。
    // 必要なら promptSelectContainer 内のDOMを再描画する実装を後で入れる。
    const container = dom.promptSelectContainer;
    if (!container) return;

    // 例：すでにUIがあるなら active 表示などを更新…（現状はノーオペ）
}
