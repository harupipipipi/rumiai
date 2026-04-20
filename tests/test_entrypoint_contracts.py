import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_root_entrypoint_targets_legacy_app_main():
    entrypoint = _read(ROOT / "rumi_ai" / "__main__.py")
    assert "_LEGACY_ROOT" in entrypoint
    assert "from rumi_ai_1_10.app import main" in entrypoint
    assert 'if __name__ == "__main__":' in entrypoint


def test_version_contract_matches_package_version():
    init_text = _read(ROOT / "rumi_ai" / "__init__.py")
    pyproject_text = _read(ROOT / "rumi_ai_1_10" / "pyproject.toml")

    init_match = re.search(r'__version__\s*=\s*"([^"]+)"', init_text)
    pyproject_match = re.search(
        r'^\s*version\s*=\s*"([^"]+)"', pyproject_text, re.MULTILINE
    )

    assert init_match, "rumi_ai.__version__ not found"
    assert pyproject_match, "project.version in pyproject.toml not found"
    assert init_match.group(1) == pyproject_match.group(1)
