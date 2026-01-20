/**
 * App - エントリポイント（Phase 5 統合 - レスポンシブ対応）
 */

import { initSidebar, loadChats } from './components/Sidebar.js';
import { initChatView, loadChat, clearChat, setLoadChatsFunc } from './components/ChatView.js';
import { registerRoute, handleRoute } from './router.js';
import { initSettings } from './components/SettingsModal.js';
import { initUIHistoryPanel } from './components/UIHistoryPanel.js';
import { initToast } from './components/Toast.js';
import { setIsMobile, setSidebarOpen, toggleSidebar, getState, subscribe } from './store.js';

const MOBILE_BREAKPOINT = 768;

document.addEventListener('DOMContentLoaded', () => {
  initToast();
  
  const sidebarEl = document.getElementById('sidebar');
  initSidebar(sidebarEl);
  
  const chatContainer = document.getElementById('chat-container');
  initChatView(chatContainer);
  
  setLoadChatsFunc(loadChats);
  
  const uiHistoryPanel = document.getElementById('ui-history-panel');
  initUIHistoryPanel(uiHistoryPanel);
  
  initSettings();
  initResponsive();
  
  registerRoute('home', () => clearChat());
  registerRoute('chat', (chatId) => loadChat(chatId));
  registerRoute('notFound', () => clearChat());
  
  handleRoute();
  
  document.getElementById('menu-toggle')?.addEventListener('click', toggleSidebar);
  
  const backdrop = document.getElementById('sidebar-backdrop');
  backdrop?.addEventListener('click', () => setSidebarOpen(false));
  
  subscribe((state) => {
    backdrop?.classList.toggle('visible', state.isSidebarOpen && state.isMobile);
  });
  
  document.addEventListener('keydown', handleGlobalKeydown);
});

function initResponsive() {
  const checkMobile = () => {
    const isMobile = window.innerWidth < MOBILE_BREAKPOINT;
    setIsMobile(isMobile);
    if (!isMobile) setSidebarOpen(false);
  };
  checkMobile();
  window.addEventListener('resize', debounce(checkMobile, 150));
}

function handleGlobalKeydown(e) {
  if (e.key === 'Escape') {
    const { isSidebarOpen, isMobile } = getState();
    if (isSidebarOpen && isMobile) setSidebarOpen(false);
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
    e.preventDefault();
    document.querySelector('.btn-new-chat')?.click();
  }
  if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
    e.preventDefault();
    const { isMobile } = getState();
    if (isMobile) toggleSidebar();
  }
}

function debounce(fn, delay) {
  let timeoutId;
  return (...args) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), delay);
  };
}
