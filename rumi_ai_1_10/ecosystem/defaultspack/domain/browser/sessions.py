from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ._utils import default_browser_root, now_iso, read_json, safe_int, sanitize_id, write_json
from .cdp import CdpClient
from .policy import BrowserArtifactStore, computer_use_fallback_contract
from .profiles import BrowserProfileManager
from .snapshots import SnapshotRefStore


class BrowserSessionManager:
    """Coordinates managed Chromium sessions and CDP tab operations."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        profile_manager: BrowserProfileManager | None = None,
        cdp_client_factory: Any | None = None,
        process_factory: Any | None = None,
        browser_executable: str | Path | None = None,
    ) -> None:
        self.root = Path(root) if root is not None else default_browser_root()
        self.session_path = self.root / "sessions.json"
        self.profile_manager = profile_manager or BrowserProfileManager(self.root)
        self.snapshot_store = SnapshotRefStore(self.root)
        self.artifact_store = BrowserArtifactStore(self.root / "artifacts")
        self._cdp_client_factory = cdp_client_factory
        self._process_factory = process_factory or subprocess.Popen
        self._browser_executable = Path(browser_executable) if browser_executable is not None else None
        self._processes: dict[str, Any] = {}

    def list_sessions(self) -> list[dict[str, Any]]:
        state = self._load_state()
        sessions = state.get("sessions") if isinstance(state.get("sessions"), dict) else {}
        return [dict(record) for _, record in sorted(sessions.items()) if isinstance(record, dict)]

    def start_session(
        self,
        *,
        session_id: str | None = None,
        profile_id: str | None = None,
        url: str | None = None,
        debugging_port: int | None = None,
        launch: bool = True,
        extra_args: list[str] | None = None,
    ) -> dict[str, Any]:
        profile = self.profile_manager.ensure_profile(profile_id or "default", set_active=False)
        session_id = sanitize_id(session_id or "session-{}".format(profile["id"]))
        port = int(debugging_port or self._default_port(session_id))
        endpoint = {"host": "127.0.0.1", "port": port, "url": "http://127.0.0.1:{}".format(port)}
        command = self._launch_command(profile, port=port, url=url, extra_args=extra_args or [])
        now = now_iso()
        record: dict[str, Any] = {
            "id": session_id,
            "profile_id": profile["id"],
            "state": "running",
            "managed": bool(launch),
            "endpoint": endpoint,
            "debugging_port": port,
            "target_url": url,
            "command": command,
            "pid": None,
            "started_at": now,
            "updated_at": now,
        }
        if launch:
            executable = Path(command[0]) if command else None
            if executable is None or not executable.exists():
                record.update(
                    {
                        "state": "unavailable",
                        "managed": False,
                        "reason": "no_supported_browser_found",
                    }
                )
            else:
                process = self._process_factory(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self._processes[session_id] = process
                record["pid"] = getattr(process, "pid", None)
        else:
            record["managed"] = False
            record["reason"] = "attached_or_mocked"
        state = self._load_state()
        state.setdefault("sessions", {})[session_id] = record
        state["active_session_id"] = session_id
        state["updated_at"] = now
        self._write_state(state)
        return dict(record)

    def stop_session(self, session_id: str | None = None) -> dict[str, Any]:
        record = self._get_session_record(session_id)
        process = self._processes.pop(record["id"], None)
        if process is not None:
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
        record["state"] = "stopped"
        record["updated_at"] = now_iso()
        self._save_session(record)
        return dict(record)

    def restart_session(self, session_id: str | None = None) -> dict[str, Any]:
        previous = self._get_session_record(session_id)
        self.stop_session(previous["id"])
        return self.start_session(
            session_id=previous["id"],
            profile_id=previous.get("profile_id"),
            url=previous.get("target_url"),
            debugging_port=safe_int(previous.get("debugging_port"), 9222),
            launch=bool(previous.get("managed")),
        )

    def health(self, session_id: str | None = None) -> dict[str, Any]:
        record = self._get_session_record(session_id)
        result = {"ok": False, "session": dict(record), "connected": False, "tabs": []}
        if record.get("state") != "running":
            result["reason"] = record.get("reason") or "session_not_running"
            return result
        client = self._client_for(record)
        try:
            result["version"] = client.version()
            result["tabs"] = client.list_tabs()
            result["connected"] = True
            result["ok"] = True
        except Exception as exc:
            result["reason"] = str(exc)
        return result

    def list_tabs(self, session_id: str | None = None) -> dict[str, Any]:
        record = self._get_session_record(session_id)
        tabs = self._client_for(record).list_tabs()
        return {"session_id": record["id"], "tabs": tabs, "count": len(tabs)}

    def open_tab(self, *, url: str = "about:blank", session_id: str | None = None) -> dict[str, Any]:
        record = self._get_session_record(session_id)
        result = self._client_for(record).new_tab(url)
        return {"session_id": record["id"], **result}

    def focus_tab(self, *, tab_id: str, session_id: str | None = None) -> dict[str, Any]:
        record = self._get_session_record(session_id)
        result = self._client_for(record).activate_tab(tab_id)
        return {"session_id": record["id"], "tab_id": tab_id, **result}

    def close_tab(self, *, tab_id: str, session_id: str | None = None) -> dict[str, Any]:
        record = self._get_session_record(session_id)
        result = self._client_for(record).close_tab(tab_id)
        return {"session_id": record["id"], "tab_id": tab_id, **result}

    def navigate_tab(self, *, url: str, tab_id: str | None = None, session_id: str | None = None) -> dict[str, Any]:
        record = self._get_session_record(session_id)
        result = self._client_for(record).navigate(tab_id, url)
        return {"session_id": record["id"], "tab_id": tab_id, "url": url, **result}

    def snapshot_tab(self, *, tab_id: str | None = None, session_id: str | None = None) -> dict[str, Any]:
        record = self._get_session_record(session_id)
        result = self._client_for(record).snapshot(tab_id)
        if not result.get("ok"):
            return {"session_id": record["id"], "tab_id": tab_id, **result}
        snapshot = self.snapshot_store.store_snapshot(session_id=record["id"], tab_id=tab_id, snapshot=result["snapshot"])
        return {"ok": True, "session_id": record["id"], "tab_id": tab_id, "snapshot": snapshot}

    def screenshot_tab(
        self,
        *,
        tab_id: str | None = None,
        session_id: str | None = None,
        format: str = "png",
        quality: int | None = None,
    ) -> dict[str, Any]:
        record = self._get_session_record(session_id)
        result = self._client_for(record).screenshot(tab_id, format=format, quality=quality)
        if not result.get("ok"):
            return {"session_id": record["id"], "tab_id": tab_id, **result}
        artifact = self.artifact_store.write_base64(
            result["data"],
            suffix=".jpg" if result.get("mime_type") == "image/jpeg" else ".png",
            mime_type=result.get("mime_type"),
            name="browser-screenshot-{}-{}".format(record["id"], tab_id or "active"),
        )
        return {"ok": True, "session_id": record["id"], "tab_id": tab_id, "artifact": artifact}

    def execute_ref_action(
        self,
        *,
        action: str,
        ref_id: str | None = None,
        session_id: str | None = None,
        tab_id: str | None = None,
        payload: dict[str, Any] | None = None,
        current_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(payload or {})
        record = self._get_session_record(session_id)
        ref = self.snapshot_store.get_ref(ref_id or "")
        recovered = None
        if ref is None and current_snapshot is not None:
            recovered = self.snapshot_store.recover_ref({"id": ref_id}, snapshot=current_snapshot)
            ref = recovered
        if ref is None:
            return computer_use_fallback_contract(
                browser_action="browser.ref.{}".format(action),
                reason="ref_not_found",
                ref={"id": ref_id} if ref_id else None,
                payload=payload,
            )
        selector = ref.get("selector")
        if selector:
            executed = self._execute_selector_action(record, tab_id or ref.get("tab_id"), selector, action, payload)
            if executed.get("ok"):
                executed["ref"] = ref
                if recovered:
                    executed["recovered"] = True
                return executed
        return computer_use_fallback_contract(
            browser_action="browser.ref.{}".format(action),
            reason="cdp_ref_action_unavailable",
            ref=ref,
            payload=payload,
        )

    def _execute_selector_action(
        self,
        record: dict[str, Any],
        tab_id: str | None,
        selector: str,
        action: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        script = _selector_script(selector, action, payload)
        if not script:
            return {"ok": False, "reason": "unsupported_ref_action", "action": action}
        evaluated = self._client_for(record).evaluate(tab_id, script)
        if evaluated.get("ok") and evaluated.get("value") is True:
            return {"ok": True, "session_id": record["id"], "tab_id": tab_id, "action": action}
        return {"ok": False, "reason": "selector_action_failed", "details": evaluated}

    def _client_for(self, record: dict[str, Any]) -> CdpClient:
        endpoint = record.get("endpoint") if isinstance(record.get("endpoint"), dict) else {}
        host = str(endpoint.get("host") or "127.0.0.1")
        port = safe_int(endpoint.get("port") or record.get("debugging_port"), 9222)
        if self._cdp_client_factory is None:
            return CdpClient(host, port)
        try:
            return self._cdp_client_factory(record)
        except TypeError:
            return self._cdp_client_factory(host, port)

    def _get_session_record(self, session_id: str | None = None) -> dict[str, Any]:
        state = self._load_state()
        sessions = state.get("sessions") if isinstance(state.get("sessions"), dict) else {}
        session_id = sanitize_id(session_id or state.get("active_session_id") or "")
        record = sessions.get(session_id)
        if not isinstance(record, dict):
            raise KeyError("browser session not found: {}".format(session_id or "active"))
        return dict(record)

    def _save_session(self, record: dict[str, Any]) -> None:
        state = self._load_state()
        state.setdefault("sessions", {})[record["id"]] = record
        if not state.get("active_session_id"):
            state["active_session_id"] = record["id"]
        state["updated_at"] = now_iso()
        self._write_state(state)

    def _load_state(self) -> dict[str, Any]:
        value = read_json(self.session_path, {})
        if not isinstance(value, dict):
            value = {}
        value.setdefault("version", 1)
        value.setdefault("sessions", {})
        return value

    def _write_state(self, state: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        write_json(self.session_path, state)

    def _launch_command(self, profile: dict[str, Any], *, port: int, url: str | None, extra_args: list[str]) -> list[str]:
        executable = self._browser_executable or self._find_browser_executable()
        if executable is None:
            return []
        args = [
            str(executable),
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port={}".format(port),
        ]
        args.extend(profile.get("launch", {}).get("args") or [])
        args.extend(extra_args)
        if url:
            args.append(url)
        return args

    @staticmethod
    def _default_port(session_id: str) -> int:
        return 9300 + (sum(ord(ch) for ch in session_id) % 400)

    @staticmethod
    def _find_browser_executable() -> Path | None:
        system = platform.system()
        candidates: list[Path] = []
        if system == "Darwin":
            candidates = [
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
                Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                Path.home() / "Applications" / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome",
            ]
        elif system == "Windows":
            for key in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
                base = os.environ.get(key)
                if base:
                    candidates.extend(
                        [
                            Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe",
                            Path(base) / "Chromium" / "Application" / "chrome.exe",
                            Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                        ]
                    )
        else:
            for name in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge"):
                found = shutil.which(name)
                if found:
                    candidates.append(Path(found))
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None


def _selector_script(selector: str, action: str, payload: dict[str, Any]) -> str | None:
    selector_json = _json_string(selector)
    if action == "click":
        return "(function(){var el=document.querySelector(%s); if(!el) return false; el.scrollIntoView({block:'center',inline:'center'}); el.click(); return true;})()" % selector_json
    if action == "type":
        text_json = _json_string(str(payload.get("text", "")))
        return "(function(){var el=document.querySelector(%s); if(!el) return false; el.focus(); if('value' in el){el.value=%s; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true}));} else {el.textContent=%s;} return true;})()" % (selector_json, text_json, text_json)
    if action == "scroll":
        amount = safe_int(payload.get("amount"), 1)
        return "(function(){var el=document.querySelector(%s); if(!el) return false; el.scrollBy(0,%d); return true;})()" % (selector_json, amount)
    return None


def _json_string(value: str) -> str:
    import json

    return json.dumps(value)
