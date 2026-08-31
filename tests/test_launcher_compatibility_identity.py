import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "tobkiri_launcher/src-tauri/tauri.conf.json"
SOURCE_SUFFIXES = set(".rs .ts .tsx .json .py .md .yml .yaml .toml .sh .mjs".split())
GENERATED_PANEL = "tobkiri_runtime/core_runtime/core_pack/core_control_panel/web/"


def _production_sources() -> dict[str, str]:
    tracked = subprocess.check_output(
        ["git", "ls-files"], cwd=ROOT, text=True
    ).splitlines()
    sources = {}
    for name in tracked:
        relative = Path(name)
        if (
            relative.suffix not in SOURCE_SUFFIXES
            or "tests" in relative.parts
            or relative.name.startswith("test_")
            or ".test." in relative.name
            or name.startswith(GENERATED_PANEL)
        ):
            continue
        payload = (ROOT / relative).read_bytes()
        assert len(payload) <= 512 * 1024, f"unbounded source: {name}"
        sources[name] = payload.decode("utf-8")
    # Hashed panel output is excluded; release builds regenerate it from scanned TS.
    return sources


def _collapsed(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "", text).lower()


def test_launcher_compatibility_identity_boundary() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert config["productName"] == "Tobkiri Launcher"
    assert config["identifier"] == "dev.rumiai.app"
    fixtures = ("dev.tobkiri.launcher", '"dev.tobkiri." + "launcher"',
                '`dev.tobkiri.${"launcher"}`', 'format!("dev.tobkiri.{}", "launcher")',
                "dev.tobkiri.launcher.ci-e2e", "dev.tobkiri.launcher.packvm-vz-helper")
    assert all("dev.tobkiri." in _collapsed(item) for item in fixtures)
    sources = _production_sources()
    # No new IDs exist yet; their future PR must add exact path+value exceptions.
    # Per-file scan; tauri config plus native bundle gates cover runtime identity.
    prefixes = ("dev.tobkiri.", "dev.tobikiri.")
    assert not any(prefix in _collapsed(text)
                   for text in sources.values() for prefix in prefixes)
    forbidden_migration = "|".join((
        "app_data_migration|.tobkiri-app-data-migration|.tobkiri-migration-complete",
        "migrate_legacy_app_data|copied legacy Rumi Viewer application data",
        "Tobkiri Launcher app identity migration",
        "legacy Rumi Viewer permissions are not copied",
    )).split("|")
    collapsed = {name: _collapsed(text) for name, text in sources.items()}
    assert not any(_collapsed(marker) in text for text in collapsed.values()
                   for marker in forbidden_migration)
    assert not (ROOT / "tobkiri_launcher/src-tauri/src/app_data_migration.rs").exists()
    assert not (ROOT / "docs/tobkiri-app-identity-migration.md").exists()
    forbidden_closure = (
        "profile_v4", "profilev4", "dispatchsession", "dispatch_session"
    )
    assert not any(marker in text for text in collapsed.values()
                   for marker in forbidden_closure)
