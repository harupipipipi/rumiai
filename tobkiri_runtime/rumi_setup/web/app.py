"""
Flask アプリケーション
"""

import webbrowser
import threading
from flask import Flask, render_template, jsonify, request

from ..core import (
    EnvironmentChecker,
    Initializer,
    Recovery,
    PackInstaller,
    AppRunner,
    get_state
)


def create_app() -> Flask:
    import os
    
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    app = Flask(__name__, template_folder=template_dir)
    
    @app.route("/")
    def index():
        return render_template("index.html")
    
    @app.route("/api/status")
    def api_status():
        state = get_state()
        return jsonify(state.to_dict())
    
    @app.route("/api/check", methods=["POST"])
    def api_check():
        def run():
            checker = EnvironmentChecker()
            checker.check_all()
        
        thread = threading.Thread(target=run)
        thread.start()
        return jsonify({"started": True})
    
    @app.route("/api/init", methods=["POST"])
    def api_init():
        data = request.get_json() or {}
        install_default = data.get("install_default", True)
        
        def run():
            initializer = Initializer()
            initializer.initialize(install_default=install_default)
        
        thread = threading.Thread(target=run)
        thread.start()
        return jsonify({"started": True})
    
    @app.route("/api/doctor", methods=["POST"])
    def api_doctor():
        def run():
            recovery = Recovery()
            recovery.diagnose()
        
        thread = threading.Thread(target=run)
        thread.start()
        return jsonify({"started": True})
    
    @app.route("/api/recover", methods=["POST"])
    def api_recover():
        def run():
            recovery = Recovery()
            recovery.recover(auto_fix=True)
        
        thread = threading.Thread(target=run)
        thread.start()
        return jsonify({"started": True})
    
    @app.route("/api/packs")
    def api_packs():
        installer = PackInstaller()
        return jsonify(installer.list_packs())
    
    @app.route("/api/run/check")
    def api_run_check():
        runner = AppRunner()
        return jsonify(runner.is_ready())
    
    @app.route("/api/run/command")
    def api_run_command():
        runner = AppRunner()
        return jsonify({
            "command": runner.get_run_command(),
            "ready": runner.is_ready()
        })
    
    return app


def run_web_mode(port: int = 8080):
    app = create_app()
    
    url = f"http://localhost:{port}"
    print("")
    print("╔════════════════════════════════════════════════╗")
    print("║    🌸 Rumi AI セットアップ (Web モード)      ║")
    print("╠════════════════════════════════════════════════╣")
    print(f"║    URL: {url:<36} ║")
    print("║    終了: Ctrl+C                                ║")
    print("╚════════════════════════════════════════════════╝")
    print("")
    
    def open_browser():
        webbrowser.open(url)
    
    threading.Timer(1.0, open_browser).start()
    
    app.run(host="0.0.0.0", port=port, debug=False)
