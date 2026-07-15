import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from blocks._common import ok, error
from domain.ai_client.client import AIClient
from domain.ai_client.model_router import ModelRouter


def run(input_data, context):
    """プロファイル CRUD。

    HTTP メソッドは input_data["_method"] で判定する。
    transport/http.py が path_inject と同様に _method を注入する想定。

    GET (一覧):
        input_data: {} or {"_method": "GET"}
        Returns: ok({"profiles": [...]})

    POST (作成):
        input_data: {
            "_method": "POST",
            "key": str,
            "profile": dict
        }
        Returns: ok({"key": str, "profile": dict})

    PUT (更新):
        input_data: {
            "_method": "PUT",
            "name": str,  # path_inject で注入される
            "updates": dict
        }
        Returns: ok({"key": str, "profile": dict})

    DELETE (削除):
        input_data: {
            "_method": "DELETE",
            "name": str,  # path_inject で注入される
        }
        Returns: ok({"deleted": str})
    """
    client = AIClient()
    router = ModelRouter(client)
    pm = router.profile_manager

    method = input_data.get("_method", "GET").upper()

    if method == "GET":
        profiles = pm.list_profiles()
        return ok({"profiles": profiles})

    elif method == "POST":
        key = input_data.get("key")
        profile_data = input_data.get("profile")
        if not key:
            return error("key is required", "MISSING_PARAM")
        if not profile_data or not isinstance(profile_data, dict):
            return error("profile dict is required", "MISSING_PARAM")
        # 必須フィールド検証
        required_fields = ["name", "provider", "model_id"]
        for field in required_fields:
            if field not in profile_data:
                return error("profile.{} is required".format(field), "MISSING_PARAM")
        # デフォルト値設定
        profile_data.setdefault("traits", [])
        profile_data.setdefault("cost", 5)
        profile_data.setdefault("speed", 5)
        profile_data.setdefault("quality", 5)
        profile_data.setdefault("context_window", 128000)
        profile_data.setdefault("strengths", ["general"])
        pm.add_custom_profile(key, profile_data)
        return ok({"key": key, "profile": profile_data})

    elif method == "PUT":
        key = input_data.get("name")
        if not key:
            return error("profile name (path parameter) is required", "MISSING_PARAM")
        updates = input_data.get("updates")
        if not updates or not isinstance(updates, dict):
            return error("updates dict is required", "MISSING_PARAM")
        existing = pm.get_profile(key)
        if existing is None:
            return error("Profile '{}' not found".format(key), "NOT_FOUND")
        pm.update_custom_profile(key, updates)
        updated = pm.get_profile(key)
        return ok({"key": key, "profile": updated})

    elif method == "DELETE":
        key = input_data.get("name")
        if not key:
            return error("profile name (path parameter) is required", "MISSING_PARAM")
        pm.remove_custom_profile(key)
        return ok({"deleted": key})

    else:
        return error("Unsupported method: {}".format(method), "INVALID_METHOD")
