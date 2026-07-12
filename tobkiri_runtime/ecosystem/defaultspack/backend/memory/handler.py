from __future__ import annotations

from typing import Any, Dict, List

from .memory_manager import MemoryManager
from .store import MemoryEntry, MemoryStore, MemoryType

_layers: Dict[str, bool] = {layer.value: True for layer in MemoryType}
_layer_stores: Dict[str, Dict[str, Any]] = {layer.value: {} for layer in MemoryType}
_user_model = MemoryStore().get_user_model()


def store_memory(layer_id: str, key: str, value: Any) -> Dict[str, Any]:
    if layer_id not in _layers:
        return {"status_code": 404}
    if not _layers[layer_id]:
        return {"status_code": 403}
    _layer_stores[layer_id][key] = value
    return {"stored": True, "layer_id": layer_id, "key": key}


def recall_memory(layer_id: str, key: str | None = None) -> Dict[str, Any]:
    if layer_id not in _layers:
        return {"status_code": 404}
    if key is None:
        items = [{"key": k, "value": v} for k, v in _layer_stores[layer_id].items()]
    else:
        items = [{"key": key, "value": _layer_stores[layer_id].get(key)}] if key in _layer_stores[layer_id] else []
    return {"results": items}


def set_layer_enabled(layer_id: str, enabled: bool) -> Dict[str, Any]:
    if layer_id not in _layers:
        return {"status_code": 404}
    _layers[layer_id] = enabled
    return {"layer_id": layer_id, "enabled": enabled}


def list_layers() -> List[Dict[str, Any]]:
    return [{"layer_id": layer_id, "enabled": enabled} for layer_id, enabled in _layers.items()]


def get_user_model() -> Dict[str, Any]:
    return _user_model.to_dict()


def set_user_model_opt_in(value: bool) -> Dict[str, Any]:
    _user_model.opt_in = bool(value)
    return _user_model.to_dict()
