/**
 * ContextMenu
 */

let activeMenu = null;

export function showContextMenu(options) {
  const { x, y, items, onClose } = options;
  hideContextMenu();
  
  const menu = document.createElement('div');
  menu.className = 'context-menu';
  menu.style.left = `${x}px`;
  menu.style.top = `${y}px`;
  
  menu.innerHTML = items.map((item, i) => {
    if (item.separator) return '<div class="context-menu-separator"></div>';
    const iconHtml = item.icon ? `<span class="context-menu-icon">${item.icon}</span>` : '';
    const dangerClass = item.danger ? 'danger' : '';
    return `<button class="context-menu-item ${dangerClass}" data-index="${i}">${iconHtml}<span class="context-menu-label">${item.label}</span></button>`;
  }).join('');
  
  document.body.appendChild(menu);
  activeMenu = menu;
  
  const rect = menu.getBoundingClientRect();
  if (rect.right > window.innerWidth) menu.style.left = `${window.innerWidth - rect.width - 10}px`;
  if (rect.bottom > window.innerHeight) menu.style.top = `${window.innerHeight - rect.height - 10}px`;
  
  menu.addEventListener('click', (e) => {
    const btn = e.target.closest('.context-menu-item');
    if (btn) {
      const index = parseInt(btn.dataset.index, 10);
      if (items[index]?.action) items[index].action();
      hideContextMenu();
    }
  });
  
  setTimeout(() => {
    const handleOutside = (e) => {
      if (!menu.contains(e.target)) { hideContextMenu(); if (onClose) onClose(); }
    };
    document.addEventListener('click', handleOutside);
    document.addEventListener('contextmenu', handleOutside);
  }, 0);
}

export function hideContextMenu() {
  if (activeMenu) { activeMenu.remove(); activeMenu = null; }
}
