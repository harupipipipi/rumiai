import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from domain.agent.instruction_queue import InstructionQueue

_engines = {}
_instruction_queue = InstructionQueue()

# ---------------------------------------------------------------------------
# マルチエージェントセッション管理
# ---------------------------------------------------------------------------

_multi_sessions = {}


def get_multi_session(session_id):
    """セッションIDからマルチエージェントセッションを取得する。見つからなければ None。"""
    return _multi_sessions.get(session_id)


def set_multi_session(session_id, session):
    """マルチエージェントセッションを登録する。"""
    _multi_sessions[session_id] = session


def remove_multi_session(session_id):
    """マルチエージェントセッションを削除する。"""
    _multi_sessions.pop(session_id, None)


# ---------------------------------------------------------------------------
# エージェントエンジン管理
# ---------------------------------------------------------------------------

def get_engine(execution_id):
    return _engines.get(execution_id)


def set_engine(execution_id, engine):
    _engines[execution_id] = engine


def remove_engine(execution_id):
    _engines.pop(execution_id, None)
    _instruction_queue.clear(execution_id)


def list_engines():
    result = {}
    for eid, engine in _engines.items():
        result[eid] = engine.status(eid)
    return result


def get_instruction_queue():
    return _instruction_queue
