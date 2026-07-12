from __future__ import annotations

from typing import Any, Dict, List

from .knowledge_manager import KnowledgeEntry, KnowledgeStore

_store = KnowledgeStore()


def create_knowledge(data: Dict[str, Any]) -> Dict[str, Any]:
    entry = KnowledgeEntry(
        knowledge_id=str(data.get("knowledge_id") or data.get("id") or ""),
        title=str(data.get("title") or ""),
        content=str(data.get("content") or ""),
        tags=list(data.get("tags") or []),
        metadata=dict(data.get("metadata") or {}),
        entry_type=str(data.get("entry_type") or "knowledge"),
        error_pattern=data.get("error_pattern") or "",
        solution=data.get("solution") or "",
        source=data.get("source") or "",
    )
    kid = _store.create(entry)
    return {"created": True, "id": kid}


def get_knowledge(knowledge_id: str) -> Dict[str, Any]:
    entry = _store.read(knowledge_id)
    return entry.to_dict() if entry else {"status_code": 404}


def list_knowledge() -> List[Dict[str, Any]]:
    return [entry.to_dict() for entry in _store.list_all()]


def update_knowledge(knowledge_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    ok = _store.update(knowledge_id, updates)
    return {"updated": bool(ok)}


def delete_knowledge(knowledge_id: str) -> Dict[str, Any]:
    return {"deleted": _store.delete(knowledge_id)}


def search_knowledge(query: str) -> List[Dict[str, Any]]:
    return _store.retrieve_relevant(query)


def store_error_solution(error_pattern: str, solution: str, source: str) -> Dict[str, Any]:
    kid = _store.accumulate_error(error_pattern, solution, source)
    return {"created": True, "id": kid}
