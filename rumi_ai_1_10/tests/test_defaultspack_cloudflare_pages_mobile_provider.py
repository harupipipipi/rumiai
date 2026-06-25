from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.webhook_url_providers.cloudflare_pages_mobile import provider as pages_provider


def _completed(args: list[str], returncode: int = 0, stdout: str = "ok") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout)


def test_cloudflare_pages_mobile_provider_deploys_project(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))
    calls: list[list[str]] = []

    def fake_run(args, *, cwd=None, input_text=None, timeout=60):
        del cwd, timeout
        calls.append(list(args))
        if "whoami" in args:
            return _completed(args, stdout="You are logged in.")
        if "secret" in args:
            assert input_text == "http://127.0.0.1:8765\n"
        return _completed(args)

    monkeypatch.setattr(pages_provider, "_run", fake_run)

    result = pages_provider.CloudflarePagesMobileProvider().create_url(
        local_url="http://127.0.0.1:8765",
        route_path="/api/mobile/v1/bootstrap",
        context={"request_data": {"project_name": "Rumi Mobile Test"}},
    )

    assert result["ok"] is True
    assert result["project_name"] == "rumi-mobile-test"
    assert result["public_url"] == "https://rumi-mobile-test.pages.dev/api/mobile/v1/bootstrap"
    assert result["private_origin_warning"] is True
    assert any(args[:5] == ["npx", "--yes", "wrangler", "pages", "project"] for args in calls)
    assert any(args[:5] == ["npx", "--yes", "wrangler", "pages", "secret"] for args in calls)
    assert any(args[:5] == ["npx", "--yes", "wrangler", "pages", "deploy"] for args in calls)

    project_root = tmp_path / "shared" / "cloudflare_pages_mobile" / "project"
    assert (project_root / "wrangler.jsonc").exists()
    function_text = (project_root / "functions" / "api" / "[[path]].js").read_text(encoding="utf-8")
    assert "/api/mobile/v1/" in function_text
    assert "/api/p2p/pairing/" in function_text

    state = pages_provider.CloudflarePagesMobileProvider().status("default")
    assert state["state"]["project_name"] == "rumi-mobile-test"


def test_cloudflare_pages_mobile_provider_requires_login(monkeypatch, tmp_path):
    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path))

    def fake_run(args, *, cwd=None, input_text=None, timeout=60):
        del cwd, input_text, timeout
        if "whoami" in args:
            return _completed(args, returncode=1, stdout="not logged in")
        return _completed(args)

    monkeypatch.setattr(pages_provider, "_run", fake_run)

    result = pages_provider.CloudflarePagesMobileProvider().create_url(
        local_url="https://origin.example.test",
        route_path="/",
        context={"request_data": {"project_name": "rumi-mobile-test"}},
    )

    assert result["ok"] is False
    assert result["needs_login"] is True
