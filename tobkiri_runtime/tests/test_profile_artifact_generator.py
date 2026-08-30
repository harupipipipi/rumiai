"""Contract tests for author intent and generated Named Profile artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from ecosystem.defaultspack.domain.runtime_v4 import BundledCatalog
from scripts import generate_profile_artifacts as generator
from tobkiri_protocol.canonical import canonical_digest
from tobkiri_protocol.validation import validate_document


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "ecosystem" / "defaultspack" / "v4"


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _copy_bundle(tmp_path: Path) -> Path:
    target = tmp_path / "v4"
    shutil.copytree(BUNDLE, target)
    return target


def _paths(bundle: Path) -> dict[str, Path]:
    return {
        "intent": bundle / "defaults.profile.intent.v1.json",
        "compatibility": bundle / "defaults.profile.v4.json",
        "lock": bundle / "defaults.profile.lock.v5.json",
        "provenance": bundle / "defaults.release.provenance.json",
    }


def _render(bundle: Path) -> dict[Path, bytes]:
    paths = _paths(bundle)
    return generator.render(
        bundle_root=bundle,
        intent_path=paths["intent"],
        compatibility_path=paths["compatibility"],
        lock_path=paths["lock"],
        provenance_path=paths["provenance"],
    )


def _check(bundle: Path) -> int:
    paths = _paths(bundle)
    return generator.main(
        [
            "--bundle-root",
            str(bundle),
            "--intent",
            str(paths["intent"]),
            "--compatibility-profile",
            str(paths["compatibility"]),
            "--lock",
            str(paths["lock"]),
            "--provenance",
            str(paths["provenance"]),
            "--check",
        ]
    )


def _publish(rendered: dict[Path, bytes]) -> None:
    for path, raw in rendered.items():
        path.write_bytes(raw)


def test_checked_in_profile_artifacts_are_deterministic_and_schema_valid() -> None:
    rendered = _render(BUNDLE)
    assert all(path.read_bytes() == raw for path, raw in rendered.items())

    intent = validate_document(
        (BUNDLE / "defaults.profile.intent.v1.json").read_bytes(),
        "profile_intent",
    )
    compatibility = validate_document((BUNDLE / "defaults.profile.v4.json").read_bytes(), "profile")
    lock = validate_document(
        (BUNDLE / "defaults.profile.lock.v5.json").read_bytes(),
        "profile_artifact_lock",
    )
    provenance = validate_document(
        (BUNDLE / "defaults.release.provenance.json").read_bytes(),
        "profile_release_provenance",
    )

    assert "provenance" not in intent
    assert intent["intent_api_version"] == "io.tobkiri.profile-intent.v1"
    assert compatibility["provenance"]["source_path"].endswith("defaults.profile.intent.v1.json")
    assert lock["profile_revision"] == canonical_digest(compatibility)
    assert lock["activation_authority"] == "unbound"
    assert lock["profile_definition_digest"] == canonical_digest(intent)
    assert lock["closure_digest"] == canonical_digest(lock["effective_set"])
    assert lock["lock_digest"] == canonical_digest(
        {key: value for key, value in lock.items() if key != "lock_digest"}
    )
    assert len(lock["effective_set"]) > len(intent["packs"])
    assert lock["variant_pins"]
    assert provenance["profile_revision"] == lock["profile_revision"]
    assert provenance["release_digest"] == canonical_digest(
        {key: value for key, value in provenance.items() if key != "release_digest"}
    )


def test_roundtrip_preserves_bundle_compatibility_and_output_bytes(tmp_path: Path) -> None:
    bundle = _copy_bundle(tmp_path)
    first = _render(bundle)
    _publish(first)
    second = _render(bundle)
    assert first == second
    assert BundledCatalog.load(bundle).profiles.keys() == {"defaults"}

    bundle_lock = json.loads((bundle / "bundle.lock.json").read_text())
    compatibility = bundle / "defaults.profile.v4.json"
    entry = next(item for item in bundle_lock["entries"] if item["path"] == compatibility.name)
    assert entry["digest"] == _sha256(compatibility.read_bytes())


@pytest.mark.parametrize(
    "artifact_name",
    [
        "defaults.profile.v4.json",
        "defaults.profile.lock.v5.json",
        "defaults.release.provenance.json",
    ],
)
def test_check_fails_closed_on_generated_artifact_tamper(
    tmp_path: Path, artifact_name: str
) -> None:
    bundle = _copy_bundle(tmp_path)
    _publish(_render(bundle))
    artifact = bundle / artifact_name
    artifact.write_bytes(artifact.read_bytes() + b" ")
    assert _check(bundle) == 1


def test_check_fails_closed_on_intent_drift_and_catalog_tamper(tmp_path: Path) -> None:
    bundle = _copy_bundle(tmp_path)
    _publish(_render(bundle))
    intent_path = bundle / "defaults.profile.intent.v1.json"
    intent = json.loads(intent_path.read_text())
    intent["display_name"] = "Changed Named Profile"
    intent_path.write_text(json.dumps(intent, indent=2) + "\n")
    assert _check(bundle) == 1
    expected = _render(bundle)
    assert (
        expected[bundle / "defaults.profile.v4.json"]
        != (bundle / "defaults.profile.v4.json").read_bytes()
    )

    pack_path = bundle / "packs" / "defaultspack.pack.v4.json"
    pack_path.write_bytes(pack_path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="bundle input digest changed"):
        _render(bundle)


def test_generator_applies_to_non_defaults_named_profile(tmp_path: Path) -> None:
    bundle = _copy_bundle(tmp_path)
    defaults_intent = bundle / "defaults.profile.intent.v1.json"
    named_intent = bundle / "research.profile.intent.v1.json"
    intent = json.loads(defaults_intent.read_text())
    intent["profile_id"] = "research"
    intent["display_name"] = "Research"
    named_intent.write_text(json.dumps(intent, indent=2) + "\n")

    named_compatibility = bundle / "research.profile.v4.json"
    named_lock = bundle / "research.profile.lock.v5.json"
    named_provenance = bundle / "research.release.provenance.json"
    bundle_lock_path = bundle / "bundle.lock.json"
    bundle_lock = json.loads(bundle_lock_path.read_text())
    for entry in bundle_lock["entries"]:
        if entry["path"] == "defaults.profile.v4.json":
            entry["path"] = named_compatibility.name
    bundle_lock_path.write_text(json.dumps(bundle_lock, indent=2) + "\n")
    (bundle / "defaults.profile.v4.json").rename(named_compatibility)

    rendered = generator.render(
        bundle_root=bundle,
        intent_path=named_intent,
        compatibility_path=named_compatibility,
        lock_path=named_lock,
        provenance_path=named_provenance,
    )
    profile = json.loads(rendered[named_compatibility])
    lock = json.loads(rendered[named_lock])
    assert profile["profile_id"] == "research"
    assert lock["profile_id"] == "research"
    assert lock["effective_set"]
