"""
lang.py - 多言語対応システム

公式コードにi18n（国際化）基盤を提供する。

設計原則:
- 公式は「仕組み」のみ提供
- 具体的なメッセージは lang/ ディレクトリに配置
- Packも独自の lang/ を持てる

ファイル形式（lang/en.txt, lang/ja.txt等）:
    # コメント
    key=value
    error.not_found={name} not found
    welcome=Hello, {user}!

Usage:
    from core_runtime.lang import L, set_locale, get_locale
    
    set_locale("ja")  # または user_data/settings/locale.txt から自動読み込み
    
    print(L("startup.success"))  # → "カーネルの起動が完了しました"
    print(L("error.not_found", name="config.json"))  # → "config.jsonが見つかりません"

PR-B追加:
- LangManager / get_lang_manager の互換alias（B6）
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Dict, Optional


LANG_DIR = "lang"
DEFAULT_LOCALE = "en"
LOCALE_FILE = "user_data/settings/locale.txt"


class LangRegistry:
    """多言語メッセージレジストリ"""
    
    def __init__(self):
        self._lock = threading.RLock()
        self._locale: str = DEFAULT_LOCALE
        self._messages: Dict[str, Dict[str, str]] = {}  # locale -> {key -> value}
        self._pack_messages: Dict[str, Dict[str, Dict[str, str]]] = {}  # pack_id -> locale -> {key -> value}
        self._loaded_locales: set = set()
        
        self._load_user_locale()
        self._load_locale(self._locale)
        if self._locale != DEFAULT_LOCALE:
            self._load_locale(DEFAULT_LOCALE)
    
    def _load_user_locale(self) -> None:
        """ユーザー設定からlocaleを読み込み"""
        locale_file = Path(LOCALE_FILE)
        if locale_file.exists():
            try:
                locale = locale_file.read_text(encoding='utf-8').strip().lower()
                if locale:
                    self._locale = locale
            except Exception:
                pass
    
    def _load_locale(self, locale: str) -> bool:
        """指定localeのメッセージファイルを読み込み"""
        if locale in self._loaded_locales:
            return True
        
        lang_file = Path(LANG_DIR) / f"{locale}.txt"
        if not lang_file.exists():
            return False
        
        try:
            messages = self._parse_lang_file(lang_file)
            with self._lock:
                self._messages[locale] = messages
                self._loaded_locales.add(locale)
            return True
        except Exception as e:
            print(f"[Lang] Failed to load {lang_file}: {e}")
            return False
    
    def _parse_lang_file(self, file_path: Path) -> Dict[str, str]:
        """言語ファイルをパース"""
        messages = {}
        
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                if not line or line.startswith('#'):
                    continue
                
                if '=' not in line:
                    continue
                
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # エスケープ処理
                value = value.replace('\\n', '\n')
                
                if key:
                    messages[key] = value
        
        return messages
    
    def get(self, key: str, **kwargs) -> str:
        """メッセージを取得"""
        with self._lock:
            # 現在のlocaleで検索
            if self._locale in self._messages:
                if key in self._messages[self._locale]:
                    return self._format(self._messages[self._locale][key], kwargs)
            
            # デフォルトlocaleで検索
            if DEFAULT_LOCALE in self._messages:
                if key in self._messages[DEFAULT_LOCALE]:
                    return self._format(self._messages[DEFAULT_LOCALE][key], kwargs)
            
            # 見つからない場合はキーをそのまま返す
            return key
    
    def _format(self, template: str, kwargs: Dict[str, Any]) -> str:
        """変数を展開"""
        if not kwargs:
            return template
        
        result = template
        for key, value in kwargs.items():
            result = result.replace('{' + key + '}', str(value))
        
        return result
    
    def set_locale(self, locale: str) -> bool:
        """localeを設定"""
        locale = locale.strip().lower()
        
        if locale not in self._loaded_locales:
            if not self._load_locale(locale):
                return False
        
        with self._lock:
            self._locale = locale
        
        return True
    
    def get_locale(self) -> str:
        """現在のlocaleを取得"""
        with self._lock:
            return self._locale
    
    def load_pack_lang(self, pack_subdir: Path, pack_id: str) -> int:
        """Packの言語ファイルを読み込み"""
        lang_dir = pack_subdir / LANG_DIR
        if not lang_dir.exists():
            return 0
        
        count = 0
        
        for lang_file in lang_dir.glob("*.txt"):
            locale = lang_file.stem.lower()
            try:
                messages = self._parse_lang_file(lang_file)
                
                with self._lock:
                    if pack_id not in self._pack_messages:
                        self._pack_messages[pack_id] = {}
                    self._pack_messages[pack_id][locale] = messages
                
                count += 1
            except Exception:
                pass
        
        return count
    
    def get_pack(self, pack_id: str, key: str, **kwargs) -> str:
        """Pack固有のメッセージを取得"""
        with self._lock:
            if pack_id in self._pack_messages:
                # 現在のlocale
                if self._locale in self._pack_messages[pack_id]:
                    if key in self._pack_messages[pack_id][self._locale]:
                        return self._format(self._pack_messages[pack_id][self._locale][key], kwargs)
                
                # デフォルトlocale
                if DEFAULT_LOCALE in self._pack_messages[pack_id]:
                    if key in self._pack_messages[pack_id][DEFAULT_LOCALE]:
                        return self._format(self._pack_messages[pack_id][DEFAULT_LOCALE][key], kwargs)
        
        # フォールバック: 公式メッセージ
        return self.get(key, **kwargs)
    
    def reload(self) -> None:
        """全メッセージを再読み込み"""
        with self._lock:
            self._messages.clear()
            self._pack_messages.clear()
            self._loaded_locales.clear()
        
        self._load_user_locale()
        self._load_locale(self._locale)
        if self._locale != DEFAULT_LOCALE:
            self._load_locale(DEFAULT_LOCALE)


# ============================================================
# B6: 互換alias（破壊的変更禁止）
# ============================================================

# LangManager は LangRegistry の別名
LangManager = LangRegistry


_global_lang_registry: Optional[LangRegistry] = None
_lang_lock = threading.Lock()


def _get_registry() -> LangRegistry:
    """グローバルなLangRegistryを取得"""
    global _global_lang_registry
    if _global_lang_registry is None:
        with _lang_lock:
            if _global_lang_registry is None:
                _global_lang_registry = LangRegistry()
    return _global_lang_registry


def get_lang_registry() -> LangRegistry:
    """LangRegistryインスタンスを取得"""
    return _get_registry()


# B6: 互換alias - get_lang_manager は get_lang_registry の別名
def get_lang_manager() -> LangRegistry:
    """
    LangManager（LangRegistry）インスタンスを取得
    
    B6: 後方互換のためのalias
    __init__.py が get_lang_manager をexportしているため、
    この関数が存在しないと ImportError になる。
    """
    return _get_registry()


def L(key: str, **kwargs) -> str:
    """メッセージを取得（ショートカット）"""
    return _get_registry().get(key, **kwargs)


def Lp(pack_id: str, key: str, **kwargs) -> str:
    """Pack固有のメッセージを取得（ショートカット）"""
    return _get_registry().get_pack(pack_id, key, **kwargs)


def set_locale(locale: str) -> bool:
    """localeを設定"""
    return _get_registry().set_locale(locale)


def get_locale() -> str:
    """現在のlocaleを取得"""
    return _get_registry().get_locale()


def reload_lang() -> None:
    """言語ファイルを再読み込み"""
    _get_registry().reload()


def load_system_lang() -> None:
    """
    システム言語ファイルを読み込む（互換関数）

    app.py が from core_runtime.lang import load_system_lang として
    呼び出すため、ImportError を防ぐ互換関数。
    内部で reload_lang() を呼ぶ。
    """
    reload_lang()
