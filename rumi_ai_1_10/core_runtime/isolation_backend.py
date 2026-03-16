"""
isolation_backend.py - 隔離バックエンド抽象インターフェース

アーキテクチャ概要:
    Rumi AI のコード実行は「隔離バックエンド」を通じて行われる。
    現在は Docker ベースの実行（secure_executor.py / python_file_executor.py）が
    唯一の実装だが、将来的に以下のバックエンドへの差し替えを想定している:

    - Docker (現行)
    - Firecracker (microVM ベースの軽量隔離)
    - gVisor (ユーザー空間カーネルによるサンドボックス)
    - Wasm (WebAssembly ランタイムによる隔離)

    本モジュールは、これらのバックエンドが共通で実装すべき
    抽象インターフェース (ABC) と、実行結果を表すデータクラスを定義する。

    各バックエンドは IsolationBackend を継承し、
    execute / is_available / get_name の 3 メソッドを実装する。
    実行結果は IsolationResult dataclass で統一的に返される。

設計原則:
    - 既存の ExecutionResult パターン (secure_executor.py) に合わせたフィールド構成
    - ABC + abstractmethod による厳格なインターフェース強制
    - バックエンド固有のロジックは各実装クラスに委譲
    - 本モジュールには ABC とデータクラスの定義のみを含む
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class IsolationResult:
    """
    隔離バックエンドの実行結果

    既存の ExecutionResult (secure_executor.py / python_file_executor.py) と
    同等のフィールドを持ち、バックエンド間で統一的な結果表現を提供する。

    Attributes:
        success: 実行が成功したかどうか
        output: 実行結果の出力データ (JSON シリアライズ可能な任意の値)
        error: エラー発生時のメッセージ (成功時は None)
        error_type: エラーの種別 (例: "timeout", "container_execution_error")
        execution_time_ms: 実行にかかった時間 (ミリ秒)
        warnings: 実行中に発生した警告メッセージのリスト
    """
    success: bool
    output: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    execution_time_ms: float = 0.0
    warnings: List[str] = field(default_factory=list)


class IsolationBackend(ABC):
    """
    隔離バックエンドの抽象基底クラス

    全ての隔離バックエンド (Docker, Firecracker, gVisor, Wasm 等) は
    このクラスを継承し、以下の 3 メソッドを実装する:

    - execute(): 隔離環境内でスクリプトを実行する
    - is_available(): バックエンドが現在の環境で利用可能かを返す
    - get_name(): バックエンドの識別名を返す

    使用例::

        class DockerBackend(IsolationBackend):
            def execute(self, pack_id, script_path, input_data, context, timeout=60):
                # Docker コンテナ内で実行
                ...
                return IsolationResult(success=True, output=result)

            def is_available(self) -> bool:
                # docker info が成功するかチェック
                ...

            def get_name(self) -> str:
                return "docker"
    """

    @abstractmethod
    def execute(
        self,
        pack_id: str,
        script_path: Path,
        input_data: Any,
        context: Dict[str, Any],
        timeout: int = 60,
    ) -> IsolationResult:
        """
        隔離環境内でスクリプトを実行する

        Args:
            pack_id: 実行対象の Pack ID
            script_path: 実行するスクリプトのパス
            input_data: スクリプトに渡す入力データ
            context: 実行コンテキスト (flow_id, step_id, phase 等)
            timeout: タイムアウト秒数 (デフォルト: 60)

        Returns:
            IsolationResult: 実行結果
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """
        バックエンドが現在の環境で利用可能かを返す

        Returns:
            bool: 利用可能なら True
        """
        ...

    @abstractmethod
    def get_name(self) -> str:
        """
        バックエンドの識別名を返す

        Returns:
            str: バックエンド名 (例: "docker", "firecracker", "gvisor", "wasm")
        """
        ...
