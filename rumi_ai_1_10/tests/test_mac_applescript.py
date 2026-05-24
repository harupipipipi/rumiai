from __future__ import annotations

import subprocess

from rumi_ai_1_10.ecosystem.rumi_default_tools_pack.domain.computer.mac import applescript


def test_send_key_combo_uses_key_code_for_return(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(applescript.sys, "platform", "darwin")
    monkeypatch.setattr(applescript.subprocess, "run", fake_run)

    assert applescript.send_key_combo("Google Chrome", "return") is True

    script = calls[0][0][2]
    assert "key code 36" in script
    assert 'keystroke "return"' not in script

    calls.clear()
    assert applescript.send_key_combo("Google Chrome", "retrun") is True
    assert "key code 36" in calls[0][0][2]


def test_send_key_combo_keeps_modifier_key_codes(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(applescript.sys, "platform", "darwin")
    monkeypatch.setattr(applescript.subprocess, "run", fake_run)

    assert applescript.send_key_combo("Google Chrome", "cmd+a") is True

    script = calls[0][0][2]
    assert "key code 0 using {command down}" in script


def test_send_key_combo_uses_key_code_for_backspace(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(applescript.sys, "platform", "darwin")
    monkeypatch.setattr(applescript.subprocess, "run", fake_run)

    assert applescript.send_key_combo("Google Chrome", "backspace") is True

    script = calls[0][0][2]
    assert "key code 51" in script
    assert 'keystroke "backspace"' not in script
