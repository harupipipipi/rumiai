from __future__ import annotations

from typing import Any, Dict, Optional
from rumi_foundation.http.routes import safe_add_url_rule

def run(context: Dict[str, Any]) -> None:
    ir = context.get("interface_registry")
    if not ir:
        return

    def bind_http(app, kernel, ctx: Optional[Dict[str, Any]] = None) -> None:
        from flask import request, jsonify

        def chats():
            return kernel.interface_registry.get("service.chats", strategy="last")

        def rels():
            return kernel.interface_registry.get("service.relationships", strategy="last")

        # diagnostics
        safe_add_url_rule(app, "/api/diagnostics", "io_http_api.diagnostics", lambda: jsonify(kernel.diagnostics.as_dict()), {"GET"})
        safe_add_url_rule(app, "/api/kernel/diagnostics", "io_http_api.kernel_diagnostics", lambda: jsonify(kernel.diagnostics.as_dict()), {"GET"})

        # message (new)
        def api_message():
            payload = request.get_json(silent=True) or {}
            chat_id = payload.get("chat_id") or request.args.get("chat_id")
            if not chat_id:
                return jsonify({"success": False, "error": "missing chat_id"}), 400
            fn = kernel.interface_registry.get("message.handle", strategy="last")
            if not callable(fn):
                return jsonify({"success": False, "error": "message.handle not provided"}), 500
            return jsonify(fn(chat_id, payload))
        safe_add_url_rule(app, "/api/message", "io_http_api.message", api_message, {"POST"})

        def api_message_stream():
            payload = request.get_json(silent=True) or {}
            chat_id = payload.get("chat_id") or request.args.get("chat_id")
            if not chat_id:
                return jsonify({"success": False, "error": "missing chat_id"}), 400
            fn = kernel.interface_registry.get("message.handle_stream", strategy="last")
            if not callable(fn):
                return jsonify({"success": False, "error": "message.handle_stream not provided"}), 500
            return fn(chat_id, payload)
        safe_add_url_rule(app, "/api/message/stream", "io_http_api.message_stream", api_message_stream, {"POST"})

        # legacy message endpoints
        def legacy_send_message(chat_id: str):
            payload = request.get_json(silent=True) or {}
            payload["streaming"] = False
            fn = kernel.interface_registry.get("message.handle", strategy="last")
            if not callable(fn):
                return jsonify({"success": False, "error": "message.handle missing"}), 500
            return jsonify(fn(chat_id, payload))
        safe_add_url_rule(app, "/api/chats/<chat_id>/send_message", "io_http_api.legacy_send_message", legacy_send_message, {"POST"})

        def legacy_send_message_stream(chat_id: str):
            payload = request.get_json(silent=True) or {}
            payload["streaming"] = True
            fn = kernel.interface_registry.get("message.handle_stream", strategy="last")
            if not callable(fn):
                return jsonify({"success": False, "error": "message.handle_stream missing"}), 500
            return fn(chat_id, payload)
        safe_add_url_rule(app, "/api/chats/<chat_id>/send_message_stream", "io_http_api.legacy_send_message_stream", legacy_send_message_stream, {"POST"})

        def legacy_abort():
            fn = kernel.interface_registry.get("message.abort", strategy="last")
            return jsonify(fn()) if callable(fn) else (jsonify({"success": False, "error": "message.abort missing"}), 500)
        safe_add_url_rule(app, "/api/stream/abort", "io_http_api.legacy_abort", legacy_abort, {"POST"})

        # user settings
        def user_settings():
            from settings_manager import SettingsManager
            sm = SettingsManager()
            if request.method == "GET":
                return jsonify(sm.get_user_settings())
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                data = {}
            sm.save_user_settings(data)
            return jsonify({"success": True})
        safe_add_url_rule(app, "/api/user/settings", "io_http_api.user_settings", user_settings, {"GET", "POST"})

        # folders + chats CRUD
        def create_folder():
            data = request.get_json(silent=True) or {}
            name = (data.get("name") or "").strip()
            try:
                folder = chats().create_folder(name)
                return jsonify({"success": True, "folder_name": folder}), 201
            except Exception as e:
                return jsonify({"success": False, "error": str(e)}), 400
        safe_add_url_rule(app, "/api/folders", "io_http_api.create_folder", create_folder, {"POST"})

        safe_add_url_rule(app, "/api/chats", "io_http_api.chats_list", lambda: jsonify(chats().get_all_chats()), {"GET"})

        def chats_create():
            data = request.get_json(silent=True) or {}
            meta = chats().create_chat(data.get("folder", None))
            return jsonify(meta), 201
        safe_add_url_rule(app, "/api/chats", "io_http_api.chats_create", chats_create, {"POST"})

        def chat_single(chat_id: str):
            cm = chats()
            if request.method == "GET":
                try:
                    return jsonify(cm.load_chat_history(chat_id))
                except FileNotFoundError:
                    return jsonify({"metadata": {"title": "新しいチャット", "is_pinned": False, "folder": None}, "messages": []})
            if request.method == "DELETE":
                try:
                    rels().delete_all_links_for(chat_id)
                    cm.delete_chat(chat_id)
                    return jsonify({"success": True})
                except FileNotFoundError:
                    return jsonify({"error": "Chat not found"}), 404
            cm.update_chat_metadata(chat_id, request.get_json(silent=True) or {})
            return jsonify({"success": True})
        safe_add_url_rule(app, "/api/chats/<chat_id>", "io_http_api.chat_single", chat_single, {"GET", "DELETE", "PATCH"})

        def chat_copy(chat_id: str):
            new_id = chats().copy_chat(chat_id)
            return jsonify({"success": True, "new_chat_id": new_id}), 201
        safe_add_url_rule(app, "/api/chats/<chat_id>/copy", "io_http_api.chat_copy", chat_copy, {"POST"})

        # ui_history
        safe_add_url_rule(app, "/api/chats/<chat_id>/ui_history", "io_http_api.ui_history", lambda chat_id: jsonify(chats().load_ui_history(chat_id)), {"GET"})

        def ui_history_logs(chat_id: str):
            exec_id = request.args.get("execution_id")
            cm = chats()
            ui = cm.load_ui_history(chat_id)
            logs = cm.get_tool_logs_for_execution(chat_id, exec_id) if exec_id else ui.get("tool_logs", [])
            return jsonify({"logs": logs})
        safe_add_url_rule(app, "/api/chats/<chat_id>/ui_history/logs", "io_http_api.ui_history_logs", ui_history_logs, {"GET"})

        def ui_history_append(chat_id: str):
            log = request.get_json(silent=True) or {}
            mid = chats().append_tool_log(chat_id, log)
            return jsonify({"success": True, "message_id": mid})
        safe_add_url_rule(app, "/api/chats/<chat_id>/ui_history/append_log", "io_http_api.ui_history_append", ui_history_append, {"POST"})

        def ui_state(chat_id: str):
            cm = chats()
            if request.method == "GET":
                ui = cm.load_ui_history(chat_id)
                return jsonify({"ui_state": ui.get("ui_state", {})})
            updates = request.get_json(silent=True) or {}
            for k, v in updates.items():
                cm.update_ui_state(chat_id, k, v)
            return jsonify({"success": True})
        safe_add_url_rule(app, "/api/chats/<chat_id>/ui_history/state", "io_http_api.ui_state", ui_state, {"GET", "POST"})

        def ui_history_clear(chat_id: str):
            chats().clear_ui_history(chat_id)
            return jsonify({"success": True})
        safe_add_url_rule(app, "/api/chats/<chat_id>/ui_history/clear", "io_http_api.ui_history_clear", ui_history_clear, {"DELETE"})

        # relationships
        def relationships():
            rm = rels()
            if request.method == "GET":
                entity_id = request.args.get("entity_id")
                link_type = request.args.get("type")
                direction = request.args.get("direction", "both")
                links = rm.get_related(entity_id, link_type, direction) if entity_id else rm.get_all_links()
                return jsonify({"links": links})
            data = request.get_json(silent=True) or {}
            for f in ("source", "target", "type"):
                if f not in data:
                    return jsonify({"error": f"{f} is required"}), 400
            link = rm.link(data["source"], data["target"], data["type"], data.get("metadata", {}))
            return jsonify({"success": True, "link": link}), 201
        safe_add_url_rule(app, "/api/relationships", "io_http_api.relationships", relationships, {"GET", "POST"})

        def relationships_entity(entity_id: str):
            rm = rels()
            if request.method == "GET":
                link_type = request.args.get("type")
                direction = request.args.get("direction", "both")
                links = rm.get_related(entity_id, link_type, direction)
                ids = rm.get_related_ids(entity_id, link_type, direction)
                return jsonify({"entity_id": entity_id, "links": links, "related_ids": ids})
            data = request.get_json(silent=True) or {}
            target = data.get("target")
            link_type = data.get("type")
            if target and link_type:
                ok = rm.unlink(entity_id, target, link_type)
                return jsonify({"success": ok}), (200 if ok else 404)
            count = rm.delete_all_links_for(entity_id)
            return jsonify({"success": True, "deleted_count": count})
        safe_add_url_rule(app, "/api/relationships/<entity_id>", "io_http_api.relationships_entity", relationships_entity, {"GET", "DELETE"})

        # ecosystem admin (minimal)
        def ecosystem_status():
            from backend_core.ecosystem.compat import is_ecosystem_initialized
            from backend_core.ecosystem import get_registry, get_active_ecosystem_manager
            if not is_ecosystem_initialized():
                return jsonify({"initialized": False, "message": "エコシステムは初期化されていません"})
            reg = get_registry()
            active = get_active_ecosystem_manager()
            return jsonify({
                "initialized": True,
                "active_pack_identity": active.active_pack_identity,
                "packs": list(reg.packs.keys()),
                "total_components": len(reg.get_all_components()),
                "overrides": active.get_all_overrides(),
            })
        safe_add_url_rule(app, "/api/ecosystem/status", "io_http_api.ecosystem_status", ecosystem_status, {"GET"})

        # removed subsystems stubs (explicit)
        def not_impl(name: str):
            return jsonify({"success": False, "error": f"{name} subsystem removed; implement as ecosystem components."}), 501

        safe_add_url_rule(app, "/api/prompts", "io_http_api.prompts_stub", lambda: not_impl("prompt"), {"GET"})
        safe_add_url_rule(app, "/api/ai/models", "io_http_api.ai_stub", lambda: not_impl("ai_client"), {"GET"})
        safe_add_url_rule(app, "/api/tools/debug", "io_http_api.tools_stub", lambda: not_impl("tool"), {"GET"})

    ir.register("io.http.binders", bind_http, meta={"component": "io_http_api_v1"})
