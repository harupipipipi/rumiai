"""FlowEngine — フロー実行エンジン（最小動作版）"""

import sys
import os
import importlib.util

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp

from .context import FlowContext
from .result import FlowResult
from .modifier import ModifierLoader


class FlowEngine:
    """Flow 実行エンジン（最小動作版）

    シングルトンパターンで実装。flow_id を受けて対応する handler.py を
    動的にロード・実行する。flows/ ディレクトリ配下のフロー定義を
    自動的にスキャンして登録する。
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._flows = {}
        self._handlers = {}
        self._modifier_loader = ModifierLoader()
        self._base_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        self._load_flows()

    def _load_flows(self):
        """flows/ 配下のフロー定義をロードする

        flows/ ディレクトリ内の各サブディレクトリを走査し、
        flow.yaml が存在するものをフロー定義として登録する。
        """
        flows_dir = os.path.join(self._base_dir, "flows")
        if not os.path.isdir(flows_dir):
            return
        for entry in sorted(os.listdir(flows_dir)):
            flow_path = os.path.join(flows_dir, entry)
            if not os.path.isdir(flow_path):
                continue
            yaml_path = os.path.join(flow_path, "flow.yaml")
            if not os.path.isfile(yaml_path):
                continue
            flow_def = self._parse_yaml(yaml_path)
            flow_id = flow_def.get("flow_id", entry)
            flow_def["_dir"] = flow_path
            flow_def["_yaml_path"] = yaml_path
            if "flow_id" not in flow_def:
                flow_def["flow_id"] = flow_id
            self._flows[flow_id] = flow_def

    def _parse_yaml(self, path):
        """YAML ファイルをパースする

        PyYAML が利用可能ならそれを使い、なければトップレベルの
        key: value ペアのみを抽出する簡易パーサーにフォールバックする。

        Args:
            path: YAML ファイルのパス

        Returns:
            パース結果の dict
        """
        try:
            import yaml
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data if isinstance(data, dict) else {}
        except ImportError:
            return self._parse_yaml_fallback(path)
        except Exception:
            return self._parse_yaml_fallback(path)

    def _parse_yaml_fallback(self, path):
        """YAML の簡易フォールバックパーサー

        トップレベルの key: value ペアのみを抽出する。
        ネストされた構造は無視する。

        Args:
            path: YAML ファイルのパス

        Returns:
            パース結果の dict
        """
        result = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.rstrip("\n\r")
                    if not stripped or stripped.lstrip().startswith("#"):
                        continue
                    if stripped[0] in (" ", "\t"):
                        continue
                    if ":" not in stripped:
                        continue
                    key, _, value = stripped.partition(":")
                    key = key.strip()
                    value = value.strip()
                    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'") and len(value) >= 2:
                        value = value[1:-1]
                    if value and key:
                        result[key] = value
        except Exception:
            pass
        return result

    def _get_handler(self, flow_id):
        """フロー ID に対応するハンドラモジュールを取得する

        キャッシュされたモジュールがあればそれを返し、なければ
        importlib で動的にロードしてキャッシュする。

        Args:
            flow_id: フロー ID

        Returns:
            handler モジュール。見つからなければ None。
        """
        if flow_id in self._handlers:
            return self._handlers[flow_id]
        flow_def = self._flows.get(flow_id)
        if not flow_def:
            return None
        handler_file = flow_def.get("handler", "handler.py")
        flow_dir = flow_def.get("_dir", "")
        handler_path = os.path.join(flow_dir, handler_file)
        if not os.path.isfile(handler_path):
            return None
        try:
            module_name = "flows_{}_handler".format(
                flow_id.replace("/", "_").replace("-", "_")
            )
            spec = importlib.util.spec_from_file_location(module_name, handler_path)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._handlers[flow_id] = module
            return module
        except Exception:
            return None

    def execute(self, flow_id, trigger_input, context=None):
        """フローを実行する

        指定された flow_id のハンドラをロードし、FlowContext を構築して
        handler.run() を呼び出す。結果を FlowResult として返す。

        Args:
            flow_id: 実行するフローの ID
            trigger_input: フローへの入力データ dict
            context: 親コンテキスト dict（オプション）

        Returns:
            FlowResult インスタンス
        """
        if flow_id not in self._flows:
            return FlowResult(
                status="error",
                output=error("Flow '{}' not found".format(flow_id)),
                metadata={"flow_id": flow_id},
            )

        handler = self._get_handler(flow_id)
        if handler is None:
            return FlowResult(
                status="error",
                output=error(
                    "Handler for flow '{}' could not be loaded".format(flow_id)
                ),
                metadata={"flow_id": flow_id},
            )

        if not hasattr(handler, "run") or not callable(handler.run):
            return FlowResult(
                status="error",
                output=error(
                    "Handler for flow '{}' has no callable run()".format(flow_id)
                ),
                metadata={"flow_id": flow_id},
            )

        flow_def = self._flows[flow_id]
        flow_config = flow_def.get("config_schema", {})
        parent_ctx = context if context is not None else {}
        session = {}
        if isinstance(parent_ctx, dict):
            session = parent_ctx.get("session", {})
            if not isinstance(session, dict):
                session = {}

        flow_context = FlowContext(
            flow_id=flow_id,
            trigger_input=trigger_input,
            flow_config=flow_config,
            session=session,
            parent_context=parent_ctx,
        )

        modifiers = self._modifier_loader.load_modifiers(flow_id)
        self._modifier_loader.apply_pre_hooks(modifiers, flow_context)

        flow_context.emit_event(
            "flow.started",
            {
                "flow_id": flow_id,
                "trigger_input_keys": (
                    list(trigger_input.keys())
                    if isinstance(trigger_input, dict)
                    else []
                ),
            },
        )

        try:
            result_data = handler.run(trigger_input, flow_context)
        except Exception as exc:
            flow_context.emit_event("flow.error", {"error": str(exc)})
            return FlowResult(
                status="error",
                output=error(str(exc)),
                metadata={
                    "flow_id": flow_id,
                    "execution_id": flow_context.execution_id,
                    "exception_type": type(exc).__name__,
                },
            )

        session_messages = []
        if isinstance(flow_context.session, dict):
            session_messages = flow_context.session.get("messages", [])
            if not isinstance(session_messages, list):
                session_messages = []

        flow_result = FlowResult(
            status="completed",
            output=result_data if result_data is not None else {},
            messages=session_messages,
            metadata={
                "flow_id": flow_id,
                "execution_id": flow_context.execution_id,
                "created_at": flow_context.created_at,
            },
        )

        self._modifier_loader.apply_post_hooks(modifiers, flow_context, flow_result)

        flow_context.emit_event(
            "flow.completed",
            {"flow_id": flow_id, "status": flow_result.status},
        )

        return flow_result

    def list_flows(self):
        """利用可能なフロー一覧を返す

        Returns:
            フロー情報の dict のリスト。各要素は flow_id, name, description を含む。
        """
        result = []
        for flow_id in sorted(self._flows.keys()):
            flow_def = self._flows[flow_id]
            result.append(
                {
                    "flow_id": flow_id,
                    "name": flow_def.get("name", flow_id),
                    "description": flow_def.get("description", ""),
                    "version": flow_def.get("version", "0.0.0"),
                }
            )
        return result

    def get_flow(self, flow_id):
        """フロー定義を取得する

        内部管理用のキー（_dir, _yaml_path 等）は除外して返す。

        Args:
            flow_id: フロー ID

        Returns:
            フロー定義 dict。見つからなければ None。
        """
        flow_def = self._flows.get(flow_id)
        if flow_def is None:
            return None
        safe_copy = {}
        for key, value in flow_def.items():
            if not key.startswith("_"):
                safe_copy[key] = value
        return safe_copy

    def reload_flows(self):
        """フロー定義を再ロードする

        キャッシュをクリアして flows/ ディレクトリを再スキャンする。
        """
        self._flows.clear()
        self._handlers.clear()
        self._modifier_loader.clear_cache()
        self._load_flows()

    @classmethod
    def reset_instance(cls):
        """シングルトンインスタンスをリセットする（テスト用）"""
        cls._instance = None
