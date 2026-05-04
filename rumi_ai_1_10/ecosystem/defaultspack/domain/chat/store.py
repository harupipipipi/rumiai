import time
import copy
import uuid
import json
import os
import re
import base64
from pathlib import Path

DEFAULT_CHAT_MODEL = "openrouter/tencent/hy3-preview:free"


def _default_conversation_model(settings_path=None):
    try:
        path = settings_path or Path(__file__).resolve().parents[2] / "user_data" / "shared" / "frontend_settings.json"
        settings = json.loads(Path(path).read_text(encoding="utf-8"))
        preferred_model = settings.get("models", {}).get("preferred_model")
        if isinstance(preferred_model, str) and preferred_model.strip():
            return preferred_model.strip()
    except Exception:
        pass
    if settings_path is not None:
        return DEFAULT_CHAT_MODEL
    try:
        from domain.ai_client.profile_loader import ProfileLoader

        profile = ProfileLoader().get("default") or {}
        provider = profile.get("provider")
        model = profile.get("model")
        if provider and model:
            candidate = "{}/{}".format(provider, model)
            if not candidate.startswith("stub/"):
                return candidate
    except Exception:
        pass
    return DEFAULT_CHAT_MODEL


def _gen_id():
    return str(uuid.uuid4())


def _now_ms():
    return int(time.time() * 1000)


