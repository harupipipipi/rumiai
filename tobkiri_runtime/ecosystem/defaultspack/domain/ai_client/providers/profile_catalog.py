import json
from pathlib import Path


def profile_dir_for(provider_name, base_file):
    return (
        Path(base_file).resolve().parents[3]
        / "user_data"
        / "shared"
        / "ai_models"
        / provider_name
        / "profiles"
    )


def iter_profile_paths(profile_dir):
    if not profile_dir.exists():
        return []
    paths = []
    seen = set()
    for pattern in ("*/profile.json", "*.json"):
        for path in sorted(profile_dir.glob(pattern)):
            resolved = str(path.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            paths.append(path)
    return paths


def infer_profile_type(profile):
    metadata = profile.get("metadata", {}) or {}
    model_type = metadata.get("type") or profile.get("type")
    if model_type:
        return model_type
    model_id = (
        profile.get("model_id")
        or profile.get("model_name")
        or profile.get("model")
        or profile.get("id")
        or ""
    )
    lowered = str(model_id).lower()
    if "embedding" in lowered:
        return "embedding"
    if "image" in lowered or "vision" in lowered or "recraft" in lowered or "flux" in lowered:
        return "image_gen"
    return "chat"


def catalog_entry_from_profile(profile, provider_name):
    provider_id = profile.get("provider_id") or profile.get("provider") or provider_name
    if provider_id != provider_name:
        return None
    model_id = (
        profile.get("model_id")
        or profile.get("model_name")
        or profile.get("model")
        or profile.get("id")
        or ""
    )
    if not model_id:
        return None
    return {
        "id": "{}/{}".format(provider_name, model_id),
        "name": profile.get("display_name") or profile.get("name") or model_id,
        "provider": provider_name,
        "type": infer_profile_type(profile),
    }


def merge_curated_and_profiles(provider_name, curated_models, profile_dir):
    models = {}
    for item in curated_models:
        models[item["id"]] = dict(item)
    for path in iter_profile_paths(profile_dir):
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        entry = catalog_entry_from_profile(profile, provider_name)
        if entry:
            models[entry["id"]] = entry
    return list(models.values())
