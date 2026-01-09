// static/js/ui_models.js
// AIモデル管理UI

import { state } from './state.js';
import { escapeHtml } from './utils.js';
import { saveUserSettingsToServer } from './api.js';

/**
 * モデル管理タブのUIを更新
 */
export async function updateModelsTabUI() {
    const container = document.getElementById('models-tab');
    if (!container) return;
    
    container.innerHTML = '<div class="flex items-center justify-center p-8"><div class="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div></div>';
    
    try {
        // すべてのモデルとお気に入りを取得
        const [modelsResponse, favoritesResponse] = await Promise.all([
            fetch('/api/ai/models'),
            fetch('/api/ai/favorites')
        ]);
        
        const modelsData = await modelsResponse.json();
        const favoritesData = await favoritesResponse.json();
        
        if (!modelsData.success || !favoritesData.success) {
            throw new Error('Failed to load models data');
        }
        
        const allModels = modelsData.models;
        const favoriteIds = favoritesData.favorites.map(f => f.id);
        
        // UIを構築
        container.innerHTML = `
            <div class="space-y-6">
                <!-- 検索バー -->
                <div class="sticky top-0 bg-white dark:bg-gray-900 z-10 pb-4">
                    <div class="flex gap-2">
                        <div class="flex-1 relative">
                            <input type="text" id="model-search-input" 
                                   placeholder="モデルを検索..." 
                                   class="w-full p-3 pl-10 rounded-lg bg-gray-100 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 focus:border-blue-500 focus:ring-0">
                            <svg class="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path>
                            </svg>
                        </div>
                        <button id="filter-toggle-btn" class="px-4 py-2 bg-gray-200 dark:bg-gray-700 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"></path>
                            </svg>
                        </button>
                    </div>
                    
                    <!-- フィルター -->
                    <div id="filter-panel" class="hidden mt-3 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg space-y-3">
                        <div class="flex flex-wrap gap-2">
                            <label class="inline-flex items-center">
                                <input type="checkbox" class="model-filter" data-filter="function_calling" checked>
                                <span class="ml-2 text-sm">Function Calling</span>
                            </label>
                            <label class="inline-flex items-center">
                                <input type="checkbox" class="model-filter" data-filter="multimodal" checked>
                                <span class="ml-2 text-sm">マルチモーダル</span>
                            </label>
                            <label class="inline-flex items-center">
                                <input type="checkbox" class="model-filter" data-filter="streaming" checked>
                                <span class="ml-2 text-sm">ストリーミング</span>
                            </label>
                            <label class="inline-flex items-center">
                                <input type="checkbox" class="model-filter" data-filter="reasoning" checked>
                                <span class="ml-2 text-sm">推論機能</span>
                            </label>
                        </div>
                        <div>
                            <label class="block text-sm font-medium mb-1">プロバイダー</label>
                            <select id="provider-filter" class="w-full p-2 rounded bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600">
                                <option value="">すべて</option>
                                ${[...new Set(allModels.map(m => m.provider))].map(p => 
                                    `<option value="${p}">${p}</option>`
                                ).join('')}
                            </select>
                        </div>
                    </div>
                </div>
                
                <!-- お気に入りセクション -->
                <div id="favorites-section">
                    <h3 class="text-lg font-semibold mb-3 flex items-center gap-2">
                        <svg class="w-5 h-5 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
                            <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"></path>
                        </svg>
                        お気に入り
                    </h3>
                    <div id="favorites-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        ${favoritesData.favorites.length > 0 ? 
                            favoritesData.favorites.map(model => createModelCard(model, true, state.userSettings.model === model.id)).join('') :
                            '<p class="text-sm text-gray-500 dark:text-gray-400 col-span-full text-center py-8">お気に入りのモデルがありません</p>'
                        }
                    </div>
                </div>
                
                <!-- すべてのモデルセクション -->
                <div id="all-models-section">
                    <h3 class="text-lg font-semibold mb-3">すべてのモデル (${allModels.length})</h3>
                    <div id="models-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        ${allModels.map(model => createModelCard(model, favoriteIds.includes(model.id), state.userSettings.model === model.id)).join('')}
                    </div>
                </div>
            </div>
        `;
        
        // イベントリスナーを設定
        setupModelEventListeners();
        
    } catch (error) {
        console.error('Failed to load models:', error);
        container.innerHTML = `
            <div class="text-center p-8 text-red-600">
                <p>モデル情報の読み込みに失敗しました</p>
                <button onclick="location.reload()" class="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg">
                    再読み込み
                </button>
            </div>
        `;
    }
}

/**
 * モデルカードのHTMLを生成
 */
