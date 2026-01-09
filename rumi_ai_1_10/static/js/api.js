// static/js/api.js

import { state } from './state.js';
import { readFileAsDataURL } from './utils.js';

/**
 * ユーザー設定をサーバーから読み込みます。
 * @returns {Promise<object>} ユーザー設定オブジェクト
 */
export async function loadUserSettingsFromServer() {
    const response = await fetch('/api/user/settings');
    if (!response.ok) throw new Error('Failed to load user settings');
    return await response.json();
}

/**
 * ユーザー設定をサーバーに保存します。
 * @param {object} settings 保存する設定オブジェクト
 */
export async function saveUserSettingsToServer(settings) {
    await fetch('/api/user/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
    });
}

/**
 * チャットリストをサーバーから読み込みます。
 * @returns {Promise<object>} チャットリストデータ
 */
export async function loadChatListFromServer() {
    const response = await fetch('/api/chats');
    if (!response.ok) throw new Error('Failed to load chat list');
    return await response.json();
}

/**
 * 新しいチャットをサーバー上で作成します。
 * @param {string|null} folderName 新しいチャットを作成するフォルダ名
 * @returns {Promise<object>} 新しいチャットのメタデータ
 */
export async function createNewChatOnServer(folderName = null) {
    const response = await fetch('/api/chats', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder: folderName }),
    });
    if (!response.ok) throw new Error('Failed to create new chat');
    return await response.json();
}

/**
 * 指定されたチャットの履歴をサーバーから読み込みます。
 * @param {string} chatId 履歴を読み込むチャットのID
 * @returns {Promise<object>} チャット履歴データ
 */
export async function loadChatHistoryFromServer(chatId) {
    const response = await fetch(`/api/chats/${chatId}`);
    if (!response.ok) throw new Error('Chat not found');
    return await response.json();
}

/**
 * チャットのメタデータ（タイトル、ピン、フォルダ）を更新します。
 * @param {string} chatId 更新するチャットのID
 * @param {object} metadata 更新するメタデータ
 */
export async function updateChatMetaOnServer(chatId, metadata) {
    await fetch(`/api/chats/${chatId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(metadata),
    });
}

/**
 * 指定されたチャットをサーバー上でコピーします。
 * @param {string} chatId コピーするチャットのID
 */
export async function copyChatOnServer(chatId) {
    await fetch(`/api/chats/${chatId}/copy`, { method: 'POST' });
}

/**
 * 指定されたチャットをサーバー上で削除します。
 * @param {string} chatId 削除するチャットのID
 */
export async function deleteChatOnServer(chatId) {
    await fetch(`/api/chats/${chatId}`, { method: 'DELETE' });
}

/**
 * 利用可能なプロンプトの一覧をサーバーから取得します。
 * @returns {Promise<Array<object>>} プロンプトのリスト
 */
export async function loadPromptsFromServer() {
    const response = await fetch('/api/prompts');
    if (!response.ok) throw new Error('Failed to load prompts');
    return await response.json();
}

/**
 * ユーザーメッセージをサーバーに送信し、AIの応答を取得します。
 * @param {string} chatId 現在のチャットID
 * @param {object} userMessage ユーザーメッセージオブジェクト
 * @returns {Promise<object>} AIの応答データ
 */
export async function sendMessageToServer(chatId, userMessage) {
    let budget = 0;
    if (state.userSettings.thinking_on) {
        switch (state.userSettings.model) {
            case 'gemini-2.5-pro': budget = state.userSettings.thinking_budget_pro; break;
            case 'gemini-2.5-flash': budget = state.userSettings.thinking_budget_flash; break;
            case 'gemini-2.5-flash-lite-preview-06-17': budget = state.userSettings.thinking_budget_lite; break;
        }
    }

    const payload = {
        message: userMessage,
        model: state.userSettings.model,
        thinking_budget: budget,
        prompt: state.currentPromptId,
    };

    const response = await fetch(`/api/chats/${chatId}/send_message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });

    if (!response.ok) {
        const errorData = await response.json();
        // 503エラーの場合、特別なエラーメッセージを投げる
        if (response.status === 503) {
            const error = new Error(errorData.error || `API error: ${response.status}`);
            error.message = '503: ' + error.message;
            throw error;
        }
        throw new Error(errorData.error || `API error: ${response.status}`);
    }
    return await response.json();
}

/**
 * ストリーミングでメッセージを送信
 * @param {string} chatId チャットID
 * @param {object} userMessage ユーザーメッセージ
 * @param {AbortSignal} abortSignal 中断シグナル
 * @param {function} onChunk チャンク受信時のコールバック
 * @param {function} onComplete 完了時のコールバック
 * @param {function} onError エラー時のコールバック
 */
