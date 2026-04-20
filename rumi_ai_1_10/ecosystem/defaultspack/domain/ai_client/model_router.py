import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

"""
model_router.py — モデルルーティングロジック

AIClient をラップし、入力を分析して最適モデルに自動ルーティングする。
AIClient 自体は変更しない。
"""

import time
import json
import copy

from domain.ai_client.task_analyzer import analyze_fast, analyze_heavy
from domain.ai_client.model_profiles import ModelProfileManager


class RoutingLog:
    """ルーティングログを管理するシンプルなインメモリストア。"""

    def __init__(self, max_entries=1000):
        self._entries = []
        self._max_entries = max_entries

    def add(self, entry):
        """ログエントリを追加する。

        Parameters
        ----------
        entry : dict
        """
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

    def get_all(self, limit=100, offset=0):
        """ログを取得する（新しい順）。

        Parameters
        ----------
        limit : int
        offset : int

        Returns
        -------
        list[dict]
        """
        reversed_entries = list(reversed(self._entries))
        return reversed_entries[offset:offset + limit]

    def count(self):
        """ログ件数を返す。"""
        return len(self._entries)

    def clear(self):
        """ログをクリアする。"""
        self._entries.clear()


class RoutingRule:
    """カスタムルーティングルール。

    ルールは JSON シリアライズ可能な条件で定義される。
    condition は以下のフィールドを持つ dict:
    - "task_type": str (マッチするタスク種類)
    - "complexity": str (マッチする複雑さ)
    - "min_tokens": int (最小トークン数)
    - "max_tokens": int (最大トークン数)
    - "has_code": bool
    - "has_images": bool
    - "language_hint": str
    各フィールドは省略可能。指定されたフィールド全てがマッチした場合にルールが適用される。
    """

    def __init__(self, rule_id, name, condition, target_model, priority=0):
        self.rule_id = rule_id
        self.name = name
        self.condition = condition
        self.target_model = target_model
        self.priority = priority

    def matches(self, analysis_result):
        """分析結果がこのルールの条件にマッチするか判定する。

        Parameters
        ----------
        analysis_result : dict

        Returns
        -------
        bool
        """
        cond = self.condition
        if "task_type" in cond:
            if analysis_result.get("task_type") != cond["task_type"]:
                return False
        if "complexity" in cond:
            if analysis_result.get("complexity") != cond["complexity"]:
                return False
        if "min_tokens" in cond:
            if analysis_result.get("context_tokens_estimate", 0) < cond["min_tokens"]:
                return False
        if "max_tokens" in cond:
            if analysis_result.get("context_tokens_estimate", 0) > cond["max_tokens"]:
                return False
        if "has_code" in cond:
            if analysis_result.get("has_code") != cond["has_code"]:
                return False
        if "has_images" in cond:
            if analysis_result.get("has_images") != cond["has_images"]:
                return False
        if "language_hint" in cond:
            if analysis_result.get("language_hint") != cond["language_hint"]:
                return False
        return True

    def to_dict(self):
        """JSON シリアライズ可能な dict に変換する。"""
        return {
            "id": self.rule_id,
            "name": self.name,
            "condition": copy.deepcopy(self.condition),
            "target_model": self.target_model,
            "priority": self.priority,
        }


