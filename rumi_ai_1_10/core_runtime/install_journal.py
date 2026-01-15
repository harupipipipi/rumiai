"""
install_journal.py - Install Journal(jsonl追記)+ uninstall基盤

Step1では「API形状」と「デフォルト保存先の固定」だけ置く。
jsonl追記やuninstallの実処理はStep5で実装する。
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple, Iterable, Set


@dataclass
class InstallJournalConfig:
    """Install Journalの基本設定"""
    dir_path: str = "user_data/settings/ecosystem/install_journal"
    enabled: bool = True
    file_prefix: str = "install_journal"


class InstallJournal:
    """
    セットアップ/依存/seed/addon_apply等が「システムとして作ったファイル」を追跡する。

    重要(確定仕様):
    - uninstallで削除してよい領域: settings/cache/assets
    - 保護領域: chats/shared
    - 会話中生成物(workspace/tool_files等)は対象外
    """

    def __init__(self, config: Optional[InstallJournalConfig] = None) -> None:
        self.config = config or InstallJournalConfig()
        self._last_error: Optional[str] = None

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def last_error(self) -> Optional[str]:
        """直近の失敗理由(あれば)"""
        return self._last_error

    def _journal_dir(self) -> Path:
        return Path(self.config.dir_path)

    def _journal_file_path(self) -> Path:
        """
        jsonl は追記ログなので、日毎ファイルに分割する(巨大化を避ける)。
        """
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        name = f"{self.config.file_prefix}_{day}.jsonl"
        return self._journal_dir() / name

    def _ensure_dir(self) -> None:
        self._journal_dir().mkdir(parents=True, exist_ok=True)

    def append(self, event: Dict[str, Any]) -> None:
        """
        journalに追記する(jsonl想定)。

        Step5 実装:
        - enabledでなければ何もしない
        - jsonlとして1行追記(UTF-8)
        - 失敗しても例外で落とさず、last_errorに保持
        """
        if not self.config.enabled:
            return

        try:
            self._ensure_dir()
            fp = self._journal_file_path()

            # 最低限の正規化(仕様を強制しないが、tsは入れておくと後で便利)
            ev = dict(event or {})
            ev.setdefault("ts", self._now_ts())

            line = json.dumps(ev, ensure_ascii=False)
            with open(fp, "a", encoding="utf-8") as f:
                f.write(line + "\n")

            self._last_error = None
        except Exception as e:
            # fail-soft
            self._last_error = f"{type(e).__name__}: {e}"
            return

    def uninstall(self, dry_run: bool = True) -> Dict[str, Any]:
        """
        uninstallを実行(削除対象だけ削除し、保護領域は絶対削除しない)。

        Step5 実装(確定仕様準拠):
        - journalに記録された created paths を候補に削除
        - 削除してよい領域(allowed roots)配下のみ削除
        - 保護領域(protected roots)配下は絶対削除しない
        - dry_run=Trueなら削除せず計画のみ返す
        - mountsが取得できる場合は mounts を優先して allowed/protected を解決
          (取得できなければ user_data の既定パスへフォールバック)
        """
        result: Dict[str, Any] = {
            "success": True,
            "dry_run": dry_run,
            "journal_dir": str(self._journal_dir()),
            "journal_files": [],
            "planned_delete": [],
            "deleted": [],
            "skipped": [],
            "errors": [],
            "policy": {},
        }

        try:
            allowed_roots, protected_roots, policy_meta = self._resolve_policy_roots()
            result["policy"] = policy_meta

            # journalファイル一覧
            jdir = self._journal_dir()
            if not jdir.exists():
                # journalが無い場合は何もしない
                return result

            files = sorted([p for p in jdir.glob("*.jsonl") if p.is_file()])
            result["journal_files"] = [str(p) for p in files]

            # 削除候補の収集(createdのみ)
            candidates = self._collect_created_paths(files, result["errors"])

            # ルール適用(allowed/protected)
            planned: List[str] = []
            for p in sorted(candidates):
                decision, reason = self._decide_path(p, allowed_roots, protected_roots)
                if decision == "delete":
                    planned.append(str(p))
                else:
                    result["skipped"].append({"path": str(p), "reason": reason})

            result["planned_delete"] = planned

            if dry_run:
                return result

            # 実削除
            for p_str in planned:
                p = Path(p_str)
                try:
                    if not p.exists():
                        result["skipped"].append({"path": p_str, "reason": "not_exists"})
                        continue

                    # 念のため再判定(TOCTOU対策)
                    decision, reason = self._decide_path(p, allowed_roots, protected_roots)
                    if decision != "delete":
                        result["skipped"].append({"path": p_str, "reason": f"recheck:{reason}"})
                        continue

                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink()
                    result["deleted"].append(p_str)
                except Exception as e:
                    result["success"] = False
                    result["errors"].append({"path": p_str, "error": f"{type(e).__name__}: {e}"})

            return result

        except Exception as e:
            # fail-soft(uninstall自体の失敗は返り値で表現)
            result["success"] = False
            result["errors"].append({"error": f"{type(e).__name__}: {e}"})
            return result

    # ---------------------------
    # internal: policy resolution
    # ---------------------------

    def _resolve_policy_roots(self) -> Tuple[List[Path], List[Path], Dict[str, Any]]:
        """
        allowed/protected roots を解決する。

        可能なら mounts.json を用いて data.* の実パスを取得し、
        取れなければ user_data の既定配置へフォールバック。
        """
        allowed: List[Path] = []
        protected: List[Path] = []

        meta: Dict[str, Any] = {
            "source": "fallback",
            "allowed_mounts": ["data.settings", "data.cache", "data.tools.assets", "data.prompts.assets", "data.ai_clients.assets", "data.supporters.assets"],
            "protected_mounts": ["data.chats", "data.shared"],
        }

        # 1) mountsが使えるならそれを優先
        try:
            from backend_core.ecosystem.mounts import get_mount_manager
            mm = get_mount_manager()
            # ensure_exists=False を使い、uninstallで余計なディレクトリを作らない
            allowed = [
                mm.get_path("data.settings", ensure_exists=False),
                mm.get_path("data.cache", ensure_exists=False),
                mm.get_path("data.tools.assets", ensure_exists=False),
                mm.get_path("data.prompts.assets", ensure_exists=False),
                mm.get_path("data.ai_clients.assets", ensure_exists=False),
                mm.get_path("data.supporters.assets", ensure_exists=False),
            ]
            protected = [
                mm.get_path("data.chats", ensure_exists=False),
                mm.get_path("data.shared", ensure_exists=False),
            ]
            meta["source"] = "mounts"
        except Exception:
            # 2) fallback: 既定 user_data 配置
            ud = Path("user_data").resolve()
            allowed = [
                (ud / "settings").resolve(),
                (ud / "cache").resolve(),
                (ud / "default_tool" / "assets").resolve(),
                (ud / "default_prompt" / "assets").resolve(),
                (ud / "default_ai_client" / "assets").resolve(),
                (ud / "default_supporter" / "assets").resolve(),
            ]
            protected = [
                (ud / "chats").resolve(),
                (ud / "shared").resolve(),
            ]

        # 末尾の存在チェックはしない(存在しなくてもルールとして成立する)
        meta["allowed_roots"] = [str(p) for p in allowed]
        meta["protected_roots"] = [str(p) for p in protected]
        return allowed, protected, meta

    def _collect_created_paths(self, files: List[Path], errors: List[Dict[str, Any]]) -> Set[Path]:
        """
        journalから created paths のみを収集する。
        modified は原則削除対象にしない(復元できないため)。
        """
        out: Set[Path] = set()
        for fp in files:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    for ln_no, line in enumerate(f, start=1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            ev = json.loads(line)
                        except Exception as e:
                            errors.append({"file": str(fp), "line": ln_no, "error": f"json_parse:{type(e).__name__}: {e}"})
                            continue

                        paths = ev.get("paths")
                        if not isinstance(paths, dict):
                            continue
                        created = paths.get("created")
                        if not isinstance(created, list):
                            continue
                        for p in created:
                            if not isinstance(p, str) or not p.strip():
                                continue
                            out.add(Path(p).expanduser().resolve())
            except Exception as e:
                errors.append({"file": str(fp), "error": f"read:{type(e).__name__}: {e}"})
        return out

    def _decide_path(self, path: Path, allowed_roots: List[Path], protected_roots: List[Path]) -> Tuple[str, str]:
        """
        Returns:
            ("delete"|"skip", reason)
        """
        try:
            p = path.expanduser().resolve()
        except Exception:
            return "skip", "unresolvable_path"

        # 保護領域は最優先で拒否
        for root in protected_roots:
            if self._is_within(p, root):
                return "skip", "protected_root"

        # allowed配下のみ削除OK
        for root in allowed_roots:
            if self._is_within(p, root):
                # ルートそのものを削除しない(危険)
                if p == root:
                    return "skip", "is_allowed_root_itself"
                return "delete", "ok"

        return "skip", "outside_allowed_roots"

    def _is_within(self, path: Path, root: Path) -> bool:
        """
        path が root 配下か(同一も含む)を判定。
        rootが相対でもresolveして比較する。
        """
        try:
            r = root.expanduser().resolve()
            path.relative_to(r)
            return True
        except Exception:
            return False
