"""PromptTemplate — tool と prompt の統一テンプレートシステム。

tool と prompt は構造が類似している:
    - name / description
    - parameters (tool) ⇔ variables (prompt)
    - 実行ロジック (tool) ⇔ テンプレート本文 (prompt)

PromptTemplate はこの共通基盤を提供する。

変数展開:
    {{variable_name}}           — 通常変数（ユーザー指定）
    {{context.total_tokens}}    — 特殊変数（実行時に自動注入）
    {{context.message_count}}   — 特殊変数
    {{context.messages}}        — 特殊変数
    {{context.knowledge}}       — 特殊変数（関連ナレッジ）
    {{context.memory}}          — 特殊変数（関連メモリ）
"""

from __future__ import annotations

import copy
import json
import re
from typing import Any


# 特殊コンテキスト変数のキー一覧
CONTEXT_VARIABLE_KEYS = (
    "context.total_tokens",
    "context.message_count",
    "context.messages",
    "context.system_prompt",
    "context.conversation_id",
    "context.knowledge",
    "context.memory",
)

# {{var}} or {{context.xxx}} にマッチ
_VAR_PATTERN = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


class PromptTemplate:
    """tool / prompt 共通のテンプレート表現。

    Attributes:
        name:        テンプレート名
        description: テンプレートの説明
        variables:   変数定義のリスト
                     [{"name": str, "type": str, "default": Any, "required": bool}, ...]
        body:        テンプレート本文（{{var}} を含む文字列）
        metadata:    自由形式のメタデータ dict
    """

    def __init__(
        self,
        name: str = "",
        description: str = "",
        variables: list[dict] | None = None,
        body: str = "",
        metadata: dict | None = None,
    ):
        self.name = name
        self.description = description
        self.variables: list[dict] = list(variables or [])
        self.body = body
        self.metadata: dict = dict(metadata or {})

    # ------------------------------------------------------------------
    # シリアライズ
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        """dict 表現を返す。JSON 永続化に使用。"""
        return {
            "name": self.name,
            "description": self.description,
            "variables": copy.deepcopy(self.variables),
            "body": self.body,
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PromptTemplate":
        """dict から PromptTemplate を復元する。"""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            variables=data.get("variables"),
            body=data.get("body", ""),
            metadata=data.get("metadata"),
        )

    # ------------------------------------------------------------------
    # tool JSON Schema 変換
    # ------------------------------------------------------------------
    def to_tool_schema(self) -> dict:
        """tool の JSON Schema 形式に変換する。

        Returns:
            {
                "tool_id":   str,
                "name":      str,
                "summary":   str,
                "tags":      ["prompt-converted"],
                "schema": {
                    "parameters": {
                        "type": "object",
                        "properties": {...},
                        "required": [...]
                    }
                },
                "execution": {"type": "prompt", "body": str}
            }
        """
        properties: dict[str, dict] = {}
        required: list[str] = []

        for var in self.variables:
            var_name = var.get("name", "")
            if not var_name:
                continue
            # context.* 変数は tool パラメータにしない
            if var_name.startswith("context."):
                continue
            prop: dict[str, Any] = {
                "type": var.get("type", "string"),
            }
            default = var.get("default")
            if default is not None:
                prop["default"] = default
            properties[var_name] = prop
            if var.get("required", False):
                required.append(var_name)

        return {
            "tool_id": self.name,
            "name": self.name,
            "summary": self.description,
            "tags": ["prompt-converted"],
            "schema": {
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                }
            },
            "execution": {
                "type": "prompt",
                "body": self.body,
            },
        }

    @classmethod
    def from_tool_schema(cls, schema: dict) -> "PromptTemplate":
        """tool 定義から PromptTemplate を生成する。

        Args:
            schema: ToolRegistry に登録された tool 定義 dict

        Returns:
            PromptTemplate インスタンス
        """
        name = schema.get("name", schema.get("tool_id", ""))
        description = schema.get("summary", "")
        parameters = (
            schema.get("schema", {})
            .get("parameters", {})
        )
        props = parameters.get("properties", {})
        required_list = set(parameters.get("required", []))

        variables: list[dict] = []
        for var_name, var_def in props.items():
            variables.append({
                "name": var_name,
                "type": var_def.get("type", "string"),
                "default": var_def.get("default"),
                "required": var_name in required_list,
            })

        # テンプレート本文: 各変数を {{var}} として埋め込んだ雛形を生成
        body_lines = []
        if description:
            body_lines.append(description)
            body_lines.append("")
        for var in variables:
            body_lines.append(
                f"{var['name']}: {{{{{var['name']}}}}}"
            )

        return cls(
            name=name,
            description=description,
            variables=variables,
            body="\n".join(body_lines),
            metadata={"converted_from": "tool"},
        )

    # ------------------------------------------------------------------
    # 変数抽出
    # ------------------------------------------------------------------
    def extract_variable_names(self) -> list[str]:
        """body 内の {{...}} から変数名を抽出して返す。"""
        return _VAR_PATTERN.findall(self.body)

    def list_context_variables(self) -> list[str]:
        """body 内で使用されている context.* 変数を返す。"""
        return [v for v in self.extract_variable_names() if v.startswith("context.")]

    def list_user_variables(self) -> list[str]:
        """body 内で使用されている通常（非 context.*）変数を返す。"""
        return [v for v in self.extract_variable_names() if not v.startswith("context.")]

    # ------------------------------------------------------------------
    # repr
    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        return (
            f"PromptTemplate(name={self.name!r}, "
            f"variables={len(self.variables)}, "
            f"body_len={len(self.body)})"
        )