export async function sendMessageToServerStream(chatId, userMessage, abortSignal, onChunk, onComplete, onError) {
    let budget = 0;
    if (state.userSettings.thinking_on) {
        switch (state.userSettings.model) {
            case 'gemini-2.5-pro': budget = state.userSettings.thinking_budget_pro; break;
            case 'gemini-2.5-flash': budget = state.userSettings.thinking_budget_flash; break;
            case 'gemini-2.5-flash-lite-preview-06-17': budget = state.userSettings.thinking_budget_lite; break;
        }
    }

    const payload = {
        message: userMessage,
        model: state.userSettings.model,
        thinking_budget: budget,
        prompt: state.currentPromptId,
        streaming: true
    };

    try {
        const response = await fetch(`/api/chats/${chatId}/send_message_stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: abortSignal
        });

        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }

        // SSEストリームを読み取る
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            // abort チェック
            if (abortSignal && abortSignal.aborted) {
                reader.cancel();
                break;
            }
            
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        
                        switch (data.type) {
                            case 'chunk':
                                onChunk(data);
                                break;
                            case 'metadata':
                                if (data.title) {
                                    state.chatTitle = data.title;
                                }
                                break;
                            case 'ai_explanation':
                                // AIの説明を送信
                                onChunk(data);
                                break;
                            case 'function_call_start':
                                onChunk(data);
                                break;
                            case 'tool_execution_start':
                                onChunk(data);
                                break;
                            case 'tool_progress':
                                // ツール進捗メッセージ
                                onChunk(data);
                                break;
                            case 'tool_execution_complete':
                                onChunk(data);
                                break;
                            case 'processing_tool_results':
                                onChunk(data);
                                break;
                            case 'aborted':
                                console.log('Stream aborted by user');
                                break;
                            case 'aborted_complete':
                                onComplete(data.full_text, data.metadata, true);
                                break;
                            case 'complete':
                                onComplete(data.full_text, data.metadata, false);
                                break;
                            case 'error':
                                onError(new Error(data.error));
                                break;
                        }
                    } catch (e) {
                        console.error('Failed to parse SSE data:', e);
                    }
                }
            }
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('Request was aborted');
            // 中断は正常な操作なのでエラーとして扱わない
            return;
        }
        onError(error);
    }
}

/**
 * 続行メッセージをストリーミングで送信
 * @param {string} chatId チャットID
 * @param {object} continueMessage 続行メッセージ
 * @param {AbortSignal} abortSignal 中断シグナル
 * @param {function} onChunk チャンク受信時のコールバック
 * @param {function} onComplete 完了時のコールバック
 * @param {function} onError エラー時のコールバック
 */
export async function sendContinueMessageStream(chatId, continueMessage, abortSignal, onChunk, onComplete, onError) {
    const payload = {
        message: continueMessage,
        model: state.userSettings.model,
        thinking_budget: state.userSettings.thinking_on ? 
            (state.userSettings.model === 'gemini-2.5-pro' ? state.userSettings.thinking_budget_pro :
             state.userSettings.model === 'gemini-2.5-flash' ? state.userSettings.thinking_budget_flash :
             state.userSettings.thinking_budget_lite) : 0,
        prompt: state.currentPromptId,
        streaming: true,
        is_continuation: true
    };

    try {
        const response = await fetch(`/api/chats/${chatId}/continue`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: abortSignal
        });

        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }

        // ストリーミングレスポンスの場合
        if (response.headers.get('content-type')?.includes('text/event-stream')) {
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                if (abortSignal && abortSignal.aborted) {
                    reader.cancel();
                    break;
                }
                
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            
                            switch (data.type) {
                                case 'chunk':
                                    onChunk(data);
                                    break;
                                case 'aborted':
                                case 'aborted_complete':
                                    onComplete(data.full_text, data.metadata, true);
                                    break;
                                case 'complete':
                                    onComplete(data.full_text, data.metadata, false);
                                    break;
                                case 'error':
                                    onError(new Error(data.error));
                                    break;
                            }
                        } catch (e) {
                            console.error('Failed to parse SSE data:', e);
                        }
                    }
                }
            }
        } else {
            // 通常のJSONレスポンスの場合
            const data = await response.json();
            onComplete(data.response, data.metadata, false);
        }
    } catch (error) {
        if (error.name === 'AbortError') {
            console.log('Continue request was aborted');
            return;
        }
        onError(error);
    }
}

/**
 * メッセージオブジェクトを作成します（ファイル処理を含む）。
 * 複数ファイルのアップロードに対応。
 * @param {string} messageText ユーザーのテキスト入力
 * @param {Array<File>} files アップロードするファイルのリスト
 * @returns {Promise<object>} API送信用のメッセージオブジェクト
 */
export async function createMessageObject(messageText, files) {
    let uploadedFilesInfo = [];
    if (files && files.length > 0) {
        console.log(`アップロードするファイル数: ${files.length}`);
        
        const filePromises = files.map(async (file, index) => {
            try {
                const dataUrl = await readFileAsDataURL(file);
                console.log(`ファイル ${index + 1}/${files.length}: ${file.name} (${file.type})`);
                
                return {
                    name: file.name,
                    path: dataUrl,
                    type: file.type || 'application/octet-stream',
                    size: file.size
                };
            } catch (error) {
                console.error(`ファイル読み込みエラー (${file.name}):`, error);
                return null;
            }
        });
        
        const results = await Promise.all(filePromises);
        uploadedFilesInfo = results.filter(info => info !== null);
        
        console.log(`正常に処理されたファイル数: ${uploadedFilesInfo.length}`);
    }
    
    return { 
        type: 'user', 
        text: messageText, 
        files: uploadedFilesInfo 
    };
}

/**
 * 新しいフォルダをサーバー上で作成します。
 * @param {string} folderName 作成するフォルダ名
 * @returns {Promise<object>} 作成結果
 */
export async function createFolderOnServer(folderName) {
    const response = await fetch('/api/folders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: folderName }),
    });
    if (!response.ok) throw new Error('Failed to create folder');
    return await response.json();
}

/**
 * 利用可能なAIモデルの一覧を取得
 * @returns {Promise<Array>} モデルのリスト
 */
export async function loadAvailableModels() {
    const response = await fetch('/api/ai/models');
    if (!response.ok) throw new Error('Failed to load models');
    const data = await response.json();
    return data.models;
}

/**
 * お気に入りモデルの一覧を取得
 * @returns {Promise<Array>} お気に入りモデルのリスト
 */
export async function loadFavoriteModels() {
    const response = await fetch('/api/ai/favorites');
    if (!response.ok) throw new Error('Failed to load favorite models');
    const data = await response.json();
    return data.favorites;
}

/**
 * お気に入りにモデルを追加
 * @param {string} modelId モデルID
 */
export async function addFavoriteModel(modelId) {
    const response = await fetch('/api/ai/favorites', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: modelId })
    });
    if (!response.ok) throw new Error('Failed to add favorite');
    return await response.json();
}

/**
 * お気に入りからモデルを削除
 * @param {string} modelId モデルID
 */
export async function removeFavoriteModel(modelId) {
    const response = await fetch(`/api/ai/favorites/${modelId}`, {
        method: 'DELETE'
    });
    if (!response.ok) throw new Error('Failed to remove favorite');
    return await response.json();
}

/**
 * 現在使用するモデルを設定
 * @param {string} modelId モデルID
 */
export async function setCurrentModel(modelId) {
    const response = await fetch('/api/ai/set-model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: modelId })
    });
    if (!response.ok) throw new Error('Failed to set model');
    return await response.json();
}

/**
 * モデルを検索
 * @param {object} criteria 検索条件
 */
export async function searchModels(criteria) {
    const response = await fetch('/api/ai/models/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(criteria)
    });
    if (!response.ok) throw new Error('Failed to search models');
    const data = await response.json();
    return data.models;
}

/**
 * チャットのサポーター設定を取得
 * @param {string} chatId チャットID
 * @returns {Promise<object>} サポーター設定
 */
export async function loadChatSupporters(chatId) {
    const response = await fetch(`/api/chats/${chatId}/supporters`);
    if (!response.ok) throw new Error('Failed to load chat supporters');
    return await response.json();
}

/**
 * チャットのサポーター設定を保存
 * @param {string} chatId チャットID
 * @param {Array<string>} supportersList 有効なサポーターのリスト（順序付き）
 */
export async function saveChatSupporters(chatId, supportersList) {
    const response = await fetch(`/api/chats/${chatId}/supporters`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ supporters: supportersList })
    });
    if (!response.ok) throw new Error('Failed to save chat supporters');
    return await response.json();
}

/**
 * 全サポーター一覧を取得
 * @returns {Promise<object>} サポーター一覧
 */
export async function loadAllSupporters() {
    const response = await fetch('/api/supporters');
    if (!response.ok) throw new Error('Failed to load supporters');
    return await response.json();
}

/**
 * サポーターを再読み込み
 * @returns {Promise<object>} 再読み込み結果
 */
export async function reloadSupporters() {
    const response = await fetch('/api/supporters/reload', { method: 'POST' });
    if (!response.ok) throw new Error('Failed to reload supporters');
    return await response.json();
}
