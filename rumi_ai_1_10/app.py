import os
import atexit
import threading
import traceback
from flask import Flask, Response
from dotenv import load_dotenv

load_dotenv('.env.local')
app = Flask(__name__)

_kernel = None
_kernel_started = False
_kernel_start_lock = threading.Lock()


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

            # シャットダウンフック登録
            atexit.register(lambda: _kernel.shutdown() if _kernel else None)

            try:
                from backend_core.ecosystem.compat import mark_ecosystem_initialized
                mark_ecosystem_initialized()
            except Exception:
                pass

        except Exception as e:
            print(f"[Kernel] startup failed (fail-soft): {e}")
            traceback.print_exc()
        finally:
            _kernel_started = True


def apply_http_binders():
    if _kernel is None:
        return
    
    ir = _kernel.interface_registry
    
    try:
        binders = ir.get("io.http.binders", strategy="all") or []
        if not isinstance(binders, list):
            binders = [binders]
        for b in binders:
            if callable(b):
                try:
                    b(app, _kernel, {"app": app})
                except Exception as e:
                    _kernel.diagnostics.record_step(
                        phase="http_bind",
                        step_id=f"binder.{getattr(b, '__name__', 'unknown')}",
                        handler="app:apply_http_binders",
                        status="failed",
                        error=e,
                        meta={"binder": str(b)}
                    )
                    traceback.print_exc()
        
        routes = ir.get("io.http.routes", strategy="all") or []
        if not isinstance(routes, list):
            routes = [routes]
        for route_def in routes:
            if isinstance(route_def, dict):
                try:
                    _apply_route_definition(route_def)
                except Exception as e:
                    _kernel.diagnostics.record_step(
                        phase="http_bind",
                        step_id=f"route.{route_def.get('rule', 'unknown')}",
                        handler="app:apply_http_binders",
                        status="failed",
                        error=e,
                        meta={"route": route_def}
                    )
                    traceback.print_exc()
        
    except Exception as e:
        _kernel.diagnostics.record_step(
            phase="http_bind",
            step_id="apply_http_binders",
            handler="app:apply_http_binders",
            status="failed",
            error=e
        )
        traceback.print_exc()


def _apply_route_definition(route_def: dict):
    rule = route_def.get("rule")
    handler = route_def.get("handler")
    methods = route_def.get("methods", ["GET"])
    endpoint = route_def.get("endpoint") or f"dynamic_{abs(hash(rule or ''))}"
    
    if not rule or not callable(handler):
        return
    
    try:
        for existing_rule in app.url_map.iter_rules():
            if existing_rule.rule == rule:
                return
        
        app.add_url_rule(rule, endpoint, handler, methods=methods)
    except Exception:
        traceback.print_exc()


def _apply_fallback_index():
    if _kernel is None:
        return
    
    for rule in app.url_map.iter_rules():
        if rule.rule == '/':
            return
    
    ir = _kernel.interface_registry
    
    def _no_ui_fallback():
        registered = list((ir.list() or {}).keys())
        return Response(
            "Rumi AI OS

"
            "No root route handler registered.\n"
            "Install a pack in ecosystem/ directory that provides a root route.\n\n"
            f"Registered interfaces ({len(registered)}):\n" +
            "\n".join(f"  - {k}" for k in sorted(registered)[:20]),
            status=503,
            content_type="text/plain; charset=utf-8"
        )
    
    app.add_url_rule('/', '_no_ui_fallback', _no_ui_fallback)


class _KernelWSGIMiddleware:
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
                    _apply_fallback_index()
                    self._initialized = True

        return self._wsgi_app(environ, start_response)


app.wsgi_app = _KernelWSGIMiddleware(app.wsgi_app)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
