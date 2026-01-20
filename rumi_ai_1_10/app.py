import os
import threading
import traceback
from flask import Flask, render_template, send_from_directory
from dotenv import load_dotenv

load_dotenv('.env.local')
app = Flask(__name__)

_kernel = None
_kernel_started = False
_kernel_start_lock = threading.Lock()

# --- Kernel bootstrap (lazy, pre-routing) ---

def ensure_kernel_started():
    global _kernel, _kernel_started
    if _kernel_started:
        return
    with _kernel_start_lock:
        if _kernel_started:
            return
        try:
            from core_runtime import Kernel
            _kernel = Kernel()
            _kernel.run_startup()

            # compat 追随（fail-soft）。将来はKernel handler側へ寄せて app.py から消せる。
            try:
                from backend_core.ecosystem.compat import mark_ecosystem_initialized
                mark_ecosystem_initialized()
            except Exception:
                pass

        except Exception as e:
            # fail-soft: 起動失敗でもプロセスは立てる（diagnosticsは /api/diagnostics 側で見える想定）
            print(f"[Kernel] startup failed (fail-soft): {e}")
            traceback.print_exc()
        finally:
            _kernel_started = True


def apply_http_binders():
    """
    ecosystem が登録する io.http.binders を適用する（idempotent前提）。
    """
    if _kernel is None:
        return
    try:
        binders = _kernel.interface_registry.get("io.http.binders", strategy="all") or []
        if not isinstance(binders, list):
            binders = [binders]
        for b in binders:
            if callable(b):
                try:
                    b(app, _kernel, {"app": app})
                except Exception:
                    traceback.print_exc()
    except Exception:
        traceback.print_exc()


class _KernelWSGIMiddleware:
    """
    WSGI入口で Kernel startup + HTTP bind を実行し、初回リクエストの404を防ぐ。
    """
    def __init__(self, wsgi_app):
        self._wsgi_app = wsgi_app
        self._init_lock = threading.Lock()
        self._initialized = False

    def __call__(self, environ, start_response):
        if not self._initialized:
            with self._init_lock:
                if not self._initialized:
                    ensure_kernel_started()
                    apply_http_binders()
                    self._initialized = True

        # 段階的に binder が増えても良いよう、毎回軽く試す（idempotent前提）
        apply_http_binders()
        return self._wsgi_app(environ, start_response)


app.wsgi_app = _KernelWSGIMiddleware(app.wsgi_app)

# --- Frontend static files ---

@app.route('/frontend/<path:filename>')
def frontend_static(filename):
    """ecosystem/default/frontend/ から静的ファイルを配信"""
    return send_from_directory('ecosystem/default/frontend', filename)

# --- UI routes only (official keeps UI shell only) ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/chats/<chat_id>')
def show_chat(chat_id):
    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True, port=5000)
