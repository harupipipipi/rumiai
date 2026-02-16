from __future__ import annotations

from typing import Any, Dict, Optional


def run(context: Dict[str, Any]) -> None:
    ir = context.get("interface_registry")
    if not ir:
        return

    def bind_http(app, kernel, ctx: Optional[Dict[str, Any]] = None) -> None:
        from flask import request, jsonify

        # foundationからsafe_add_url_ruleを取得
        safe_add = kernel.interface_registry.get("foundation.safe_add_url_rule", strategy="last")
        if not callable(safe_add):
            # フォールバック実装
            _registered = set()

            def safe_add(app, rule, endpoint, view_func, methods):
                if endpoint in _registered:
                    return False
                if endpoint in getattr(app, "view_functions", {}):
                    return False
                try:
                    app.add_url_rule(rule, endpoint, view_func, methods=list(methods))
                    _registered.add(endpoint)
                    return True
                except Exception:
                    return False

        def chats():
            return kernel.interface_registry.get("service.chats", strategy="last")

        def rels():
            return kernel.interface_registry.get("service.relationships", strategy="last")

        def settings_mgr():
            return kernel.interface_registry.get("service.settings_manager", strategy="last")

        # ========================================
        # Diagnostics
        # ========================================
        def api_diagnostics():
            return jsonify(kernel.diagnostics.as_dict())

        safe_add(app, "/api/diagnostics", "io_http_api.diagnostics", api_diagnostics, {"GET"})
        safe_add(app, "/api/kernel/diagnostics", "io_http_api.kernel_diagnostics", api_diagnostics, {"GET"})

        # ========================================
        # Message API (new)
        # ========================================
        def api_message():
            payload = request.get_json(silent=True) or {}
            chat_id = payload.get("chat_id") or request.args.get("chat_id")
            if not chat_id:
                return jsonify({"success": False, "error": "missing chat_id"}), 400
            fn = kernel.interface_registry.get("message.handle", strategy="last")
            if not callable(fn):
                return jsonify({"success": False, "error": "message.handle not provided"}), 500
            result = fn(chat_id, payload)
            return jsonify(result)

        safe_add(app, "/api/message", "io_http_api.message", api_message, {"POST"})

        def api_message_stream():
            payload = request.get_json(silent=True) or {}
            chat_id = payload.get("chat_id") or request.args.get("chat_id")
            if not chat_id:
                return jsonify({"success": False, "error": "missing chat_id"}), 400
            fn = kernel.interface_registry.get("message.handle_stream", strategy="last")
            if not callable(fn):
                return jsonify({"success": False, "error": "message.handle_stream not provided"}), 500
            return fn(chat_id, payload)

        safe_add(app, "/api/message/stream", "io_http_api.message_stream", api_message_stream, {"POST"})

        # ========================================
        # Legacy Message Endpoints
        # ========================================
        def legacy_send_message(chat_id: str):
            payload = request.get_json(silent=True) or {}
            payload["streaming"] = False
            fn = kernel.interface_registry.get("message.handle", strategy="last")
            if not callable(fn):
                return jsonify({"success": False, "error": "message.handle missing"}), 500
            result = fn(chat_id, payload)
            return jsonify(result)

        safe_add(app, "/api/chats/<chat_id>/send_message", "io_http_api.legacy_send_message", legacy_send_message, {"POST"})

        def legacy_send_message_stream(chat_id: str):
            payload = request.get_json(silent=True) or {}
            payload["streaming"] = True
            fn = kernel.interface_registry.get("message.handle_stream", strategy="last")
            if not callable(fn):
                return jsonify({"success": False, "error": "message.handle_stream missing"}), 500
            return fn(chat_id, payload)

        safe_add(app, "/api/chats/<chat_id>/send_message_stream", "io_http_api.legacy_send_message_stream", legacy_send_message_stream, {"POST"})

        def legacy_abort():
            fn = kernel.interface_registry.get("message.abort", strategy="last")
            if callable(fn):
                return jsonify(fn())
            return jsonify({"success": False, "error": "message.abort missing"}), 500

        safe_add(app, "/api/stream/abort", "io_http_api.legacy_abort", legacy_abort, {"POST"})

        # ========================================
        # User Settings
        # ========================================
        def user_settings():
            sm = settings_mgr()
            if sm is None:
                return jsonify({"error": "settings service not available"}), 503
            if request.method == "GET":
                return jsonify(sm.get_user_settings())
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                data = {}
            sm.save_user_settings(data)
            return jsonify({"success": True})

        safe_add(app, "/api/user/settings", "io_http_api.user_settings", user_settings, {"GET", "POST"})

        # ========================================
        # Folders
        # ========================================
        def create_folder():
            cm = chats()
            if cm is None:
                return jsonify({"error": "chats service not available"}), 503
            data = request.get_json(silent=True) or {}
            name = (data.get("name") or "").strip()
            try:
                folder = cm.create_folder(name)
                return jsonify({"success": True, "folder_name": folder}), 201
            except Exception as e:
                return jsonify({"success": False, "error": str(e)}), 400

        safe_add(app, "/api/folders", "io_http_api.create_folder", create_folder, {"POST"})

        # ========================================
        # Chats CRUD
        # ========================================
        def chats_list():
            cm = chats()
            if cm is None:
                return jsonify({"pinned": [], "folders": {}, "uncategorized": []})
            return jsonify(cm.get_all_chats())

        safe_add(app, "/api/chats", "io_http_api.chats_list", chats_list, {"GET"})

        def chats_create():
            cm = chats()
            if cm is None:
                return jsonify({"error": "chats service not available"}), 503
            data = request.get_json(silent=True) or {}
            meta = cm.create_chat(data.get("folder", None))
            return jsonify(meta), 201

        safe_add(app, "/api/chats", "io_http_api.chats_create", chats_create, {"POST"})

        def chat_single(chat_id: str):
            cm = chats()
            rm = rels()
            if cm is None:
                return jsonify({"error": "chats service not available"}), 503
            if request.method == "GET":
                try:
                    return jsonify(cm.load_chat_history(chat_id))
                except FileNotFoundError:
                    return jsonify({
                        "conversation_id": chat_id,
                        "title": "新しいチャット",
                        "schema_version": "2.0",
                        "messages": [],
                        "mapping": {},
                        "current_node": None,
                        "is_pinned": False,
                        "folder": None
                    })
            if request.method == "DELETE":
                try:
                    if rm is not None:
                        rm.delete_all_links_for(chat_id)
                    cm.delete_chat(chat_id)
                    return jsonify({"success": True})
                except FileNotFoundError:
                    return jsonify({"error": "Chat not found"}), 404
            # PATCH
            metadata = request.get_json(silent=True) or {}
            try:
                cm.update_chat_metadata(chat_id, metadata)
                return jsonify({"success": True})
            except FileNotFoundError:
                return jsonify({"error": "Chat not found"}), 404

        safe_add(app, "/api/chats/<chat_id>", "io_http_api.chat_single", chat_single, {"GET", "DELETE", "PATCH"})

        def chat_copy(chat_id: str):
            cm = chats()
            if cm is None:
                return jsonify({"error": "chats service not available"}), 503
            try:
                new_id = cm.copy_chat(chat_id)
                return jsonify({"success": True, "new_chat_id": new_id}), 201
            except FileNotFoundError:
                return jsonify({"error": "Chat not found"}), 404

        safe_add(app, "/api/chats/<chat_id>/copy", "io_http_api.chat_copy", chat_copy, {"POST"})

        # ========================================
        # Chat Config
        # ========================================
        def chat_config(chat_id: str):
            cm = chats()
            if cm is None:
                return jsonify({"error": "chats service not available"}), 503
            if request.method == "GET":
                config = cm.load_chat_config(chat_id)
                return jsonify(config)
            # PATCH
            updates = request.get_json(silent=True) or {}
            config = cm.update_chat_config(chat_id, updates)
            return jsonify({"success": True, "config": config})

        safe_add(app, "/api/chats/<chat_id>/config", "io_http_api.chat_config", chat_config, {"GET", "PATCH"})

        # ========================================
        # UI History
        # ========================================
        def ui_history(chat_id: str):
            cm = chats()
            if cm is None:
                return jsonify({"tool_logs": [], "ui_state": {}})
            return jsonify(cm.load_ui_history(chat_id))

        safe_add(app, "/api/chats/<chat_id>/ui_history", "io_http_api.ui_history", ui_history, {"GET"})

        def ui_history_logs(chat_id: str):
            cm = chats()
            if cm is None:
                return jsonify({"logs": []})
            exec_id = request.args.get("execution_id")
            if exec_id:
                logs = cm.get_tool_logs_for_execution(chat_id, exec_id)
            else:
                ui = cm.load_ui_history(chat_id)
                logs = ui.get("tool_logs", [])
            return jsonify({"logs": logs})

        safe_add(app, "/api/chats/<chat_id>/ui_history/logs", "io_http_api.ui_history_logs", ui_history_logs, {"GET"})

        def ui_history_append(chat_id: str):
            cm = chats()
            if cm is None:
                return jsonify({"error": "chats service not available"}), 503
            log = request.get_json(silent=True) or {}
            mid = cm.append_tool_log(chat_id, log)
            return jsonify({"success": True, "message_id": mid})

        safe_add(app, "/api/chats/<chat_id>/ui_history/append_log", "io_http_api.ui_history_append", ui_history_append, {"POST"})

        def ui_state(chat_id: str):
            cm = chats()
            if cm is None:
                return jsonify({"ui_state": {}})
            if request.method == "GET":
                ui = cm.load_ui_history(chat_id)
                return jsonify({"ui_state": ui.get("ui_state", {})})
            # POST
            updates = request.get_json(silent=True) or {}
            for k, v in updates.items():
                cm.update_ui_state(chat_id, k, v)
            return jsonify({"success": True})

        safe_add(app, "/api/chats/<chat_id>/ui_history/state", "io_http_api.ui_state", ui_state, {"GET", "POST"})

        def ui_history_clear(chat_id: str):
            cm = chats()
            if cm is None:
                return jsonify({"error": "chats service not available"}), 503
            cm.clear_ui_history(chat_id)
            return jsonify({"success": True})

        safe_add(app, "/api/chats/<chat_id>/ui_history/clear", "io_http_api.ui_history_clear", ui_history_clear, {"DELETE"})

        # ========================================
        # Relationships
        # ========================================
        def relationships():
            rm = rels()
            if rm is None:
                return jsonify({"error": "relationships service not available"}), 503
            if request.method == "GET":
                entity_id = request.args.get("entity_id")
                link_type = request.args.get("type")
                direction = request.args.get("direction", "both")
                if entity_id:
                    links = rm.get_related(entity_id, link_type, direction)
                else:
                    links = rm.get_all_links()
                return jsonify({"links": links})
            # POST
            data = request.get_json(silent=True) or {}
            for f in ("source", "target", "type"):
                if f not in data:
                    return jsonify({"error": f"{f} is required"}), 400
            link = rm.link(data["source"], data["target"], data["type"], data.get("metadata", {}))
            return jsonify({"success": True, "link": link}), 201

        safe_add(app, "/api/relationships", "io_http_api.relationships", relationships, {"GET", "POST"})

        def relationships_entity(entity_id: str):
            rm = rels()
            if rm is None:
                return jsonify({"error": "relationships service not available"}), 503
            if request.method == "GET":
                link_type = request.args.get("type")
                direction = request.args.get("direction", "both")
                links = rm.get_related(entity_id, link_type, direction)
                ids = rm.get_related_ids(entity_id, link_type, direction)
                return jsonify({"entity_id": entity_id, "links": links, "related_ids": ids})
            # DELETE
            data = request.get_json(silent=True) or {}
            target = data.get("target")
            link_type = data.get("type")
            if target and link_type:
                ok = rm.unlink(entity_id, target, link_type)
                return jsonify({"success": ok}), (200 if ok else 404)
            count = rm.delete_all_links_for(entity_id)
            return jsonify({"success": True, "deleted_count": count})

        safe_add(app, "/api/relationships/<entity_id>", "io_http_api.relationships_entity", relationships_entity, {"GET", "DELETE"})

        # ========================================
        # Ecosystem Admin
        # ========================================
        def ecosystem_status():
            try:
                from backend_core.ecosystem.compat import is_ecosystem_initialized
                from backend_core.ecosystem import get_registry, get_active_ecosystem_manager
                if not is_ecosystem_initialized():
                    return jsonify({"initialized": False})
                reg = get_registry()
                active = get_active_ecosystem_manager()
                return jsonify({
                    "initialized": True,
                    "active_pack_identity": active.active_pack_identity,
                    "packs": list(reg.packs.keys()),
                    "total_components": len(reg.get_all_components()),
                    "overrides": active.get_all_overrides(),
                })
            except Exception as e:
                return jsonify({"initialized": False, "error": str(e)})

        safe_add(app, "/api/ecosystem/status", "io_http_api.ecosystem_status", ecosystem_status, {"GET"})

        # ========================================
        # Stubs for removed subsystems
        # ========================================
        def not_impl(name: str):
            return jsonify({"success": False, "error": f"{name} subsystem not installed"}), 501

        safe_add(app, "/api/prompts", "io_http_api.prompts_stub", lambda: not_impl("prompt"), {"GET"})
        safe_add(app, "/api/ai/models", "io_http_api.ai_stub", lambda: not_impl("ai_client"), {"GET"})
        safe_add(app, "/api/tools/debug", "io_http_api.tools_stub", lambda: not_impl("tool"), {"GET"})

    # InterfaceRegistryにbinderを登録
    ir.register("io.http.binders", bind_http, meta={"component": "io_http_api_v1"})
