from __future__ import annotations

from blocks._common import error, ok

from ._runtime import ref_store


def run(input_data, context=None):
    input_data = input_data if isinstance(input_data, dict) else {}
    action = str(input_data.get("action") or "extract")
    store = ref_store(input_data, context)
    try:
        if action == "extract":
            snapshot = input_data.get("snapshot") if isinstance(input_data.get("snapshot"), dict) else {}
            return ok({"refs": store.extract_refs(snapshot)})
        if action == "store":
            snapshot = input_data.get("snapshot") if isinstance(input_data.get("snapshot"), dict) else {}
            return ok(
                {
                    "snapshot": store.store_snapshot(
                        session_id=str(input_data.get("session_id") or "default"),
                        tab_id=input_data.get("tab_id"),
                        snapshot=snapshot,
                    )
                }
            )
        if action == "resolve":
            ref = store.get_ref(str(input_data.get("ref_id") or input_data.get("ref") or ""))
            if ref is None:
                return error("ref not found", code="NOT_FOUND")
            return ok({"ref": ref})
        if action == "recover":
            stale = input_data.get("stale_ref") or input_data.get("ref_id") or input_data.get("ref")
            snapshot = input_data.get("snapshot") if isinstance(input_data.get("snapshot"), dict) else None
            recovered = store.recover_ref(
                stale,
                snapshot=snapshot,
                session_id=input_data.get("session_id"),
                tab_id=input_data.get("tab_id"),
            )
            if recovered is None:
                return error("ref recovery failed", code="NOT_FOUND")
            return ok({"ref": recovered})
    except Exception as exc:
        return error(str(exc), code="BROWSER_REF_ERROR")
    return error("unsupported browser ref action: {}".format(action), code="INVALID_ACTION")
