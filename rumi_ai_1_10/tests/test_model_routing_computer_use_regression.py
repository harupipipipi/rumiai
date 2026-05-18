from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_computer_use_inference_regex_and_prefocus_symbols_remain_present():
    source = (DEFAULTSPACK_ROOT / "domain" / "chat" / "run_request.py").read_text(encoding="utf-8")
    assert "_COMPUTER_USE_REQUEST_RE" in source
    assert "_COMPUTER_USE_CHROME_TARGET_RE" in source
    assert "_COMPUTER_USE_VIVALDI_TARGET_RE" in source
    assert "_COMPUTER_USE_LINE_TARGET_RE" in source
    assert "def prefocus_computer_use_target_window" in source
    assert "computer.select_window" in source
