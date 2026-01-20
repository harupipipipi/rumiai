/**
 * API Client
 */

const BASE_URL = '';

async function request(method, endpoint, data = null) {
  const options = {
    method,
    headers: { 'Content-Type': 'application/json' },
  };
  if (data && (method === 'POST' || method === 'PATCH' || method === 'PUT')) {
    options.body = JSON.stringify(data);
  }
  const response = await fetch(`${BASE_URL}${endpoint}`, options);
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
    const error = new Error(errorData.error || `HTTP ${response.status}`);
    error.status = response.status;
    error.data = errorData;
    throw error;
  }
  return response.json();
}

export async function fetchChats() { return request('GET', '/api/chats'); }
export async function createChat(folder = null) { return request('POST', '/api/chats', folder ? { folder } : {}); }
export async function getChat(chatId) { return request('GET', `/api/chats/${chatId}`); }
export async function updateChat(chatId, data) { return request('PATCH', `/api/chats/${chatId}`, data); }
export async function deleteChat(chatId) { return request('DELETE', `/api/chats/${chatId}`); }
export async function copyChat(chatId) { return request('POST', `/api/chats/${chatId}/copy`); }
export async function createFolder(name) { return request('POST', '/api/folders', { name }); }

export async function sendMessage(chatId, text) {
  return request('POST', '/api/message', { chat_id: chatId, message: { text } });
}

export function sendMessageStream(chatId, text, callbacks = {}) {
  const { onChunk, onComplete, onError, onStart } = callbacks;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => {
    controller.abort();
    if (onError) onError(new Error('接続がタイムアウトしました'));
  }, 60000);
  
  if (onStart) onStart();
  
  fetch('/api/message/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chat_id: chatId, message: { text } }),
    signal: controller.signal,
  })
    .then(async (response) => {
      clearTimeout(timeoutId);
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.error || `サーバーエラー (${response.status})`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const jsonStr = line.slice(6).trim();
              if (!jsonStr) continue;
              const data = JSON.parse(jsonStr);
              if (data.type === 'chunk' && onChunk) onChunk(data.text || '');
              else if (data.type === 'complete' && onComplete) onComplete(data.full_text || '');
              else if (data.type === 'error' && onError) onError(new Error(data.message || 'ストリームエラー'));
            } catch (e) { console.warn('SSE parse error:', e); }
          }
        }
      }
    })
    .catch((err) => {
      clearTimeout(timeoutId);
      if (err.name !== 'AbortError' && onError) onError(err);
    });
  
  return { abort: () => { clearTimeout(timeoutId); controller.abort(); } };
}

export async function abortStream() { return request('POST', '/api/stream/abort'); }
export async function getSettings() { return request('GET', '/api/user/settings'); }
export async function saveSettings(settings) { return request('POST', '/api/user/settings', settings); }
export async function getUIHistory(chatId) { return request('GET', `/api/chats/${chatId}/ui_history`); }
export async function getDiagnostics() { return request('GET', '/api/diagnostics'); }
