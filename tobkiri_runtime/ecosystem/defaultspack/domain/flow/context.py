"""Flow execution context with durable checkpoints and public events."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import error, gen_id, timestamp


class FlowControlError(RuntimeError):
    """Base class for a deliberate durable-flow stop."""

    status = "failed"
    code = "FLOW_STOPPED"


class FlowCancelled(FlowControlError):
    status = "cancelled"
    code = "FLOW_CANCELLED"


class FlowPaused(FlowControlError):
    status = "paused"
    code = "FLOW_PAUSED"


class FlowBudgetExceeded(FlowControlError):
    status = "failed"
    code = "FLOW_BUDGET_EXCEEDED"


class FlowContext:
    """Flow 実行コンテキスト

    フローのハンドラに渡され、外部サービスへのアクセスや
    変数の保存・取得、イベント発行などの機能を提供する。
    """

    def __init__(
        self,
        flow_id,
        trigger_input,
        flow_config,
        session=None,
        parent_context=None,
        *,
        execution_id=None,
        run_store=None,
    ):
        self.flow_id = flow_id
        self.trigger_input = trigger_input
        self.flow_config = flow_config
        self.session = session if session is not None else {}
        self._parent_context = parent_context if parent_context is not None else {}
        self._variables = {}
        self._events = []
        self._execution_id = str(execution_id or gen_id())
        self._run_store = run_store
        self._created_at = timestamp()

    def call_handler(self, handler_name, params):
        """他の handler を呼び出す

        parent_context に call_handler コールバックがあればそれに委譲し、
        なければスタブ応答を返すフォールバック。

        Args:
            handler_name: 呼び出すハンドラ名（例: "defaults.chat.send"）
            params: ハンドラに渡すパラメータ dict

        Returns:
            ハンドラの実行結果 dict
        """
        if isinstance(self._parent_context, dict) and "call_handler" in self._parent_context:
            callback = self._parent_context["call_handler"]
            if callable(callback):
                return callback(handler_name, params)
        if hasattr(self._parent_context, "call_handler") and callable(getattr(self._parent_context, "call_handler", None)):
            return self._parent_context.call_handler(handler_name, params)
        return error(f"handler is not available in this flow context: {handler_name}", code="NOT_IMPLEMENTED")

    def emit_event(self, event_type, data):
        """イベントを発行する

        parent_context に emit_event コールバックがあればそれに委譲し、
        なければ内部のイベントリストに記録する。

        Args:
            event_type: イベントタイプ文字列
            data: イベントデータ dict
        """
        event_record = {
            "type": event_type,
            "data": data,
            "flow_id": self.flow_id,
            "execution_id": self._execution_id,
            "timestamp": timestamp(),
        }
        self._events.append(event_record)
        if self._run_store is not None:
            self._run_store.append_event(self._execution_id, event_record)
        if isinstance(self._parent_context, dict) and "emit_event" in self._parent_context:
            callback = self._parent_context["emit_event"]
            if callable(callback):
                return callback(event_type, data)
        if hasattr(self._parent_context, "emit_event") and callable(getattr(self._parent_context, "emit_event", None)):
            return self._parent_context.emit_event(event_type, data)
        return None

    def set_variable(self, key, value):
        """コンテキスト変数を設定する

        Args:
            key: 変数名
            value: 変数値
        """
        self._variables[key] = value

    def get_variable(self, key, default=None):
        """コンテキスト変数を取得する

        Args:
            key: 変数名
            default: デフォルト値

        Returns:
            変数値。存在しなければ default。
        """
        return self._variables.get(key, default)

    def get_config(self, key, default=None):
        """フロー設定値を取得する

        config_schema から key に対応するデフォルト値を取得する。

        Args:
            key: 設定キー
            default: デフォルト値

        Returns:
            設定値。存在しなければ default。
        """
        if isinstance(self.flow_config, dict):
            schema_entry = self.flow_config.get(key)
            if schema_entry is None:
                return default
            if isinstance(schema_entry, dict) and "default" in schema_entry:
                return schema_entry["default"]
            if not isinstance(schema_entry, dict):
                return schema_entry
        return default

    def get_events(self):
        """記録されたイベント一覧を返す"""
        return list(self._events)

    def check_control(self):
        """Stop at a safe boundary when durable control or budgets require it."""

        if isinstance(self._parent_context, dict):
            cancelled = self._parent_context.get("is_cancelled")
            if callable(cancelled) and cancelled():
                if self._run_store is not None:
                    self._run_store.request_cancel(
                        self._execution_id,
                        reason="user_cancel",
                    )
                raise FlowCancelled("flow run was cancelled by the user")
        if self._run_store is None:
            return
        state = self._run_store.control_state(self._execution_id)
        if state.get("cancel_requested"):
            raise FlowCancelled("flow run was cancelled")
        if state.get("pause_requested"):
            raise FlowPaused("flow run was paused")
        if state.get("timed_out"):
            raise FlowBudgetExceeded("flow timeout exceeded")
        if state.get("token_budget_exhausted"):
            raise FlowBudgetExceeded("flow token budget exceeded")
        if state.get("cost_budget_exhausted"):
            raise FlowBudgetExceeded("flow cost budget exceeded")

    def checkpoint(
        self,
        *,
        phase,
        step_id,
        values,
        outputs,
        iteration=0,
        usage=None,
    ):
        """Persist a resumable checkpoint at a phase boundary."""

        if self._run_store is None:
            return None
        return self._run_store.checkpoint(
            self._execution_id,
            phase=phase,
            step_id=step_id,
            values=values,
            outputs=outputs,
            iteration=iteration,
            usage=usage,
        )

    def receipt(self, receipt_key):
        if self._run_store is None:
            return None
        return self._run_store.receipt(self._execution_id, receipt_key)

    def record_receipt(self, receipt_key, result):
        if self._run_store is None:
            return None
        return self._run_store.record_receipt(
            self._execution_id,
            receipt_key=receipt_key,
            result=result,
        )

    @property
    def execution_id(self):
        """実行 ID"""
        return self._execution_id

    @property
    def created_at(self):
        """コンテキスト作成日時"""
        return self._created_at