class ChatStore:
    _instance = None

    def __new__(cls):
        storage_path = cls._default_storage_path()
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._storage_path = storage_path
            cls._instance._conversations = cls._instance._load_conversations()
            if cls._instance._conversations:
                cls._instance._save_conversation_files()
        elif cls._instance._storage_path != storage_path:
            cls._instance._storage_path = storage_path
            cls._instance._conversations = cls._instance._load_conversations()
            if cls._instance._conversations:
                cls._instance._save_conversation_files()
        return cls._instance

    @staticmethod
    def _default_storage_path():
        override = os.environ.get("RUMI_DEFAULTSPACK_CHAT_STORE_PATH")
        if override:
            return Path(override)
        return Path(__file__).resolve().parents[2] / "user_data" / "shared" / "chat" / "conversations.json"

    def _load_conversations(self):
        try:
            data = json.loads(self._storage_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except Exception:
            return {}
        conversations = data.get("conversations") if isinstance(data, dict) else data
        if not isinstance(conversations, dict):
            return {}
        loaded = {}
        for conversation_id, conversation in conversations.items():
            if not isinstance(conversation, dict):
                continue
            self._normalize_conversation(str(conversation_id), conversation)
            self._sanitize_inline_thought_messages(conversation)
            loaded[str(conversation_id)] = conversation
        return loaded

    def _save_conversations(self):
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        for conversation in self._conversations.values():
            if isinstance(conversation, dict):
                self._sanitize_inline_thought_messages(conversation)
        payload = {
            "schema_version": 1,
            "updated_at": _now_ms(),
            "conversations": self._conversations,
        }
        tmp_path = self._storage_path.with_suffix(self._storage_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self._storage_path)
        self._save_conversation_files()

    # ----------------------------------------------------------
    # Conversation CRUD
    # ----------------------------------------------------------
    def create_conversation(
        self,
        model=None,
        system_prompt_id=None,
        agent_id=None,
        tags=None,
        parent_conversation_id=None,
        conversation_kind=None,
        metadata=None,
        group_id=None,
    ):
        cid = _gen_id()
        now = _now_ms()
        parent_id = str(parent_conversation_id) if parent_conversation_id else None
        conv = {
            "id": cid,
            "title": "New Conversation",
            "created_at": now,
            "updated_at": now,
            "model": model if model else _default_conversation_model(),
            "system_prompt_id": system_prompt_id,
            "agent_id": agent_id,
            "tags": tags if tags is not None else [],
            "is_starred": False,
            "is_archived": False,
            "current_node_id": None,
            "parent_conversation_id": parent_id,
            "child_conversation_ids": [],
            "conversation_kind": conversation_kind or ("subagent" if parent_id else "chat"),
            "group_id": group_id,
            "metadata": metadata if isinstance(metadata, dict) else {},
            "messages": [],
        }
        self._conversations[cid] = conv
        if parent_id and parent_id in self._conversations:
            parent = self._conversations[parent_id]
            self._normalize_conversation(parent_id, parent)
            if cid not in parent["child_conversation_ids"]:
                parent["child_conversation_ids"].append(cid)
            parent["updated_at"] = now
        self._save_conversations()
        return copy.deepcopy(conv)

    def get_conversation(self, conversation_id):
        conv = self._conversations.get(conversation_id)
        if conv is None:
            return None
        return copy.deepcopy(conv)

    def list_conversations(self, limit=50, offset=0, tag=None, is_starred=None, is_archived=None):
        results = []
        for conv in self._conversations.values():
            if tag is not None and tag not in conv.get("tags", []):
                continue
            if is_starred is not None and conv.get("is_starred") != is_starred:
                continue
            if is_archived is not None and conv.get("is_archived") != is_archived:
                continue
            results.append(conv)
        results.sort(key=lambda c: c["updated_at"], reverse=True)
        total = len(results)
        page = results[offset: offset + limit]
        return [copy.deepcopy(c) for c in page], total

    def update_conversation(self, conversation_id, updates):
        conv = self._conversations.get(conversation_id)
        if conv is None:
            return None
        protected = {"id", "created_at", "messages"}
        for key, value in updates.items():
            if key not in protected:
                conv[key] = value
        conv["updated_at"] = _now_ms()
        self._save_conversations()
        return copy.deepcopy(conv)

    def delete_conversation(self, conversation_id):
        if conversation_id in self._conversations:
            conv = self._conversations[conversation_id]
            parent_id = conv.get("parent_conversation_id") if isinstance(conv, dict) else None
            if parent_id in self._conversations:
                parent = self._conversations[parent_id]
                child_ids = parent.get("child_conversation_ids", [])
                if isinstance(child_ids, list):
                    parent["child_conversation_ids"] = [cid for cid in child_ids if cid != conversation_id]
                    parent["updated_at"] = _now_ms()
            for candidate in self._conversations.values():
                if isinstance(candidate, dict) and candidate.get("parent_conversation_id") == conversation_id:
                    candidate["parent_conversation_id"] = None
            del self._conversations[conversation_id]
            self._save_conversations()
            return True
        return False

    # ----------------------------------------------------------
    # Message CRUD
    # ----------------------------------------------------------
    def add_message(self, conversation_id, message_dict):
        conv = self._conversations.get(conversation_id)
        if conv is None:
            return None
        msg = copy.deepcopy(message_dict)
        if "id" not in msg or msg["id"] is None:
            msg["id"] = _gen_id()
        msg["conversation_id"] = conversation_id
        if "parent_id" not in msg or msg["parent_id"] is None:
            msg["parent_id"] = conv["current_node_id"]
        if "children_ids" not in msg:
            msg["children_ids"] = []
        if "sequence_number" not in msg or msg["sequence_number"] is None:
            msg["sequence_number"] = len(conv["messages"]) + 1
        if "created_at" not in msg or msg["created_at"] is None:
            msg["created_at"] = _now_ms()
        if "raw_text" not in msg or msg["raw_text"] is None:
            msg["raw_text"] = self._extract_raw_text(msg.get("content", []))
        for field in ("finish_reason", "usage", "widget", "metadata", "events", "tool_logs"):
            if field not in msg:
                msg[field] = None
        parent_id = msg["parent_id"]
        if parent_id is not None:
            for m in conv["messages"]:
                if m["id"] == parent_id:
                    if msg["id"] not in m["children_ids"]:
                        m["children_ids"].append(msg["id"])
                    break
        conv["messages"].append(msg)
        conv["current_node_id"] = msg["id"]
        conv["updated_at"] = _now_ms()
        self._save_conversations()
        self._persist_message_artifacts(conversation_id, msg)
        return copy.deepcopy(msg)

    def get_message(self, conversation_id, message_id):
        conv = self._conversations.get(conversation_id)
        if conv is None:
            return None
        for msg in conv["messages"]:
            if msg["id"] == message_id:
                return copy.deepcopy(msg)
        return None

    def update_message(self, conversation_id, message_id, updates):
        conv = self._conversations.get(conversation_id)
        if conv is None:
            return None
        protected = {"id", "conversation_id", "created_at"}
        for msg in conv["messages"]:
            if msg["id"] == message_id:
                for key, value in updates.items():
                    if key not in protected:
                        msg[key] = value
                conv["updated_at"] = _now_ms()
                self._save_conversations()
                self._persist_message_artifacts(conversation_id, msg)
                return copy.deepcopy(msg)
        return None

    def delete_message(self, conversation_id, message_id):
        conv = self._conversations.get(conversation_id)
        if conv is None:
            return False
        target = None
        for msg in conv["messages"]:
            if msg["id"] == message_id:
                target = msg
                break
        if target is None:
            return False
        parent_id = target.get("parent_id")
        if parent_id is not None:
            for msg in conv["messages"]:
                if msg["id"] == parent_id:
                    if message_id in msg["children_ids"]:
                        msg["children_ids"].remove(message_id)
                    break
        conv["messages"] = [m for m in conv["messages"] if m["id"] != message_id]
        if conv["current_node_id"] == message_id:
            conv["current_node_id"] = parent_id
        conv["updated_at"] = _now_ms()
        self._save_conversations()
        return True

    # ----------------------------------------------------------
    # Message range / bulk operations (for summarize & trim)
    # ----------------------------------------------------------
    def get_messages_range(self, conversation_id, start_message_id, end_message_id):
        """start_message_id から end_message_id までの範囲のメッセージを返す。

        Returns:
            tuple(list[msg], int) — (範囲内メッセージのリスト, start のインデックス)
            None — start または end が見つからない場合
        """
        conv = self._conversations.get(conversation_id)
        if conv is None:
            return None
        messages = conv["messages"]
        start_idx = None
        end_idx = None
        for i, msg in enumerate(messages):
            if msg["id"] == start_message_id:
                start_idx = i
            if msg["id"] == end_message_id:
                end_idx = i
        if start_idx is None or end_idx is None:
            return None
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx
        range_msgs = messages[start_idx:end_idx + 1]
        return [copy.deepcopy(m) for m in range_msgs], start_idx

    def delete_messages_bulk(self, conversation_id, message_ids):
        """複数メッセージを一括削除する。parent_id / children_ids の整合性を維持。

        Returns:
            int — 削除されたメッセージ数
        """
        conv = self._conversations.get(conversation_id)
        if conv is None:
            return 0
        delete_set = set(message_ids)
        # 削除対象外メッセージの children_ids から削除対象を除去
        for msg in conv["messages"]:
            if msg["id"] not in delete_set:
                msg["children_ids"] = [
                    cid for cid in msg.get("children_ids", [])
                    if cid not in delete_set
                ]
        # 削除対象外メッセージの parent_id が削除対象を指す場合は None にする
        for msg in conv["messages"]:
            if msg["id"] not in delete_set:
                if msg.get("parent_id") in delete_set:
                    msg["parent_id"] = None
        original_count = len(conv["messages"])
        conv["messages"] = [m for m in conv["messages"] if m["id"] not in delete_set]
        deleted_count = original_count - len(conv["messages"])
        # current_node_id が削除対象の場合、残っているメッセージの最後に移動
        if conv["current_node_id"] in delete_set:
            if conv["messages"]:
                conv["current_node_id"] = conv["messages"][-1]["id"]
            else:
                conv["current_node_id"] = None
        conv["updated_at"] = _now_ms()
        self._save_conversations()
        return deleted_count

    def insert_message_at(self, conversation_id, message_dict, position_index,
                          parent_id=None, children_ids=None):
        """指定位置にメッセージを挿入し、parent_id / children_ids を接続する。

        Args:
            conversation_id: 会話ID
            message_dict: 挿入するメッセージ辞書
            position_index: 挿入位置（messagesリストのインデックス）
            parent_id: このメッセージの parent_id（明示指定）
            children_ids: このメッセージの children_ids（明示指定）

        Returns:
            挿入されたメッセージの deepcopy、または失敗時 None
        """
        conv = self._conversations.get(conversation_id)
        if conv is None:
            return None
        msg = copy.deepcopy(message_dict)
        if "id" not in msg or msg["id"] is None:
            msg["id"] = _gen_id()
        msg["conversation_id"] = conversation_id
        msg["parent_id"] = parent_id
        msg["children_ids"] = children_ids if children_ids is not None else []
        if "sequence_number" not in msg or msg["sequence_number"] is None:
            msg["sequence_number"] = position_index + 1
        if "created_at" not in msg or msg["created_at"] is None:
            msg["created_at"] = _now_ms()
        if "raw_text" not in msg or msg["raw_text"] is None:
            msg["raw_text"] = self._extract_raw_text(msg.get("content", []))
        for field in ("finish_reason", "usage", "widget"):
            if field not in msg:
                msg[field] = None
        # 親メッセージの children_ids にこのメッセージを追加
        if parent_id is not None:
            for m in conv["messages"]:
                if m["id"] == parent_id:
                    if msg["id"] not in m["children_ids"]:
                        m["children_ids"].append(msg["id"])
                    break
        # children のメッセージの parent_id をこのメッセージに更新
        if children_ids:
            for m in conv["messages"]:
                if m["id"] in children_ids:
                    m["parent_id"] = msg["id"]
        # 位置にクランプして挿入
        idx = max(0, min(position_index, len(conv["messages"])))
        conv["messages"].insert(idx, msg)
        # sequence_number を再採番
        for i, m in enumerate(conv["messages"]):
            m["sequence_number"] = i + 1
        conv["current_node_id"] = conv["messages"][-1]["id"]
        conv["updated_at"] = _now_ms()
        self._save_conversations()
        return copy.deepcopy(msg)

    # ----------------------------------------------------------
    # Search
    # ----------------------------------------------------------
    def search(self, query, conversation_id=None):
        results = []
        q_lower = query.lower()
        targets = {}
        if conversation_id is not None:
            conv = self._conversations.get(conversation_id)
            if conv is not None:
                targets[conversation_id] = conv
        else:
            targets = self._conversations
        for conv in targets.values():
            for msg in conv["messages"]:
                raw = msg.get("raw_text", "") or ""
                if q_lower in raw.lower():
                    results.append(copy.deepcopy(msg))
        return results

    # ----------------------------------------------------------
    # Branch
    # ----------------------------------------------------------
    def branch(self, conversation_id, message_id):
        conv = self._conversations.get(conversation_id)
        if conv is None:
            return None
        chain = self._get_chain(conv, message_id)
        if chain is None:
            return None
        new_conv = self.create_conversation(
            model=conv["model"],
            system_prompt_id=conv.get("system_prompt_id"),
            agent_id=conv.get("agent_id"),
            tags=list(conv.get("tags", [])),
        )
        new_conv_obj = self._conversations[new_conv["id"]]
        new_conv_obj["title"] = conv["title"] + " (branch)"
        old_to_new = {}
        for old_msg in chain:
            new_msg_id = _gen_id()
            old_to_new[old_msg["id"]] = new_msg_id
        prev_new_id = None
        for idx, old_msg in enumerate(chain):
            new_msg_id = old_to_new[old_msg["id"]]
            new_parent = None
            if old_msg["parent_id"] is not None and old_msg["parent_id"] in old_to_new:
                new_parent = old_to_new[old_msg["parent_id"]]
            new_msg = {
                "id": new_msg_id,
                "conversation_id": new_conv["id"],
                "parent_id": new_parent,
                "children_ids": [],
                "sequence_number": idx + 1,
                "role": old_msg["role"],
                "content": copy.deepcopy(old_msg.get("content", [])),
                "raw_text": old_msg.get("raw_text", ""),
                "created_at": old_msg.get("created_at", _now_ms()),
                "finish_reason": old_msg.get("finish_reason"),
                "usage": copy.deepcopy(old_msg.get("usage")),
                "widget": copy.deepcopy(old_msg.get("widget")),
            }
            if new_parent is not None:
                for m in new_conv_obj["messages"]:
                    if m["id"] == new_parent:
                        m["children_ids"].append(new_msg_id)
                        break
            new_conv_obj["messages"].append(new_msg)
            new_conv_obj["current_node_id"] = new_msg_id
            prev_new_id = new_msg_id
        new_conv_obj["updated_at"] = _now_ms()
        self._save_conversations()
        return copy.deepcopy(new_conv_obj)

    # ----------------------------------------------------------
    # Export
    # ----------------------------------------------------------
    def export_conversation(self, conversation_id, fmt="markdown"):
        conv = self._conversations.get(conversation_id)
        if conv is None:
            return None
        from domain.chat.exporter import export_markdown, export_json
        conv_copy = copy.deepcopy(conv)
        if fmt == "json":
            return export_json(conv_copy)
        return export_markdown(conv_copy)

    # ----------------------------------------------------------
    # Message chain helper
    # ----------------------------------------------------------
    def get_message_chain(self, conversation_id, up_to_message_id):
        conv = self._conversations.get(conversation_id)
        if conv is None:
            return []
        return self._get_chain(conv, up_to_message_id) or []

    def _get_chain(self, conv, message_id):
        msg_map = {m["id"]: m for m in conv["messages"]}
        if message_id not in msg_map:
            return None
        chain = []
        current_id = message_id
        while current_id is not None:
            msg = msg_map.get(current_id)
            if msg is None:
                break
            chain.append(copy.deepcopy(msg))
            current_id = msg.get("parent_id")
        chain.reverse()
        return chain

    # ----------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------
    @staticmethod
    def _extract_raw_text(content_blocks):
        parts = []
        if not isinstance(content_blocks, list):
            return str(content_blocks) if content_blocks else ""
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return " ".join(parts)

    @staticmethod
    def _normalize_conversation(conversation_id, conversation):
        conversation.setdefault("id", conversation_id)
        conversation.setdefault("title", "New Conversation")
        conversation.setdefault("created_at", _now_ms())
        conversation.setdefault("updated_at", conversation.get("created_at", _now_ms()))
        conversation.setdefault("model", _default_conversation_model())
        conversation.setdefault("system_prompt_id", None)
        conversation.setdefault("agent_id", None)
        conversation.setdefault("tags", [])
        conversation.setdefault("is_starred", False)
        conversation.setdefault("is_archived", False)
        conversation.setdefault("current_node_id", None)
        conversation.setdefault("parent_conversation_id", None)
        conversation.setdefault("child_conversation_ids", [])
        conversation.setdefault("conversation_kind", "subagent" if conversation.get("parent_conversation_id") else "chat")
        conversation.setdefault("group_id", None)
        conversation.setdefault("metadata", {})
        conversation.setdefault("messages", [])
        if not isinstance(conversation.get("child_conversation_ids"), list):
            conversation["child_conversation_ids"] = []
        if not isinstance(conversation.get("metadata"), dict):
            conversation["metadata"] = {}

    # ----------------------------------------------------------
    # Per-chat files / workspace artifacts
    # ----------------------------------------------------------
    def conversation_dir(self, conversation_id):
        return self._storage_path.parent / "conversations" / str(conversation_id)

    def conversation_workspace_dir(self, conversation_id):
        return self.conversation_dir(conversation_id) / "workspace"

    def persist_attachments(self, conversation_id, attachments):
        if not isinstance(attachments, list):
            return []
        refs = []
        attachment_dir = self.conversation_workspace_dir(conversation_id) / "attachments"
        attachment_dir.mkdir(parents=True, exist_ok=True)
        for index, attachment in enumerate(attachments):
            if not isinstance(attachment, dict):
                continue
            name = self._safe_filename(str(attachment.get("name") or f"attachment-{index + 1}"))
            path = attachment_dir / name
            suffix = 1
            while path.exists():
                path = attachment_dir / f"{Path(name).stem}-{suffix}{Path(name).suffix}"
                suffix += 1
            written = False
            data_url = attachment.get("dataUrl") or attachment.get("data_url")
            if isinstance(data_url, str) and data_url.startswith("data:") and "," in data_url:
                try:
                    path.write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
                    written = True
                except Exception:
                    written = False
            if not written and isinstance(attachment.get("content"), str):
                path.write_text(attachment["content"], encoding="utf-8")
                written = True
            if not written:
                path.write_text(json.dumps(self._attachment_manifest(attachment), ensure_ascii=False, indent=2), encoding="utf-8")
            refs.append(
                {
                    "id": attachment.get("id"),
                    "name": attachment.get("name") or name,
                    "size": attachment.get("size"),
                    "type": attachment.get("type"),
                    "source": attachment.get("source"),
                    "sourcePath": attachment.get("sourcePath"),
                    "workspace_path": str(path.relative_to(self.conversation_dir(conversation_id))),
                }
            )
        return refs

    def _save_conversation_files(self):
        for conversation_id, conversation in self._conversations.items():
            self._save_conversation_file(str(conversation_id), conversation)

    def _save_conversation_file(self, conversation_id, conversation):
        conversation_dir = self.conversation_dir(conversation_id)
        (conversation_dir / "workspace" / "attachments").mkdir(parents=True, exist_ok=True)
        (conversation_dir / "workspace" / "tools").mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "updated_at": _now_ms(),
            "conversation": conversation,
        }
        tmp_path = conversation_dir / "history.json.tmp"
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(conversation_dir / "history.json")

    def _persist_message_artifacts(self, conversation_id, msg):
        if not isinstance(msg, dict):
            return
        if msg.get("role") == "assistant" and isinstance(msg.get("tool_logs"), list) and msg["tool_logs"]:
            tool_dir = self.conversation_workspace_dir(conversation_id) / "tools"
            tool_dir.mkdir(parents=True, exist_ok=True)
            path = tool_dir / "{}-tool_logs.json".format(self._safe_filename(str(msg.get("id") or "message")))
            path.write_text(json.dumps(msg["tool_logs"], ensure_ascii=False, indent=2), encoding="utf-8")

    def _sanitize_inline_thought_messages(self, conversation):
        for msg in conversation.get("messages", []) if isinstance(conversation.get("messages"), list) else []:
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            thoughts = []
            for block in msg.get("content", []) if isinstance(msg.get("content"), list) else []:
                if not isinstance(block, dict) or block.get("type") != "text":
                    continue
                text = str(block.get("text") or "")

                def collect(match):
                    value = str(match.group(1) or "").strip()
                    if value:
                        thoughts.append(value)
                    return ""

                cleaned = re.sub(r"<thought>(.*?)</thought>", collect, text, flags=re.DOTALL).strip()
                if cleaned != text:
                    block["text"] = cleaned
            if thoughts:
                metadata = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}
                thinking = metadata.get("thinking") if isinstance(metadata.get("thinking"), dict) else {}
                metadata["thinking"] = {
                    **thinking,
                    "state": "completed",
                    "transcript": "\n\n".join(thoughts),
                    "source": "google_inline_thought",
                }
                msg["metadata"] = metadata
                msg["raw_text"] = self._extract_raw_text(msg.get("content", []))

    @staticmethod
    def _safe_filename(name):
        cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .")
        return cleaned[:160] or "attachment"

    @staticmethod
    def _attachment_manifest(attachment):
        return {
            key: attachment.get(key)
            for key in ("id", "name", "size", "type", "truncated", "source", "sourcePath")
            if isinstance(attachment, dict) and key in attachment
        }
