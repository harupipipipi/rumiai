from __future__ import annotations

from typing import Any

from .context import AdaptiveError, now_iso, redact
from .event_service import event_indicates_failure, event_indicates_verified_success, event_payload_bool


class SkillServiceMixin:
    def skill_candidate_list(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del args, ctx
        state = self.store.read_json("skills/candidates.json", {"version": 1, "candidates": []})
        promoted = self.store.read_json("skills/promoted.json", {"version": 1, "skills": []})
        return {
            "profile_id": self.profile_id,
            "candidates": state.get("candidates", []) if isinstance(state, dict) else [],
            "promoted_skills": promoted.get("skills", []) if isinstance(promoted, dict) else [],
            "local_only": True,
        }

    def skill_candidate_promote(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        self._ensure_not_frozen("skill_candidate.promote")
        candidate_id = str(args.get("candidate_id") or "").strip()
        if not candidate_id:
            raise AdaptiveError("INVALID_INPUT", "candidate_id is required")
        result = self._promote_skill_candidate(candidate_id, args)
        self._append_event("adaptive.skill_candidate.promote", {"candidate_id": candidate_id, "skill_id": result["skill"]["skill_id"]})
        return {"profile_id": self.profile_id, "candidate_id": candidate_id, "promoted": True, **result}

    def skill_candidate_rollback(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        self._ensure_not_frozen("skill_candidate.rollback")
        candidate_id = str(args.get("candidate_id") or "").strip()
        if not candidate_id:
            raise AdaptiveError("INVALID_INPUT", "candidate_id is required")
        result = self._rollback_skill_candidate(candidate_id, args)
        self._append_event("adaptive.skill_candidate.rollback", {"candidate_id": candidate_id, "skill_id": result["skill"].get("skill_id")})
        return {"profile_id": self.profile_id, "candidate_id": candidate_id, "rolled_back": True, **result}

    def _promote_skill_candidate(self, candidate_id: str, args: dict[str, Any]) -> dict[str, Any]:
        selected: dict[str, Any] = {}

        def update_candidates(state: Any) -> dict[str, Any]:
            nonlocal selected
            candidates = state.get("candidates") if isinstance(state, dict) and isinstance(state.get("candidates"), list) else []
            selected = next((item for item in candidates if item.get("candidate_id") == candidate_id or item.get("id") == candidate_id), {})
            if not selected and isinstance(args.get("candidate"), dict):
                selected = dict(args["candidate"])
                selected.setdefault("candidate_id", candidate_id)
                candidates.append(selected)
            if not selected:
                raise AdaptiveError("NOT_FOUND", "skill candidate not found")
            selected["status"] = "promoted"
            selected["promoted_at"] = now_iso()
            selected["updated_at"] = selected["promoted_at"]
            return {"version": 1, "candidates": candidates[-500:]}

        self.store.update_json("skills/candidates.json", {"version": 1, "candidates": []}, update_candidates)
        evidence = self._validate_skill_candidate_evidence(selected)
        skill = {
            "skill_id": str(args.get("skill_id") or selected.get("skill_id") or f"skill_{candidate_id}"),
            "candidate_id": candidate_id,
            "title": str(selected.get("title") or selected.get("name") or candidate_id),
            "status": "canary",
            "canary_state": "pending",
            "evidence": evidence,
            "source": redact(selected),
            "promoted_at": now_iso(),
            "updated_at": now_iso(),
        }

        def update_promoted(state: Any) -> dict[str, Any]:
            skills = state.get("skills") if isinstance(state, dict) and isinstance(state.get("skills"), list) else []
            existing = next((item for item in skills if item.get("skill_id") == skill["skill_id"]), None)
            if existing is None:
                skills.append(skill)
            else:
                existing.update(skill)
            return {"version": 1, "skills": skills[-500:]}

        self.store.update_json("skills/promoted.json", {"version": 1, "skills": []}, update_promoted)
        return {"candidate": selected, "skill": skill}

    def _rollback_skill_candidate(self, candidate_id: str, args: dict[str, Any]) -> dict[str, Any]:
        skill_id = str(args.get("skill_id") or "").strip()
        rolled_back: dict[str, Any] = {}

        def update_promoted(state: Any) -> dict[str, Any]:
            nonlocal rolled_back
            skills = state.get("skills") if isinstance(state, dict) and isinstance(state.get("skills"), list) else []
            for skill in skills:
                if skill.get("candidate_id") == candidate_id or (skill_id and skill.get("skill_id") == skill_id):
                    skill["status"] = "rolled_back"
                    skill["rollback_reason"] = str(args.get("reason") or "").strip() or None
                    skill["rolled_back_at"] = now_iso()
                    skill["updated_at"] = skill["rolled_back_at"]
                    rolled_back = dict(skill)
                    return {"version": 1, "skills": skills[-500:]}
            raise AdaptiveError("NOT_FOUND", "promoted skill not found")

        self.store.update_json("skills/promoted.json", {"version": 1, "skills": []}, update_promoted)

        def update_candidates(state: Any) -> dict[str, Any]:
            candidates = state.get("candidates") if isinstance(state, dict) and isinstance(state.get("candidates"), list) else []
            for candidate in candidates:
                if candidate.get("candidate_id") == candidate_id or candidate.get("id") == candidate_id:
                    candidate["status"] = "rolled_back"
                    candidate["updated_at"] = now_iso()
            return {"version": 1, "candidates": candidates[-500:]}

        self.store.update_json("skills/candidates.json", {"version": 1, "candidates": []}, update_candidates)
        return {"skill": rolled_back}

    def _validate_skill_candidate_evidence(self, candidate: dict[str, Any]) -> dict[str, Any]:
        evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), dict) else {}
        failure_id = str(evidence.get("failure_event_id") or "").strip()
        success_id = str(evidence.get("success_event_id") or "").strip()
        replay_id = str(evidence.get("replay_event_id") or "").strip()
        if not failure_id or not success_id:
            raise AdaptiveError("INVALID_INPUT", "skill promotion requires failure_event_id and success_event_id evidence")
        failure = self._event_by_id(failure_id)
        success = self._event_by_id(success_id)
        replay = self._event_by_id(replay_id) if replay_id else None
        if failure is None:
            raise AdaptiveError("INVALID_INPUT", "failure evidence event not found")
        if success is None:
            raise AdaptiveError("INVALID_INPUT", "success evidence event not found")
        if not event_indicates_failure(failure):
            raise AdaptiveError("INVALID_INPUT", "failure evidence must describe a failed episode")
        if not event_indicates_verified_success(success):
            raise AdaptiveError("INVALID_INPUT", "success evidence must describe a verified successful episode")
        if replay is None and not event_payload_bool(success, "replay_verified"):
            raise AdaptiveError("INVALID_INPUT", "skill promotion requires replay evidence")
        if replay is not None and not event_indicates_verified_success(replay):
            raise AdaptiveError("INVALID_INPUT", "replay evidence must describe a verified successful replay")
        return {
            "failure_event_id": failure_id,
            "success_event_id": success_id,
            "replay_event_id": replay_id or success_id,
            "canary_required": True,
        }
