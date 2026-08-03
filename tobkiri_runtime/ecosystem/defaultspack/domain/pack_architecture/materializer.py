"""Selected-only, descriptor-only materialization for Shell contributions."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from .errors import ProfileResolutionError
from .resolver import ResolvedProfile


def materialize_selected_artifacts(
    resolution: ResolvedProfile,
    destination: Path,
) -> tuple[Path, ...]:
    """Copy only artifacts selected by a resolved profile.

    This helper copies signed/prebuilt descriptor inputs for conformance and
    setup preview.  It never invokes an entrypoint, installs dependencies, or
    runs a build command.  A production host may replace the copy operation with
    its verified CAS promotion while retaining the same selected artifact list.
    """
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    materialized: list[Path] = []
    materialized_sources: dict[Path, tuple[Path, str]] = {}
    for artifact in resolution.selected_artifacts:
        source = artifact.source_path.resolve()
        if not source.is_file():
            raise ProfileResolutionError(f"selected artifact disappeared: {source}")
        if artifact.digest.startswith("sha256:"):
            actual_digest = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
            if actual_digest != artifact.digest:
                raise ProfileResolutionError(
                    f"selected artifact digest changed: {artifact.artifact_id}"
                )
        artifact_ref = Path(artifact.artifact_ref)
        if ".." in artifact_ref.parts:
            # Shared contribution descriptors are owned by the provider pack
            # but stored once at the catalog root.  Keep their materialized
            # location inside the destination and preserve the original ref
            # in the manifest instead of allowing traversal components.
            target_ref = Path("contributions") / source.name
        else:
            target_ref = artifact_ref
        target = destination / artifact.pack_id / target_ref
        target = target.resolve()
        try:
            target.relative_to(destination)
        except ValueError as exc:
            raise ProfileResolutionError(
                f"artifact destination escapes materialization root: {artifact.artifact_ref}"
            ) from exc
        previous = materialized_sources.get(target)
        if previous is not None:
            if previous != (source, artifact.digest):
                raise ProfileResolutionError(
                    f"materialization target collision: {artifact.artifact_id}"
                )
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        materialized.append(target)
        materialized_sources[target] = (source, artifact.digest)
    manifest_path = destination / "materialization-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "io.tobkiri.materialization.v1",
                "profile_id": resolution.profile_id,
                "base_pack": resolution.base_pack_id,
                "shell_provider": resolution.shell_provider_id,
                "presentation_family": resolution.presentation_family,
                "selected_artifacts": [
                    {
                        "artifact_id": item.artifact_id,
                        "pack_id": item.pack_id,
                        "artifact_ref": item.artifact_ref,
                        "digest": item.digest,
                        "kind": item.kind,
                    }
                    for item in resolution.selected_artifacts
                ],
                "omitted_contributions": list(resolution.omitted_contribution_ids),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return tuple(materialized)
