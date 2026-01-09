// static/js/utils.js

/**
 * HTML特殊文字をエスケープします。
 * @param {string} unsafe - エスケープ対象の文字列
 * @returns {string} エスケープ後の文字列
 */
export function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') return '';
    return unsafe
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/**
 * FileオブジェクトをData URL形式の文字列に変換します。
 * @param {File} file - 変換するFileオブジェクト
 * @returns {Promise<string>} Data URL文字列
 */
export function readFileAsDataURL(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = (error) => reject(error);
        reader.readAsDataURL(file);
    });
}

/**
 * 現在のテーマに応じたAIのアイコンパスを取得します。
 * @returns {string} アイコン画像のパス
 */
export function getAIIconSrc() {
    const isDark = document.documentElement.classList.contains('dark');
    return isDark ? '/static/images/icon_dark.png' : '/static/images/icon_light.png';
}
