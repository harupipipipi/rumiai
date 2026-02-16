/**
 * Store - アプリケーション状態管理
 */

const state = {
  chats: { pinned: [], folders: {}, uncategorized: [] },
  currentChatId: null,
  currentChat: null,
  isLoading: false,
  isChatsLoading: false,
  isStreaming: false,
  streamingText: '',
  streamError: null,
  isSidebarOpen: false,
  isMobile: false,
  settings: {},
  error: null
};

const listeners = new Set();

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notify() { listeners.forEach(l => l(state)); }

export function setState(updates) { Object.assign(state, updates); notify(); }
export function getState() { return state; }
export function setChats(chats) { setState({ chats, isChatsLoading: false }); }
export function setChatsLoading(isLoading) { setState({ isChatsLoading: isLoading }); }
export function setCurrentChat(chatId, chatData) { setState({ currentChatId: chatId, currentChat: chatData }); }
export function setLoading(isLoading) { setState({ isLoading }); }
export function setStreaming(isStreaming, text = '') { setState({ isStreaming, streamingText: text }); }
export function appendStreamingText(text) { setState({ streamingText: state.streamingText + text }); }
export function setStreamError(error) { setState({ streamError: error, isStreaming: false }); }
export function clearStreamError() { setState({ streamError: null }); }
export function setSidebarOpen(isOpen) { setState({ isSidebarOpen: isOpen }); }
export function toggleSidebar() { setState({ isSidebarOpen: !state.isSidebarOpen }); }
export function setIsMobile(isMobile) { setState({ isMobile }); }
export function setError(error) { setState({ error }); }
export function clearError() { setState({ error: null }); }
