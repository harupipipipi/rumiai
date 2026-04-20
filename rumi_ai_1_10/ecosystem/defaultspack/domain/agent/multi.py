import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import re
import threading

from blocks._common import gen_id, timestamp
from domain.agent.agent_def import AgentDefinition
from domain.ai_client.client import AIClient


# ---------------------------------------------------------------------------
# MessageBus — エージェント間インメモリメッセージバス
# ---------------------------------------------------------------------------

class MessageBus:
    """エージェント間でメッセージを送受信するインメモリバス。

    shared_messages  : 全エージェントが参照できる共有メッセージ履歴
    private_queues   : エージェント名 → そのエージェント宛のメッセージリスト
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.shared_messages = []
        self.private_queues = {}

    def register_agent(self, agent_name):
        with self._lock:
            if agent_name not in self.private_queues:
                self.private_queues[agent_name] = []

    def post_shared(self, sender, content, turn_number):
        """共有メッセージを投稿する。"""
        msg = {
            "id": "msg_" + gen_id(),
            "sender": sender,
            "content": content,
            "turn": turn_number,
            "timestamp": timestamp(),
        }
        with self._lock:
            self.shared_messages.append(msg)
        return msg

    def post_direct(self, sender, target, content, turn_number):
        """特定エージェント宛にダイレクトメッセージを送る。"""
        msg = {
            "id": "msg_" + gen_id(),
            "sender": sender,
            "target": target,
            "content": content,
            "turn": turn_number,
            "timestamp": timestamp(),
        }
        with self._lock:
            if target in self.private_queues:
                self.private_queues[target].append(msg)
            self.shared_messages.append(msg)
        return msg

    def get_shared_history(self):
        with self._lock:
            return list(self.shared_messages)

    def get_private_messages(self, agent_name):
        with self._lock:
            return list(self.private_queues.get(agent_name, []))

    def to_dict(self):
        with self._lock:
            return {
                "shared_messages": list(self.shared_messages),
                "private_queues": {k: list(v) for k, v in self.private_queues.items()},
            }


# ---------------------------------------------------------------------------
# MultiAgentSession — セッション状態
# ---------------------------------------------------------------------------

class MultiAgentSession:
    """マルチエージェントセッションの全状態を保持する。"""

    def __init__(self, session_id, task, agents, orchestration, max_turns):
        self.session_id = session_id
        self.task = task
        self.agents = agents
        self.orchestration = orchestration
        self.max_turns = max_turns
        self.status = "created"
        self.current_turn = 0
        self.message_bus = MessageBus()
        self.agent_contexts = {}
        self.shared_context = {}
        self.result = None
        self.error = None
        self.created_at = timestamp()
        self.updated_at = timestamp()

        for agent in self.agents:
            self.message_bus.register_agent(agent.name)
            self.agent_contexts[agent.name] = {
                "messages": [],
                "status": "idle",
                "turns_taken": 0,
                "done": False,
            }

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "task": self.task,
            "agents": [a.to_dict() for a in self.agents],
            "orchestration": self.orchestration,
            "max_turns": self.max_turns,
            "status": self.status,
            "current_turn": self.current_turn,
            "message_bus": self.message_bus.to_dict(),
            "agent_contexts": {
                name: {
                    "status": ctx["status"],
                    "turns_taken": ctx["turns_taken"],
                    "done": ctx["done"],
                    "message_count": len(ctx["messages"]),
                }
                for name, ctx in self.agent_contexts.items()
            },
            "shared_context": self.shared_context,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


# ---------------------------------------------------------------------------
# MultiAgentOrchestrator — 本体
# ---------------------------------------------------------------------------

_MENTION_RE = re.compile(r"@(\w+)\s*:")

DONE_MARKER = "[DONE]"


class MultiAgentOrchestrator:
    """複数エージェントの協調を管理するオーケストレーター。"""

    def __init__(self):
        self._client = AIClient()

    # ------------------------------------------------------------------
    # AI 呼び出しヘルパー（AgentEngine のパターンを踏襲）
    # ------------------------------------------------------------------

    def _ai_complete(self, messages, model, tools):
        """AIClient 経由で completion を取得する。"""
        try:
            result = self._client.complete(model, messages, tools=tools)
            return {"status": "ok", "data": result}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _parse_ai_response(self, ai_result):
        """AI レスポンスをパースして type/content を返す。"""
        if ai_result.get("status") != "ok":
            return {
                "type": "error",
                "content": ai_result.get("error", "AI call failed"),
            }
        data = ai_result.get("data", {})

        if isinstance(data, dict) and data.get("tool_calls"):
            tool_calls = data["tool_calls"]
            first_call = (
                tool_calls[0]
                if isinstance(tool_calls, list) and len(tool_calls) > 0
                else tool_calls
            )
            return {
                "type": "tool_call",
                "tool_name": first_call.get(
                    "name", first_call.get("function", {}).get("name", "unknown")
                ),
                "tool_args": first_call.get(
                    "args", first_call.get("function", {}).get("arguments", {})
                ),
                "raw": first_call,
            }

        content = ""
        if isinstance(data, dict):
            content = data.get("content", data.get("text", str(data)))
        elif isinstance(data, str):
            content = data
        else:
            content = str(data)
        return {"type": "text", "content": content}

    # ------------------------------------------------------------------
    # メッセージ構築
    # ------------------------------------------------------------------

    def _build_system_prompt(self, agent_def, session):
        """エージェント用のシステムプロンプトを構築する。"""
        parts = []
        if agent_def.system_prompt:
            parts.append(agent_def.system_prompt)

        parts.append(
            "Your name is '"
            + agent_def.name
            + "'. Your role: "
            + agent_def.role
        )

        other_names = [a.name for a in session.agents if a.name != agent_def.name]
        if other_names:
            parts.append(
                "Other agents in this session: "
                + ", ".join(other_names)
                + ". You can address them with @name: message."
            )

        parts.append(
            "The shared task is: " + session.task
        )
        parts.append(
            "When you believe the task is fully complete, include '"
            + DONE_MARKER
            + "' in your response."
        )

        return "\n\n".join(parts)

    def _build_messages_for_agent(self, agent_def, session):
        """あるエージェント向けの messages リストを構築する。"""
        messages = []

        system_content = self._build_system_prompt(agent_def, session)
        messages.append({"role": "system", "content": system_content})

        messages.append({"role": "user", "content": "Task: " + session.task})

        shared = session.message_bus.get_shared_history()
        for msg in shared:
            if msg["sender"] == agent_def.name:
                messages.append({"role": "assistant", "content": msg["content"]})
            else:
                messages.append({
                    "role": "user",
                    "content": "[" + msg["sender"] + "]: " + msg["content"],
                })

        private_msgs = session.message_bus.get_private_messages(agent_def.name)
        ctx_private = session.agent_contexts[agent_def.name]["messages"]
        already_in_shared = {m["id"] for m in shared}
        for pm in private_msgs:
            if pm["id"] not in already_in_shared:
                messages.append({
                    "role": "user",
                    "content": "[DM from " + pm["sender"] + "]: " + pm["content"],
                })
        for cm in ctx_private:
            messages.append(cm)

        return messages

    # ------------------------------------------------------------------
    # ターン制御
    # ------------------------------------------------------------------

    def _select_next_agents_round_robin(self, session):
        """ラウンドロビンで次に発言するエージェントを1つ返す。"""
        agents = session.agents
        if not agents:
            return []
        idx = session.current_turn % len(agents)
        agent = agents[idx]
        if session.agent_contexts[agent.name]["done"]:
            for offset in range(1, len(agents)):
                candidate = agents[(idx + offset) % len(agents)]
                if not session.agent_contexts[candidate.name]["done"]:
                    return [candidate]
            return []
        return [agent]

    def _select_next_agents_directed(self, session):
        """直前のメッセージ中の @mention から次の発言者を決定する。"""
        shared = session.message_bus.get_shared_history()
        if not shared:
            return [session.agents[0]] if session.agents else []

        last_msg = shared[-1]
        content = last_msg.get("content", "")
        mentions = _MENTION_RE.findall(content)

        agent_map = {a.name: a for a in session.agents}
        targets = []
        for name in mentions:
            if name in agent_map and not session.agent_contexts[name]["done"]:
                if agent_map[name] not in targets:
                    targets.append(agent_map[name])

        if not targets:
            return self._select_next_agents_round_robin(session)
        return targets

    def _select_next_agents_free(self, session):
        """全エージェント（done でないもの）を返す。"""
        return [
            a for a in session.agents
            if not session.agent_contexts[a.name]["done"]
        ]

    def _select_next_agents(self, session):
        if session.orchestration == "directed":
            return self._select_next_agents_directed(session)
        elif session.orchestration == "free":
            return self._select_next_agents_free(session)
        else:
            return self._select_next_agents_round_robin(session)

    # ------------------------------------------------------------------
    # 1エージェントのターン実行
    # ------------------------------------------------------------------

    def _run_agent_turn(self, agent_def, session):
        """1エージェントの1ターンを実行し、応答を返す。"""
        ctx = session.agent_contexts[agent_def.name]
        ctx["status"] = "thinking"

        messages = self._build_messages_for_agent(agent_def, session)
        ai_result = self._ai_complete(messages, agent_def.model, agent_def.tools)
        parsed = self._parse_ai_response(ai_result)

        if parsed["type"] == "error":
            ctx["status"] = "error"
            return {"agent": agent_def.name, "type": "error", "content": parsed["content"]}

        if parsed["type"] == "tool_call":
            tool_summary = (
                "I need to call tool '"
                + parsed["tool_name"]
                + "' with args: "
                + str(parsed["tool_args"])
            )
            session.message_bus.post_shared(agent_def.name, tool_summary, session.current_turn)
            ctx["status"] = "idle"
            ctx["turns_taken"] += 1
            return {
                "agent": agent_def.name,
                "type": "tool_call",
                "content": tool_summary,
                "tool_name": parsed["tool_name"],
                "tool_args": parsed["tool_args"],
            }

        content = parsed["content"]

        mentions = _MENTION_RE.findall(content)
        agent_names = {a.name for a in session.agents}
        directed_targets = [m for m in mentions if m in agent_names and m != agent_def.name]

        if directed_targets:
            for target in directed_targets:
                session.message_bus.post_direct(
                    agent_def.name, target, content, session.current_turn
                )
        else:
            session.message_bus.post_shared(
                agent_def.name, content, session.current_turn
            )

        if DONE_MARKER in content:
            ctx["done"] = True

        ctx["status"] = "idle"
        ctx["turns_taken"] += 1
        session.updated_at = timestamp()

        return {"agent": agent_def.name, "type": "text", "content": content}

    # ------------------------------------------------------------------
    # free モード用: 並列実行
    # ------------------------------------------------------------------

    def _run_agents_parallel(self, agents, session):
        """複数エージェントを並列で実行する。"""
        results = []
        thread_agent_pairs = []

        result_lock = threading.Lock()

        def _worker(agent_def):
            r = self._run_agent_turn(agent_def, session)
            with result_lock:
                results.append(r)

        for agent_def in agents:
            t = threading.Thread(target=_worker, args=(agent_def,))
            thread_agent_pairs.append((t, agent_def))
            t.start()

        for t, _ad in thread_agent_pairs:
            t.join(timeout=120)

        # タイムアウトしたスレッドのエージェントを処理する
        agents_in_results = set()
        with result_lock:
            agents_in_results = {r["agent"] for r in results}

        for t, ad in thread_agent_pairs:
            if t.is_alive():
                session.agent_contexts[ad.name]["status"] = "timeout"
                if ad.name not in agents_in_results:
                    with result_lock:
                        results.append({
                            "agent": ad.name,
                            "type": "timeout",
                            "content": "Agent timed out after 120 seconds",
                        })

        return results

    # ------------------------------------------------------------------
    # オーケストレーション: メイン実行
    # ------------------------------------------------------------------

    def execute(self, task, agent_dicts, orchestration="round_robin", max_turns=10):
        """マルチエージェントタスクを開始し、完了まで実行する。

        Parameters
        ----------
        task : str
            タスク記述。
        agent_dicts : list[dict]
            各エージェントの定義 dict。
        orchestration : str
            "round_robin" | "directed" | "free"
        max_turns : int
            最大ターン数。

        Returns
        -------
        dict
            セッション結果。
        """
        session_id = "multi_" + gen_id()

        agents = []
        for ad in agent_dicts:
            agents.append(AgentDefinition.from_dict(ad))

        if not agents:
            return {
                "session_id": session_id,
                "status": "error",
                "error": "at least one agent is required",
            }

        session = MultiAgentSession(
            session_id=session_id,
            task=task,
            agents=agents,
            orchestration=orchestration,
            max_turns=max_turns,
        )
        session.status = "running"

        turn_results = []

        for turn in range(max_turns):
            session.current_turn = turn + 1
            session.updated_at = timestamp()

            next_agents = self._select_next_agents(session)
            if not next_agents:
                break

            if session.orchestration == "free" and len(next_agents) > 1:
                turn_res = self._run_agents_parallel(next_agents, session)
            else:
                turn_res = []
                for agent_def in next_agents:
                    r = self._run_agent_turn(agent_def, session)
                    turn_res.append(r)

            turn_results.extend(turn_res)

            all_done = all(
                session.agent_contexts[a.name]["done"] for a in session.agents
            )
            if all_done:
                break

        # --- ステータス3分岐 ---
        all_done = all(
            session.agent_contexts[a.name]["done"] for a in session.agents
        )
        if all_done:
            session.status = "completed"
        elif session.current_turn >= max_turns:
            session.status = "max_turns_reached"
        else:
            session.status = "stopped"

        final_messages = session.message_bus.get_shared_history()
        if final_messages:
            session.result = final_messages[-1].get("content", "")
        else:
            session.result = ""

        session.updated_at = timestamp()

        return {
            "session_id": session_id,
            "status": session.status,
            "session": session,
            "turn_results": turn_results,
            "result": session.to_dict(),
        }

    # ------------------------------------------------------------------
    # 外部メッセージ投入
    # ------------------------------------------------------------------

    def inject_message(self, session, message, target_agent=None):
        """実行中のセッションに外部からメッセージを投入する。"""
        if target_agent:
            agent_names = {a.name for a in session.agents}
            if target_agent not in agent_names:
                return {"status": "error", "error": "agent not found: " + target_agent}
            session.message_bus.post_direct(
                "user", target_agent, message, session.current_turn
            )
            session.agent_contexts[target_agent]["messages"].append({
                "role": "user",
                "content": "[User message]: " + message,
            })
        else:
            session.message_bus.post_shared("user", message, session.current_turn)
            for agent in session.agents:
                session.agent_contexts[agent.name]["messages"].append({
                    "role": "user",
                    "content": "[User message]: " + message,
                })

        session.updated_at = timestamp()

        return {
            "status": "ok",
            "session_id": session.session_id,
            "message": "Message injected successfully",
        }

    # ------------------------------------------------------------------
    # ステータス取得
    # ------------------------------------------------------------------

    def get_status(self, session):
        """セッションの状態を返す。"""
        return session.to_dict()
