/**
 * ユーティリティ関数
 */

export function getLinearThread(history) {
  if (!history) return [];
  const { mapping, current_node, messages } = history;
  if (!current_node || !mapping || !messages) return [];
  const path = [];
  let nodeId = current_node;
  while (nodeId) {
    path.push(nodeId);
    nodeId = mapping[nodeId]?.parent || null;
  }
  path.reverse();
  const msgById = new Map(messages.map(m => [m.message_id, m]));
  return path.map(id => msgById.get(id)).filter(Boolean);
}

export function formatRelativeTime(timestamp) {
  if (!timestamp) return '';
  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now - date;
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);
  if (diffSec < 60) return 'たった今';
  if (diffMin < 60) return `${diffMin}分前`;
  if (diffHour < 24) return `${diffHour}時間前`;
  if (diffDay < 7) return `${diffDay}日前`;
  return date.toLocaleDateString('ja-JP');
}

export function renderMarkdown(text) {
  if (!text) return '';
  if (typeof marked !== 'undefined') {
    marked.setOptions({ breaks: true, gfm: true });
    return marked.parse(text);
  }
  return escapeHtml(text).replace(/\n/g, '<br>');
}

export function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

export function debounce(fn, delay) {
  let timeoutId;
  return (...args) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), delay);
  };
}

export function generateId() { return 'id-' + Math.random().toString(36).substr(2, 9); }
