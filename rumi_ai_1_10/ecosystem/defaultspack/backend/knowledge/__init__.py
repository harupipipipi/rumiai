"""knowledge module - Knowledge base CRUD and relevance search."""
from __future__ import annotations
import logging, threading, time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
logger = logging.getLogger(__name__)

@dataclass
class KnowledgeEntry:
    knowledge_id: str; title: str = ""; content: str = ""; category: str = "general"
    tags: List[str] = field(default_factory=list); metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time); relevance_score: float = 0.0
    def to_dict(self): return {"knowledge_id": self.knowledge_id, "title": self.title, "content": self.content, "category": self.category, "tags": self.tags, "relevance_score": self.relevance_score}

class KnowledgeManager:
    def __init__(self):
        self._lock = threading.RLock(); self._entries: Dict[str, KnowledgeEntry] = {}
    def create(self, entry: KnowledgeEntry): self._entries[entry.knowledge_id] = entry
    def get(self, kid: str) -> Optional[KnowledgeEntry]: return self._entries.get(kid)
    def update(self, kid: str, **kw) -> bool:
        e = self._entries.get(kid)
        if not e: return False
        for k, v in kw.items():
            if hasattr(e, k): setattr(e, k, v)
        return True
    def delete(self, kid: str) -> bool: return self._entries.pop(kid, None) is not None
    def list_all(self) -> List[KnowledgeEntry]: return list(self._entries.values())
    def search(self, query: str, limit: int = 10) -> List[KnowledgeEntry]:
        q = set(query.lower().split()); results = []
        for e in self._entries.values():
            txt = set(f"{e.title} {e.content} {' '.join(e.tags)}".lower().split())
            overlap = q & txt
            if overlap:
                e.relevance_score = len(overlap) / max(len(q), 1)
                results.append(e)
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        return results[:limit]
    def store_error_solution(self, error: str, solution: str) -> str:
        kid = f"err-{len(self._entries)}"
        self.create(KnowledgeEntry(knowledge_id=kid, title=f"Error: {error[:80]}", content=f"Error: {error}\nSolution: {solution}", category="error_solution", tags=["error", "solution"]))
        return kid