function createModelCard(model, isFavorite, isActive) {
    const features = model.features || {};
    const providerLabel = model.provider ? `(${model.provider})` : '';
    
    return `
        <div class="model-card p-4 rounded-lg border ${isActive ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20' : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800'} hover:shadow-lg transition-all"
             data-model-id="${model.id}"
             data-provider="${model.provider}"
             data-function-calling="${features.supports_function_calling || false}"
             data-multimodal="${features.is_multimodal || false}"
             data-streaming="${features.supports_streaming || false}"
             data-reasoning="${features.supports_reasoning || false}">
            
            <div class="flex justify-between items-start mb-2">
                <div class="flex-1">
                    <h4 class="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                        ${escapeHtml(model.name)} ${providerLabel}
                    </h4>
                    <p class="text-xs text-gray-500 dark:text-gray-400">${escapeHtml(model.id)}</p>
                </div>
                <button class="favorite-btn flex-shrink-0 p-1 hover:scale-110 transition-transform" 
                        data-model-id="${model.id}"
                        title="${isFavorite ? 'お気に入りから削除' : 'お気に入りに追加'}">
                    <svg class="w-6 h-6 ${isFavorite ? 'text-yellow-500 fill-current' : 'text-gray-400'}" 
                         fill="${isFavorite ? 'currentColor' : 'none'}" 
                         stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"></path>
                    </svg>
                </button>
            </div>
            
            <p class="text-sm text-gray-600 dark:text-gray-300 mb-3 line-clamp-2">
                ${escapeHtml(model.description || '')}
            </p>
            
            <!-- 機能バッジ -->
            <div class="flex flex-wrap gap-1 mb-3">
                ${features.supports_function_calling ? '<span class="badge badge-blue">Function Calling</span>' : ''}
                ${features.is_multimodal ? '<span class="badge badge-green">マルチモーダル</span>' : ''}
                ${features.supports_streaming ? '<span class="badge badge-purple">ストリーミング</span>' : ''}
                ${features.supports_reasoning ? '<span class="badge badge-orange">推論</span>' : ''}
            </div>
            
            <button class="use-model-btn w-full py-2 px-4 rounded-lg ${isActive ? 'bg-blue-600 text-white' : 'bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600'} transition-colors"
                    data-model-id="${model.id}"
                    ${isActive ? 'disabled' : ''}>
                ${isActive ? '使用中' : 'このモデルを使用'}
            </button>
        </div>
    `;
}

/**
 * イベントリスナーを設定
 */
function setupModelEventListeners() {
    // 検索
    const searchInput = document.getElementById('model-search-input');
    if (searchInput) {
        searchInput.addEventListener('input', filterModels);
    }
    
    // フィルタートグル
    const filterToggleBtn = document.getElementById('filter-toggle-btn');
    const filterPanel = document.getElementById('filter-panel');
    if (filterToggleBtn && filterPanel) {
        filterToggleBtn.addEventListener('click', () => {
            filterPanel.classList.toggle('hidden');
        });
    }
    
    // フィルターチェックボックス
    document.querySelectorAll('.model-filter').forEach(checkbox => {
        checkbox.addEventListener('change', filterModels);
    });
    
    // プロバイダーフィルター
    const providerFilter = document.getElementById('provider-filter');
    if (providerFilter) {
        providerFilter.addEventListener('change', filterModels);
    }
    
    // お気に入りボタン
    document.querySelectorAll('.favorite-btn').forEach(btn => {
        btn.addEventListener('click', handleFavoriteToggle);
    });
    
    // モデル使用ボタン
    document.querySelectorAll('.use-model-btn').forEach(btn => {
        btn.addEventListener('click', handleUseModel);
    });
}

/**
 * モデルをフィルタリング
 */
function filterModels() {
    const searchQuery = document.getElementById('model-search-input')?.value.toLowerCase() || '';
    const providerFilter = document.getElementById('provider-filter')?.value || '';
    
    // アクティブなフィルター
    const activeFilters = {};
    document.querySelectorAll('.model-filter:checked').forEach(checkbox => {
        activeFilters[checkbox.dataset.filter] = true;
    });
    
    // すべてのモデルカードをフィルタリング
    let visibleCount = 0;
    document.querySelectorAll('.model-card').forEach(card => {
        const modelId = card.dataset.modelId.toLowerCase();
        const provider = card.dataset.provider;
        const cardText = card.textContent.toLowerCase();
        
        // 検索クエリチェック
        const matchesSearch = !searchQuery || modelId.includes(searchQuery) || cardText.includes(searchQuery);
        
        // プロバイダーフィルターチェック
        const matchesProvider = !providerFilter || provider === providerFilter;
        
        // 機能フィルターチェック
        const matchesFunctionCalling = !activeFilters.function_calling || card.dataset.functionCalling === 'true';
        const matchesMultimodal = !activeFilters.multimodal || card.dataset.multimodal === 'true';
        const matchesStreaming = !activeFilters.streaming || card.dataset.streaming === 'true';
        const matchesReasoning = !activeFilters.reasoning || card.dataset.reasoning === 'true';
        
        // すべての条件を満たす場合のみ表示
        if (matchesSearch && matchesProvider && matchesFunctionCalling && matchesMultimodal && matchesStreaming && matchesReasoning) {
            card.style.display = '';
            visibleCount++;
        } else {
            card.style.display = 'none';
        }
    });
    
    // 結果数を更新
    const allModelsSection = document.getElementById('all-models-section');
    if (allModelsSection) {
        const heading = allModelsSection.querySelector('h3');
        if (heading) {
            const totalCount = document.querySelectorAll('#models-grid .model-card').length;
            heading.textContent = `すべてのモデル (${visibleCount}/${totalCount})`;
        }
    }
}

