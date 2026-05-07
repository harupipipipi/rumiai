"""defaults.coding.terminal_exec — ターミナルコマンド実行ブロック"""

from blocks._common import error, ok
from blocks.coding._approval import approval_invalid_response, approval_required, is_server_approved
from domain.coding.terminal import Terminal
from domain.safety.audit import record_attempt, record_execution, record_failure


def run(input_data, context=None):
    """コマンドを実行する。

    input_data:
        command (str): 実行するコマンド
        cwd (str|null, optional): 作業ディレクトリ
        timeout (int, optional): タイムアウト秒数（デフォルト: 30）

    returns:
        {"status":"ok","data":{"command":str,"exit_code":int,"stdout":str,"stderr":str}}
    """
    command = input_data.get("command")
    if not command:
        return error("'command' is required", code="INVALID_INPUT")

    cwd = input_data.get("cwd")
    timeout = input_data.get("timeout", 30)

    try:
        terminal = Terminal(input_data.get("workspace_root"))
        operation = "terminal.exec"
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
                    exit_code=None,
                    stdout="",
                    stderr="",
                )
            )
        result = terminal.execute(
            command,
            cwd=cwd,
            timeout=timeout,
            env=input_data.get("env"),
            approved=approved,
        )
        if result.get("exit_code") is None:
            record_failure(operation, risk["risk_level"], "not executed", {"command": command, "cwd": cwd})
        else:
            record_execution(
                operation,
                risk["risk_level"],
                {"command": command, "cwd": cwd},
                exit_code=result.get("exit_code"),
            )
        return ok(result)
    except Exception as e:
        record_failure("terminal.exec", "medium", str(e), {"command": command, "cwd": cwd})
        return error(str(e), code="EXEC_ERROR")
