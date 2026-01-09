// static/js/ui_tools.js

export function showToolUIOnStart(toolName, toolDisplayName, uiInfo) {
    if (uiInfo && uiInfo.ui_available) {
        const execution = {
            tool_name: toolDisplayName,
            function_name: toolName,
            ui_info: uiInfo,
            icon: ''
        };
        showToolUIPanel(execution);
    }
}

export function showToolUIPanel(execution) {
    let panel = document.getElementById('tool-ui-right-panel');
    
    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'tool-ui-right-panel';
        panel.className = 'fixed right-14 top-0 h-full w-96 bg-white dark:bg-gray-800 border-l border-gray-200 dark:border-gray-700 shadow-xl z-30 transition-transform transform translate-x-full';
        panel.innerHTML = `
            <div class="flex justify-between items-center p-4 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
                <div class="flex items-center gap-2">
                    <span class="tool-icon"></span>
                    <span class="tool-name font-semibold"></span>
                </div>
                <button onclick="closeToolUIPanel()" class="p-1 hover:bg-gray-200 dark:hover:bg-gray-700 rounded transition-colors">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                </button>
            </div>
            <div class="relative h-full">
                <iframe class="w-full h-full" frameborder="0"></iframe>
                <div id="tool-ui-loading" class="absolute inset-0 bg-white dark:bg-gray-800 flex items-center justify-center">
                    <div class="text-center">
                        <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                        <p class="mt-2 text-sm text-gray-600 dark:text-gray-400">ツールUIを読み込み中...</p>
                    </div>
                </div>
            </div>
        `;
        document.body.appendChild(panel);
    }
    
    const iframe = panel.querySelector('iframe');
    const toolName = panel.querySelector('.tool-name');
    const toolIcon = panel.querySelector('.tool-icon');
    const loadingDiv = panel.querySelector('#tool-ui-loading');
    
    toolName.textContent = execution.tool_name;
    
    if (execution.icon) {
        toolIcon.innerHTML = execution.icon;
    }
    
    if (execution.ui_info && execution.ui_info.ui_port) {
        const htmlFile = execution.ui_info.html_file || 'index.html';
        iframe.src = `http://localhost:${execution.ui_info.ui_port}/${htmlFile}`;
        
        iframe.onload = () => {
            loadingDiv.classList.add('hidden');
        };
    } else {
        loadingDiv.innerHTML = `
            <div class="text-center text-red-600">
                <p>UIが利用できません</p>
            </div>
        `;
    }
    
    setTimeout(() => {
        panel.classList.remove('translate-x-full');
    }, 100);
    
    const chatWindow = document.getElementById('chat-window');
    const messagesContainer = document.getElementById('messages-container');
    const footer = chatWindow?.querySelector('footer');
    
    if (chatWindow) {
        const marginRight = '440px';
        if (messagesContainer) messagesContainer.style.marginRight = marginRight;
        if (footer) footer.style.marginRight = marginRight;
        const header = chatWindow.querySelector('header');
        if (header) header.style.marginRight = marginRight;
    }
}

// グローバル関数として定義
window.closeToolUIPanel = function() {
    const panel = document.getElementById('tool-ui-right-panel');
    if (panel) {
        panel.classList.add('translate-x-full');
        
        const chatWindow = document.getElementById('chat-window');
        const messagesContainer = document.getElementById('messages-container');
        const footer = chatWindow?.querySelector('footer');
        const header = chatWindow?.querySelector('header');
        
        if (messagesContainer) messagesContainer.style.marginRight = '56px';
        if (footer) footer.style.marginRight = '56px';
        if (header) header.style.marginRight = '56px';
        
        setTimeout(() => {
            panel.remove();
        }, 300);
    }
}
