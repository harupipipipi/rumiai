/**
 * Modal
 */

let activeModal = null;

export function showModal(options) {
  const { title, content, onClose, buttons = [] } = options;
  hideModal();
  
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-header">
        <h3 class="modal-title">${title}</h3>
        <button class="modal-close" aria-label="閉じる">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
      <div class="modal-content">${content}</div>
      ${buttons.length > 0 ? `<div class="modal-footer">${buttons.map((btn, i) => `<button class="modal-btn ${btn.primary ? 'primary' : ''} ${btn.danger ? 'danger' : ''}" data-index="${i}">${btn.label}</button>`).join('')}</div>` : ''}
    </div>
  `;
  
  document.body.appendChild(overlay);
  activeModal = overlay;
  
  overlay.querySelector('.modal-close')?.addEventListener('click', () => { hideModal(); if (onClose) onClose(); });
  overlay.addEventListener('click', (e) => { if (e.target === overlay) { hideModal(); if (onClose) onClose(); } });
  overlay.querySelectorAll('.modal-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const buttonConfig = buttons[parseInt(btn.dataset.index, 10)];
      if (buttonConfig?.action) buttonConfig.action();
    });
  });
  
  const handleKeydown = (e) => { if (e.key === 'Escape') { hideModal(); if (onClose) onClose(); } };
  document.addEventListener('keydown', handleKeydown);
  overlay._keydownHandler = handleKeydown;
  
  return overlay;
}

export function hideModal() {
  if (activeModal) {
    if (activeModal._keydownHandler) document.removeEventListener('keydown', activeModal._keydownHandler);
    activeModal.remove();
    activeModal = null;
  }
}

export function showPromptModal(options) {
  const { title, placeholder = '', defaultValue = '', onConfirm, onCancel } = options;
  const inputId = 'modal-input-' + Date.now();
  
  const modal = showModal({
    title,
    content: `<input type="text" id="${inputId}" class="modal-input" placeholder="${placeholder}" value="${defaultValue}">`,
    buttons: [
      { label: 'キャンセル', action: () => { hideModal(); if (onCancel) onCancel(); } },
      { label: '確定', primary: true, action: () => { const v = document.getElementById(inputId)?.value?.trim() || ''; hideModal(); if (onConfirm) onConfirm(v); } }
    ]
  });
  
  setTimeout(() => { const input = document.getElementById(inputId); input?.focus(); input?.select(); }, 50);
  document.getElementById(inputId)?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); const v = e.target.value.trim(); hideModal(); if (onConfirm) onConfirm(v); }
  });
  return modal;
}

export function showConfirmModal(options) {
  const { title, message, confirmLabel = '確定', cancelLabel = 'キャンセル', danger = false, onConfirm, onCancel } = options;
  return showModal({
    title,
    content: `<p>${message}</p>`,
    buttons: [
      { label: cancelLabel, action: () => { hideModal(); if (onCancel) onCancel(); } },
      { label: confirmLabel, primary: !danger, danger, action: () => { hideModal(); if (onConfirm) onConfirm(); } }
    ]
  });
}

export function showSelectModal(options) {
  const { title, items, onSelect, onCancel } = options;
  const listHtml = items.map((item, i) => `<button class="modal-select-item" data-index="${i}" data-value="${item.value}">${item.icon ? `<span class="modal-select-icon">${item.icon}</span>` : ''}<span class="modal-select-label">${item.label}</span></button>`).join('');
  const modal = showModal({ title, content: `<div class="modal-select-list">${listHtml}</div>`, onClose: onCancel });
  modal.querySelectorAll('.modal-select-item').forEach(btn => {
    btn.addEventListener('click', () => { const v = btn.dataset.value; hideModal(); if (onSelect) onSelect(v); });
  });
  return modal;
}
