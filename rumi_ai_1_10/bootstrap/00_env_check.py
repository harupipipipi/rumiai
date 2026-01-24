"""環境チェックのサンプル"""
import sys


def run(context):
    diagnostics = context.get("diagnostics")
    
    if sys.version_info < (3, 9):
        if diagnostics:
            diagnostics.record_step(
                phase="bootstrap",
                step_id="env_check.python_version",
                handler="bootstrap:env_check",
                status="failed",
                error={"type": "VersionError", "message": f"Python 3.9+ required, got {sys.version}"}
            )
        return
    
    if diagnostics:
        diagnostics.record_step(
            phase="bootstrap",
            step_id="env_check.complete",
            handler="bootstrap:env_check",
            status="success",
            meta={"python_version": sys.version}
        )