class ModelRouter:
    """モデルルーティングエンジン。

    AIClient をラップして使用する。AIClient 自体は変更しない。

    Parameters
    ----------
    client : AIClient
        AIClient インスタンス。
    """

    _instance = None

    def __new__(cls, client=None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, client=None):
        if self._initialized:
            return
        self._initialized = True
        self._client = client
        self._profile_manager = ModelProfileManager()
        self._routing_log = RoutingLog()
        self._custom_rules = []
        self._next_rule_id = 1

    @property
    def profile_manager(self):
        """ModelProfileManager へのアクセス。"""
        return self._profile_manager

    @property
    def routing_log(self):
        """RoutingLog へのアクセス。"""
        return self._routing_log

    def set_client(self, client):
        """AIClient を設定する。遅延初期化用。"""
        self._client = client

    def analyze(self, messages, mode="fast"):
        """入力を分析する。

        Parameters
        ----------
        messages : list[dict]
            StandardMessage 形式。
        mode : str
            "fast" or "heavy"

        Returns
        -------
        dict
            分析結果。
        """
        if mode == "heavy":
            return analyze_heavy(messages)
        return analyze_fast(messages)

    def add_rule(self, name, condition, target_model, priority=0):
        """カスタムルーティングルールを追加する。

        Parameters
        ----------
        name : str
        condition : dict
        target_model : str
        priority : int

        Returns
        -------
        dict
            作成されたルール。
        """
        rule_id = "rule_{}".format(self._next_rule_id)
        self._next_rule_id += 1
        rule = RoutingRule(rule_id, name, condition, target_model, priority)
        self._custom_rules.append(rule)
        # 優先度の高い順にソート
        self._custom_rules.sort(key=lambda r: r.priority, reverse=True)
        return rule.to_dict()

    def remove_rule(self, rule_id):
        """ルールを削除する。

        Parameters
        ----------
        rule_id : str

        Returns
        -------
        bool
            削除成功なら True。
        """
        before = len(self._custom_rules)
        self._custom_rules = [r for r in self._custom_rules if r.rule_id != rule_id]
        return len(self._custom_rules) < before

    def list_rules(self):
        """全ルールをリストで返す。

        Returns
        -------
        list[dict]
        """
        return [r.to_dict() for r in self._custom_rules]

    def route(self, messages, mode="fast", speed_preference="balanced"):
        """入力を分析し、最適モデルを選択する。

        Parameters
        ----------
        messages : list[dict]
            StandardMessage 形式。
        mode : str
            "fast" or "heavy"
        speed_preference : str
            "fast", "balanced", "heavy"

        Returns
        -------
        dict
            {
                "selected_model": str,
                "analysis": dict,
                "scores": dict,
                "matched_rule": str | None,
                "reason": str,
            }
        """
        start_time = time.time()

        # 1. 入力分析
        analysis = self.analyze(messages, mode=mode)

        # 2. カスタムルールチェック
        matched_rule = None
        for rule in self._custom_rules:
            if rule.matches(analysis):
                # ターゲットモデルのプロバイダーが利用可能か確認
                if self._is_model_available(rule.target_model):
                    matched_rule = rule
                    break

        if matched_rule is not None:
            selected_model = matched_rule.target_model
            reason = "Matched custom rule: {}".format(matched_rule.name)
            scores = {}
        else:
            # 3. プロファイルベースのスコアリング
            available_models = self._profile_manager.get_available_models(self._client)
            if not available_models:
                selected_model = "stub/default"
                reason = "No available models found"
                scores = {}
            else:
                scores = {}
                for model_key in available_models:
                    scores[model_key] = self._profile_manager.score_model(
                        model_key, analysis, speed_preference=speed_preference
                    )
                # 最高スコアのモデルを選択
                selected_model = max(scores, key=scores.get)
                reason = "Best score: {:.1f}".format(scores[selected_model])

        elapsed = time.time() - start_time

        # 4. ログ記録
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "selected_model": selected_model,
            "analysis": analysis,
            "scores": scores,
            "matched_rule": matched_rule.to_dict() if matched_rule else None,
            "reason": reason,
            "mode": mode,
            "speed_preference": speed_preference,
            "elapsed_ms": round(elapsed * 1000, 2),
        }
        self._routing_log.add(log_entry)

        return {
            "selected_model": selected_model,
            "analysis": analysis,
            "scores": scores,
            "matched_rule": matched_rule.name if matched_rule else None,
            "reason": reason,
        }

    def route_and_complete(self, messages, mode="fast", speed_preference="balanced",
                           tools=None, params=None):
        """ルーティング + AI 呼び出しを一括で行う。

        Parameters
        ----------
        messages : list[dict]
        mode : str
        speed_preference : str
        tools : list | None
        params : dict | None

        Returns
        -------
        dict
            {
                "routing": dict (route() の結果),
                "response": dict (AIClient.complete() の結果),
            }
        """
        routing_result = self.route(messages, mode=mode, speed_preference=speed_preference)
        selected_model = routing_result["selected_model"]

        response = self._client.complete(
            selected_model, messages, tools=tools or [], params=params or {}
        )

        return {
            "routing": routing_result,
            "response": response,
        }

    def route_and_stream(self, messages, mode="fast", speed_preference="balanced",
                         tools=None, params=None):
        """ルーティング + ストリーミング AI 呼び出しを一括で行う。

        Parameters
        ----------
        messages : list[dict]
        mode : str
        speed_preference : str
        tools : list | None
        params : dict | None

        Returns
        -------
        tuple(dict, generator)
            (routing_result, stream_generator)
        """
        routing_result = self.route(messages, mode=mode, speed_preference=speed_preference)
        selected_model = routing_result["selected_model"]

        stream_gen = self._client.stream(
            selected_model, messages, tools=tools or [], params=params or {}
        )

        return routing_result, stream_gen

    def _is_model_available(self, model_key):
        """モデルが利用可能か判定する。

        Parameters
        ----------
        model_key : str

        Returns
        -------
        bool
        """
        if self._client is None:
            return False
        if "/" in model_key:
            provider_name = model_key.split("/", 1)[0]
            return provider_name in self._client._providers
        return False
