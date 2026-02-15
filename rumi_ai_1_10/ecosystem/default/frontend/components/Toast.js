/**
 * Toast
 */

let toastContainer = null;
const toasts = new Map();
let toastId = 0;

export function initToast() {
  if (toastContainer) return;
  toastContainer = document.createElement('div');
  toastContainer.className = 'toast-container';
  toastContainer.setAttribute('role', 'alert');
  toastContainer.setAttribute('aria-live', 'polite');
  document.body.appendChild(toastContainer);
}

export function showToast(options) {
  const { message, type = 'info', duration = 4000, action = null } = options;
  initToast();
  const id = ++toastId;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.dataset.toastId = id;
  const icons = { info: 'ℹ️', success: '✅', error: '❌', warning: '⚠️' };
  
  const escapeHtml = (t) => { const d = document.createElement('div'); d.textContent = t; return d.innerHTML; };
  
  toast.innerHTML = `
    <span class="toast-icon">${icons[type] || icons.info}</span>
    <span class="toast-message">${escapeHtml(message)}</span>
    ${action ? `<button class="toast-action">${escapeHtml(action.label)}</button>` : ''}
    <button class="toast-close" aria-label="閉じる">×</button>
  `;
  
  toastContainer.appendChild(toast);
  toasts.set(id, toast);
  requestAnimationFrame(() => toast.classList.add('show'));
  
  toast.querySelector('.toast-close')?.addEventListener('click', () => hideToast(id));
  if (action) toast.querySelector('.toast-action')?.addEventListener('click', () => { action.onClick?.(); hideToast(id); });
  if (duration > 0) setTimeout(() => hideToast(id), duration);
  return id;
}

export function hideToast(id) {
  const toast = toasts.get(id);
  if (!toast) return;
  toast.classList.remove('show');
  toast.classList.add('hide');
  setTimeout(() => { toast.remove(); toasts.delete(id); }, 300);
}

export function showError(message, options = {}) { return showToast({ message, type: 'error', ...options }); }
export function showSuccess(message, options = {}) { return showToast({ message, type: 'success', ...options }); }
export function showWarning(message, options = {}) { return showToast({ message, type: 'warning', ...options }); }
export function showInfo(message, options = {}) { return showToast({ message, type: 'info', ...options }); }
