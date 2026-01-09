// static/js/state.js

// アプリケーションの状態を管理するオブジェクト
export const state = {
    currentChatId: null,
    chatToInteractId: null, // コンテキストメニューで操作対象のチャットID
    isCreatingChat: false,
    isNewChatPending: false, // 新規チャットが保留中かどうか
    filesToUpload: [], // 複数ファイルに対応するため配列に変更
    userSettings: {
        theme: 'dark',
        model: 'gemini-2.5-flash',
        thinking_on: true,
        thinking_budget_pro: 32768,
        thinking_budget_flash: 24576,
        thinking_budget_lite: 24576,
        streaming_on: false,  // ストリーミング設定
        favorite_models: []  // お気に入りモデル
    },
    isAwaitingAIResponse: false,
    chatListData: { pinned: [], folders: {}, uncategorized: [] },
    availablePrompts: [],
    currentPromptId: 'normal_prompt',
    isMultiSelectMode: false, // 複数選択モードのフラグ
    selectedChats: [], // 選択されたチャットIDのリスト
    currentStreamController: null,  // 現在のストリーミング接続を管理
    isStreaming: false,  // ストリーミング中かどうか
    abortController: null,  // 中断用のAbortController
    wasAborted: false,  // 強制停止されたかどうか
    lastAbortedText: '',  // 強制停止時のテキスト
    chatTitle: '', // 現在のチャットタイトル
    availableModels: [],  // 利用可能なモデル
    favoriteModels: [],   // お気に入りモデル
    
    // サポーター関連
    allSupporters: [],      // 全サポーター一覧（キャッシュ用）
    activeSupporters: []    // 現在のチャットで有効なサポーター（順序付き）
};

/**
 * アップロードするファイルのリストにファイルを追加します。
 * @param {File[]} files - 追加するファイルの配列
 */
export function addFiles(files) {
    state.filesToUpload.push(...files);
}

/**
 * 指定されたインデックスのファイルをアップロードリストから削除します。
 * @param {number} fileIndex - 削除するファイルのインデックス
 */
export function removeFile(fileIndex) {
    state.filesToUpload.splice(fileIndex, 1);
}

/**
 * アップロードするファイルのリストをすべてクリアします。
 */
export function clearFiles() {
    state.filesToUpload = [];
}

/**
 * サポーター一覧を設定します。
 * @param {Array} supporters - サポーター情報の配列
 */
export function setSupporters(supporters) {
    state.allSupporters = supporters;
}

/**
 * 現在のチャットで有効なサポーターを設定します。
 * @param {Array<string>} activeSupporters - 有効なサポーターIDの配列（順序付き）
 */
export function setActiveSupporters(activeSupporters) {
    state.activeSupporters = activeSupporters;
}

/**
 * サポーター状態をクリアします。
 */
export function clearSupporters() {
    state.allSupporters = [];
    state.activeSupporters = [];
}
