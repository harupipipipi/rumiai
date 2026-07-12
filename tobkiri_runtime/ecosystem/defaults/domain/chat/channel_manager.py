"""
domain/chat/channel_manager.py — Slack-style channel management.

Singleton manager for channels. In-memory store with JSON file persistence.
Does NOT modify ChatStore.
"""

import copy
import json
import os
import threading
import time
import uuid


def _gen_id():
    return str(uuid.uuid4())


def _now_ms():
    return int(time.time() * 1000)


CHANNEL_TYPES = ("public", "private", "direct")

_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "..", "..", ".data", "channels")


class ChannelManager:
    """Singleton channel manager with in-memory + JSON persistence."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._channels = {}
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._load_from_disk()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _ensure_persist_dir(self):
        os.makedirs(_PERSIST_DIR, exist_ok=True)

    def _persist_channel(self, channel):
        """Write a single channel dict to disk as JSON."""
        self._ensure_persist_dir()
        path = os.path.join(_PERSIST_DIR, channel["id"] + ".json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(channel, fh, ensure_ascii=False, indent=2)

    def _delete_channel_file(self, channel_id):
        path = os.path.join(_PERSIST_DIR, channel_id + ".json")
        if os.path.exists(path):
            os.remove(path)

    def _load_from_disk(self):
        """Load all channel JSON files from disk into memory."""
        if not os.path.isdir(_PERSIST_DIR):
            return
        for fname in os.listdir(_PERSIST_DIR):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(_PERSIST_DIR, fname)
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    ch = json.load(fh)
                if isinstance(ch, dict) and "id" in ch:
                    self._channels[ch["id"]] = ch
            except (json.JSONDecodeError, OSError):
                continue

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create_channel(self, name, channel_type="public", description="",
                       created_by=None, members=None):
        """Create a new channel and return its deep copy."""
        if channel_type not in CHANNEL_TYPES:
            return None, "channel_type must be one of: " + ", ".join(CHANNEL_TYPES)
        if not name or not isinstance(name, str):
            return None, "name is required and must be a non-empty string"
        if channel_type == "direct":
            if not members or len(members) != 2:
                return None, "direct channels require exactly 2 members"
            existing = self._find_direct_channel(members[0], members[1])
            if existing is not None:
                return copy.deepcopy(existing), None

        cid = _gen_id()
        now = _now_ms()
        initial_members = list(members) if members else []
        if created_by and created_by not in initial_members:
            initial_members.insert(0, created_by)

        channel = {
            "id": cid,
            "name": name,
            "description": description,
            "channel_type": channel_type,
            "created_by": created_by,
            "members": initial_members,
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            self._channels[cid] = channel
            self._persist_channel(channel)
        return copy.deepcopy(channel), None

    def get_channel(self, channel_id):
        ch = self._channels.get(channel_id)
        if ch is None:
            return None
        return copy.deepcopy(ch)

    def list_channels(self, channel_type=None, member_id=None, limit=50, offset=0):
        results = []
        for ch in self._channels.values():
            if channel_type and ch["channel_type"] != channel_type:
                continue
            if member_id and member_id not in ch["members"]:
                continue
            results.append(ch)
        results.sort(key=lambda c: c["updated_at"], reverse=True)
        total = len(results)
        page = results[offset: offset + limit]
        return [copy.deepcopy(c) for c in page], total

    def update_channel(self, channel_id, updates):
        with self._lock:
            ch = self._channels.get(channel_id)
            if ch is None:
                return None, "channel not found"
            protected = {"id", "created_at", "created_by", "channel_type"}
            for key, value in updates.items():
                if key not in protected:
                    ch[key] = value
            ch["updated_at"] = _now_ms()
            self._persist_channel(ch)
        return copy.deepcopy(ch), None

    def delete_channel(self, channel_id):
        with self._lock:
            if channel_id not in self._channels:
                return False
            del self._channels[channel_id]
            self._delete_channel_file(channel_id)
        return True

    # ------------------------------------------------------------------
    # Member management
    # ------------------------------------------------------------------

    def add_member(self, channel_id, member_id):
        with self._lock:
            ch = self._channels.get(channel_id)
            if ch is None:
                return None, "channel not found"
            if member_id in ch["members"]:
                return copy.deepcopy(ch), None
            ch["members"].append(member_id)
            ch["updated_at"] = _now_ms()
            self._persist_channel(ch)
        return copy.deepcopy(ch), None

    def remove_member(self, channel_id, member_id):
        with self._lock:
            ch = self._channels.get(channel_id)
            if ch is None:
                return None, "channel not found"
            if member_id not in ch["members"]:
                return None, "member not in channel"
            ch["members"].remove(member_id)
            ch["updated_at"] = _now_ms()
            self._persist_channel(ch)
        return copy.deepcopy(ch), None

    def get_members(self, channel_id):
        ch = self._channels.get(channel_id)
        if ch is None:
            return None
        return list(ch["members"])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_direct_channel(self, member_a, member_b):
        """Return existing direct channel between two members, or None."""
        pair = {member_a, member_b}
        for ch in self._channels.values():
            if ch["channel_type"] == "direct" and set(ch["members"]) == pair:
                return ch
        return None

    def touch_channel(self, channel_id):
        """Update the updated_at timestamp without changing other fields."""
        with self._lock:
            ch = self._channels.get(channel_id)
            if ch is not None:
                ch["updated_at"] = _now_ms()
                self._persist_channel(ch)