/**
 * お気に入りトグル処理
 */
async function handleFavoriteToggle(event) {
    event.stopPropagation();
    const btn = event.currentTarget;
    const modelId = btn.dataset.modelId;
    const svg = btn.querySelector('svg');
    const isFavorite = svg.classList.contains('fill-current');
    
    // ボタンを一時的に無効化
    btn.disabled = true;
    
    try {
        if (isFavorite) {
            // お気に入りから削除
            const response = await fetch(`/api/ai/favorites/${modelId}`, {
                method: 'DELETE'
            });
            
            if (response.ok) {
                svg.classList.remove('fill-current', 'text-yellow-500');
                svg.classList.add('text-gray-400');
                svg.setAttribute('fill', 'none');
                btn.title = 'お気に入りに追加';
                
                showNotification(`${modelId} をお気に入りから削除しました`, 'info');
            } else {
                throw new Error('Failed to remove from favorites');
            }
        } else {
            // お気に入りに追加
            const response = await fetch('/api/ai/favorites', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model_id: modelId })
            });
            
            if (response.ok) {
                svg.classList.add('fill-current', 'text-yellow-500');
                svg.classList.remove('text-gray-400');
                svg.setAttribute('fill', 'currentColor');
                btn.title = 'お気に入りから削除';
                
                showNotification(`${modelId} をお気に入りに追加しました`, 'success');
            } else {
                throw new Error('Failed to add to favorites');
            }
        }
        
        // お気に入りセクションを更新
        await updateFavoritesSection();
        
        // モデル選択メニューも更新
        import('./ui_settings.js').then(({ updateModelSelectionUI }) => {
            updateModelSelectionUI();
        });
        
    } catch (error) {
        console.error('Failed to toggle favorite:', error);
        showNotification('お気に入りの更新に失敗しました', 'error');
    } finally {
        btn.disabled = false;
    }
}

/**
 * モデル使用処理
 */
async function handleUseModel(event) {
    const btn = event.currentTarget;
    const modelId = btn.dataset.modelId;
    
    // ボタンを一時的に無効化
    btn.disabled = true;
    const originalText = btn.textContent;
    btn.textContent = '設定中...';
    
    try {
        const response = await fetch('/api/ai/set-model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model_id: modelId })
        });
        
        if (response.ok) {
            const data = await response.json();
            
            // 設定を更新
            state.userSettings.model = modelId;
            
            // UIを更新
            await updateModelsTabUI();
            
            // 他のUIも更新
            import('./ui_settings.js').then(({ updateAllUI }) => {
                updateAllUI();
            });
            
            showNotification(data.message || `モデルを ${modelId} に変更しました`, 'success');
        } else {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to set model');
        }
    } catch (error) {
        console.error('Failed to set model:', error);
        showNotification('モデルの変更に失敗しました: ' + error.message, 'error');
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

/**
 * お気に入りセクションのみ更新
 */
async function updateFavoritesSection() {
    try {
        const response = await fetch('/api/ai/favorites');
        const data = await response.json();
        
        if (data.success) {
            const favoritesGrid = document.getElementById('favorites-grid');
            if (favoritesGrid) {
                if (data.favorites.length > 0) {
                    favoritesGrid.innerHTML = data.favorites.map(model => 
                        createModelCard(model, true, state.userSettings.model === model.id)
                    ).join('');
                } else {
                    favoritesGrid.innerHTML = '<p class="text-sm text-gray-500 dark:text-gray-400 col-span-full text-center py-8">お気に入りのモデルがありません</p>';
                }
                
                // イベントリスナーを再設定
                setupModelEventListeners();
            }
        }
    } catch (error) {
        console.error('Failed to update favorites:', error);
    }
}

/**
 * 通知を表示
 */
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `fixed bottom-4 right-4 p-4 rounded-lg shadow-lg ${
        type === 'success' ? 'bg-green-500' : 
        type === 'error' ? 'bg-red-500' : 
        'bg-blue-500'
    } text-white z-50 animate-fadeIn`;
    
    const icon = type === 'success' ? 
        '<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg>' :
        type === 'error' ?
        '<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path></svg>' :
        '<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"></path></svg>';
    
    notification.innerHTML = `
        <div class="flex items-center gap-3">
            ${icon}
            <span>${escapeHtml(message)}</span>
        </div>
    `;
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transform = 'translateY(20px)';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}
