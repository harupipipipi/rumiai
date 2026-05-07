"""defaults.coding.terminal_stream — ターミナルストリーム実行ブロック"""

from blocks._common import error, ok
from blocks.coding._approval import approval_invalid_response, approval_required, is_server_approved
from domain.coding.terminal import Terminal
from domain.safety.audit import record_attempt, record_execution, record_failure


def run(input_data, context=None):
    """コマンドをストリーム実行する（スタブ）。

    input_data:
        command (str): 実行するコマンド
        cwd (str|null, optional): 作業ディレクトリ

    returns:
        {"status":"ok","data":{"command":str,"stream_id":str,"started":true}}
    """
    command = input_data.get("command")
    if not command:
        return error("'command' is required", code="INVALID_INPUT")

    cwd = input_data.get("cwd")

    try:
        terminal = Terminal(input_data.get("workspace_root"))
        operation = "terminal.stream"
        risk = terminal.classify(command)
        record_attempt(operation, risk["risk_level"], {"command": command, "cwd": cwd})
        approved = is_server_approved(context, operation, input_data)
        if risk["approval_required"] and not approved:
            invalid = approval_invalid_response(operation, input_data, error)
            if invalid:
                return invalid
            return ok(
                approval_required(
                    operation,
                    risk["risk_level"],
                    args=input_data,
                    command=command,
                    cwd=cwd,
                    risk=risk,
                    started=False,
                )
            )
        result = terminal.stream(command, cwd=cwd, approved=approved)
        record_execution(operation, risk["risk_level"], {"command": command, "cwd": cwd})
        return ok(result)
    except Exception as e:
        record_failure("terminal.stream", "medium", str(e), {"command": command, "cwd": cwd})
        return error(str(e), code="STREAM_ERROR")
