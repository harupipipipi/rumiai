use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::Command;

use sha2::{Digest, Sha256};

const APP_SOURCE_DIR: &str = "tobkiri_runtime";
const PRESENTATION_RELEASE_ROOT_ENV: &str = "TOBKIRI_PRESENTATION_RELEASE_ROOT";
const PRESENTATION_CATALOG_FILENAME: &str = "presentation_catalog.json";
const PRESENTATION_RELEASE_FILENAME: &str = "presentation_release.v4.json";
const PRESENTATION_INDEX_FILENAME: &str = "shell_artifact_index.v4.json";
const PRESENTATION_LOCK_FILENAME: &str = "shell_profile_lock.v4.json";
const RUNTIME_RESOURCE_MANIFEST: &str = "runtime-resource-manifest.v1.json";
const RUNTIME_RESOURCE_SCHEMA: &str = "io.tobkiri.runtime-resource-manifest.v1";
const CARGO_TARGET_DIR_ENV: &str = "CARGO_TARGET_DIR";
const GENERATED_RESOURCE_DIRS: &[&str] = &[
    "core_runtime/core_pack/core_control_panel/web",
    "ecosystem/defaultspack/ui",
    "bundled",
];
const CANONICAL_HOST_FILES: &[&str] = &[
    "README.md",
    "__init__.py",
    "admission.py",
    "artifact_compiler.py",
    "authority_v4.py",
    "backends.py",
    "broker.py",
    "composition.py",
    "contracts.py",
    "effects.py",
    "errors.py",
    "materialization.py",
    "models.py",
    "ports.py",
    "resources.py",
    "runtime.py",
    "shells.py",
    "triggers.py",
];

#[cfg(not(test))]
fn main() {
    println!("cargo:rerun-if-changed=splash/index.html");
    println!("cargo:rerun-if-changed=splash/tobkiri_launcher_startup_blade_cut.svg");
    println!("cargo:rerun-if-changed=src/lib.rs");
    println!("cargo:rerun-if-changed=../../pack-shell/Cargo.toml");
    println!("cargo:rerun-if-changed=../../pack-shell/src");
    println!("cargo:rerun-if-changed=../../tobkiri_runtime/app.py");
    println!("cargo:rerun-if-changed=../../tobkiri_runtime/core_runtime");
    println!("cargo:rerun-if-changed=../../tobkiri_runtime/tobkiri_host");
    println!("cargo:rerun-if-changed=../../tobkiri_runtime/ecosystem");
    println!("cargo:rerun-if-changed=../../tobkiri_runtime/flows");
    println!("cargo:rerun-if-changed=../../tobkiri_runtime/lang");
    println!("cargo:rerun-if-changed=../../tobkiri_runtime/rumi_setup");
    println!("cargo:rerun-if-changed=../../tobkiri_runtime/requirements.txt");
    println!("cargo:rerun-if-changed=bundled");
    println!("cargo:rerun-if-changed=bundled/presentation_catalog.json");
    println!("cargo:rerun-if-env-changed={PRESENTATION_RELEASE_ROOT_ENV}");
    println!("cargo:rerun-if-changed=capabilities");

    warn_legacy_defaultspack_app_bundle();
    stage_runtime_bundle().expect("failed to stage runtime bundle");
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "debug_approval_status",
            "arm_debug_approval",
            "revoke_debug_approval",
            "coding_approval_operator",
            "get_presentation_catalog",
            "select_presentation",
            "launch_selected_presentation",
        ]),
    ))
    .expect("failed to build Tauri application manifest")
}

#[cfg(test)]
fn main() {}

fn warn_legacy_defaultspack_app_bundle() {
    let Some(home) = std::env::var_os("HOME").map(PathBuf::from) else {
        return;
    };
    let legacy_app = home.join("Applications").join("Rumi_Defaultspack.app");
    if !legacy_app.exists() {
        return;
    }

    let launch = fs::read_to_string(legacy_app.join("Contents").join("MacOS").join("launch"))
        .unwrap_or_default();
    let missing_markers = [
        "--api-token",
        "--port",
        "RUMI_LOG_DIR",
        "RUMI_DEFAULTSPACK_OPEN_BROWSER",
    ]
    .into_iter()
    .filter(|marker| !launch.contains(marker))
    .collect::<Vec<_>>();
    if missing_markers.is_empty() {
        println!(
            "cargo:warning=legacy underscore-named Defaultspack app bundle detected at {}; re-register Defaultspack from Rumi Viewer to clean it up",
            legacy_app.display()
        );
    } else {
        println!(
            "cargo:warning=legacy Defaultspack app bundle detected at {}; missing launch markers: {}; re-register Defaultspack from Rumi Viewer or remove the legacy bundle",
            legacy_app.display(),
            missing_markers.join(", ")
        );
    }
}

fn stage_runtime_bundle() -> io::Result<()> {
    let project_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = project_dir
        .parent()
        .and_then(Path::parent)
        .expect("src-tauri should live under tobkiri_launcher/");
    let runtime_root = repo_root.join(APP_SOURCE_DIR);
    let staged_root = project_dir.join("gen").join("app");

    reset_dir(&staged_root).map_err(|error| stage_error("reset staged runtime", error))?;
    if !copy_tracked_runtime_tree(repo_root, &staged_root)
        .map_err(|error| stage_error("copy tracked runtime", error))?
    {
        return Err(stage_error(
            "copy tracked runtime",
            io::Error::new(
                io::ErrorKind::NotFound,
                "git tracked runtime inventory is unavailable",
            ),
        ));
    }
    verify_canonical_host_package(&staged_root)
        .map_err(|error| stage_error("verify canonical Host package", error))?;
    copy_generated_resource_dirs(&runtime_root, &staged_root)
        .map_err(|error| stage_error("copy generated resources", error))?;
    stage_setup_brand_icon(repo_root, &staged_root)
        .map_err(|error| stage_error("stage setup brand icon", error))?;

    let bundled_src = project_dir.join("bundled");
    if !bundled_src.is_dir() {
        return Err(stage_error(
            "locate Launcher bundled resources",
            io::Error::new(
                io::ErrorKind::NotFound,
                format!(
                    "bundled resource directory is missing at {}",
                    bundled_src.display()
                ),
            ),
        ));
    }
    copy_dir_recursive(&bundled_src, &staged_root.join("bundled"))
        .map_err(|error| stage_error("copy Launcher bundled resources", error))?;
    let bundled_catalog = bundled_src.join(PRESENTATION_CATALOG_FILENAME);
    let staged_catalog = staged_root
        .join("bundled")
        .join(PRESENTATION_CATALOG_FILENAME);
    let catalog_source = stage_presentation_release(&staged_root)
        .map_err(|error| stage_error("stage verified presentation artifact", error))?
        .unwrap_or(bundled_catalog);
    verify_staged_catalog(&catalog_source, &staged_catalog)
        .map_err(|error| stage_error("verify staged presentation catalog", error))?;

    stage_pack_shell(repo_root, &staged_root)
        .map_err(|error| stage_error("stage pack-shell", error))?;
    write_runtime_resource_manifest(&staged_root)
        .map_err(|error| stage_error("seal staged runtime", error))?;

    Ok(())
}

fn collect_runtime_resource_files(root: &Path, current: &Path) -> io::Result<Vec<PathBuf>> {
    let mut files = Vec::new();
    for entry in fs::read_dir(current)? {
        let entry = entry?;
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path)?;
        if metadata.file_type().is_symlink() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!(
                    "staged runtime resource may not be a symlink: {}",
                    path.display()
                ),
            ));
        }
        if metadata.is_dir() {
            files.extend(collect_runtime_resource_files(root, &path)?);
        } else if metadata.is_file()
            && path.file_name().and_then(|name| name.to_str()) != Some(RUNTIME_RESOURCE_MANIFEST)
        {
            files.push(path.strip_prefix(root).unwrap_or(&path).to_path_buf());
        }
    }
    files.sort();
    Ok(files)
}

fn verify_canonical_host_package(staged_root: &Path) -> io::Result<()> {
    let host_root = staged_root.join("tobkiri_host");
    let mut actual = Vec::new();
    for entry in fs::read_dir(&host_root)? {
        let entry = entry?;
        let metadata = fs::symlink_metadata(entry.path())?;
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unsafe canonical Host resource: {}", entry.path().display()),
            ));
        }
        actual.push(entry.file_name().to_string_lossy().into_owned());
    }
    actual.sort();
    let mut expected = CANONICAL_HOST_FILES
        .iter()
        .map(|name| (*name).to_owned())
        .collect::<Vec<_>>();
    expected.sort();
    if actual != expected {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "canonical Host resource inventory mismatch",
        ));
    }
    Ok(())
}

fn write_runtime_resource_manifest(staged_root: &Path) -> io::Result<()> {
    let entries = collect_runtime_resource_files(staged_root, staged_root)?
        .into_iter()
        .map(|relative| {
            let payload = fs::read(staged_root.join(&relative))?;
            Ok(serde_json::json!({
                "path": relative.to_string_lossy().replace('\\', "/"),
                "size": payload.len(),
                "sha256": format!("{:x}", Sha256::digest(&payload)),
            }))
        })
        .collect::<io::Result<Vec<_>>>()?;
    let document = serde_json::json!({
        "schema": RUNTIME_RESOURCE_SCHEMA,
        "entries": entries,
    });
    let payload = serde_json::to_vec_pretty(&document)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    fs::write(
        staged_root.join(RUNTIME_RESOURCE_MANIFEST),
        [payload, b"\n".to_vec()].concat(),
    )
}

fn stage_presentation_release(staged_root: &Path) -> io::Result<Option<PathBuf>> {
    let Some(raw_root) = std::env::var_os(PRESENTATION_RELEASE_ROOT_ENV) else {
        println!("cargo:rustc-env=TOBKIRI_PRESENTATION_TRUST_KEY_B64=");
        println!("cargo:rustc-env=TOBKIRI_PRESENTATION_TRUST_KEY_ID=");
        return Ok(None);
    };
    stage_presentation_release_at(staged_root, &PathBuf::from(raw_root))
}

fn stage_presentation_release_at(
    staged_root: &Path,
    release_root: &Path,
) -> io::Result<Option<PathBuf>> {
    require_directory(release_root, "release presentation root")?;
    let catalog = release_root.join(PRESENTATION_CATALOG_FILENAME);
    require_regular_file(&catalog, "release presentation catalog")?;

    let release_bundled = release_root.join("bundled");
    require_directory(&release_bundled, "release presentation bundle directory")?;
    let artifacts = release_bundled.join("presentation-artifacts");
    require_directory(&artifacts, "release presentation artifacts")?;
    for filename in [
        PRESENTATION_RELEASE_FILENAME,
        PRESENTATION_INDEX_FILENAME,
        PRESENTATION_LOCK_FILENAME,
    ] {
        require_regular_file(
            &release_bundled.join(filename),
            "release presentation binding file",
        )?;
    }

    let release_manifest = read_regular_file(
        &release_bundled.join(PRESENTATION_RELEASE_FILENAME),
        "release presentation manifest",
    )?;
    let release: serde_json::Value =
        serde_json::from_slice(&release_manifest).map_err(|error| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                format!("release presentation manifest is malformed: {error}"),
            )
        })?;
    let public_key = release
        .get("public_key")
        .and_then(serde_json::Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| {
            io::Error::new(io::ErrorKind::InvalidData, "release public key is missing")
        })?;
    let key_id = release
        .get("key_id")
        .and_then(serde_json::Value::as_str)
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "release key id is missing"))?;
    println!("cargo:rustc-env=TOBKIRI_PRESENTATION_TRUST_KEY_B64={public_key}");
    println!("cargo:rustc-env=TOBKIRI_PRESENTATION_TRUST_KEY_ID={key_id}");

    let staged_bundled = staged_root.join("bundled");
    copy_file(
        &catalog,
        &staged_bundled.join(PRESENTATION_CATALOG_FILENAME),
    )?;
    copy_dir_recursive(&artifacts, &staged_bundled.join("presentation-artifacts"))?;
    for filename in [
        PRESENTATION_RELEASE_FILENAME,
        PRESENTATION_INDEX_FILENAME,
        PRESENTATION_LOCK_FILENAME,
    ] {
        copy_file(
            &release_bundled.join(filename),
            &staged_bundled.join(filename),
        )?;
    }
    Ok(Some(catalog))
}

fn verify_staged_catalog(source_catalog: &Path, staged_catalog: &Path) -> io::Result<()> {
    let expected = read_regular_file(source_catalog, "source presentation catalog")?;
    let actual = read_regular_file(staged_catalog, "staged presentation catalog")?;
    if expected != actual {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!(
                "manifest-derived presentation catalog differs between {} and {}",
                source_catalog.display(),
                staged_catalog.display()
            ),
        ));
    }
    Ok(())
}

fn require_regular_file(path: &Path, label: &str) -> io::Result<()> {
    let metadata = fs::symlink_metadata(path).map_err(|error| {
        if error.kind() == io::ErrorKind::NotFound {
            io::Error::new(
                io::ErrorKind::NotFound,
                format!("{label} is missing at {}", path.display()),
            )
        } else {
            error
        }
    })?;
    if metadata.file_type().is_symlink() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("{label} may not be a symlink: {}", path.display()),
        ));
    }
    if !metadata.is_file() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("{label} must be a regular file: {}", path.display()),
        ));
    }
    Ok(())
}

fn require_directory(path: &Path, label: &str) -> io::Result<()> {
    let metadata = fs::symlink_metadata(path).map_err(|error| {
        if error.kind() == io::ErrorKind::NotFound {
            io::Error::new(
                io::ErrorKind::NotFound,
                format!("{label} is missing at {}", path.display()),
            )
        } else {
            error
        }
    })?;
    if metadata.file_type().is_symlink() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("{label} may not be a symlink: {}", path.display()),
        ));
    }
    if !metadata.is_dir() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("{label} must be a directory: {}", path.display()),
        ));
    }
    Ok(())
}

fn read_regular_file(path: &Path, label: &str) -> io::Result<Vec<u8>> {
    require_regular_file(path, label)?;
    fs::read(path)
}

fn stage_error(step: &str, error: io::Error) -> io::Error {
    io::Error::new(error.kind(), format!("{step}: {error}"))
}

fn stage_setup_brand_icon(repo_root: &Path, staged_root: &Path) -> io::Result<()> {
    let icon_source = repo_root
        .join("tobkiri_launcher")
        .join("assets")
        .join("app-icon")
        .join("tobkiri-launcher-icon.png");
    let icon_target = staged_root
        .join("core_runtime")
        .join("core_pack")
        .join("core_setup")
        .join("web")
        .join("assets")
        .join("tobkiri-launcher-icon.png");
    copy_file(&icon_source, &icon_target).map(|_| ())
}

fn stage_pack_shell(repo_root: &Path, staged_root: &Path) -> io::Result<()> {
    let Some(pack_shell) = ensure_pack_shell_binary(repo_root)? else {
        return Ok(());
    };
    let bundled_dir = staged_root.join("bundled");
    fs::create_dir_all(&bundled_dir)?;
    copy_file(&pack_shell, &bundled_dir.join(pack_shell_binary_name()))?;
    Ok(())
}

fn ensure_pack_shell_binary(repo_root: &Path) -> io::Result<Option<PathBuf>> {
    if let Some(pack_shell) = find_pack_shell_binary(repo_root)? {
        return Ok(Some(pack_shell));
    }

    let manifest = repo_root.join("pack-shell").join("Cargo.toml");
    if !manifest.is_file() {
        return Ok(None);
    }

    let cargo = std::env::var_os("CARGO").unwrap_or_else(|| "cargo".into());
    let mut command = Command::new(cargo);
    command
        .args(["build", "--locked", "--manifest-path"])
        .arg(&manifest)
        .current_dir(repo_root);

    if let Ok(target) = std::env::var("TARGET") {
        validate_path_component(&target, "Rust target")?;
        command.arg("--target").arg(&target);
    }

    if std::env::var("PROFILE").as_deref() == Ok("release") {
        command.arg("--release");
    }

    let output = command.output()?;
    if output.status.success() {
        return find_pack_shell_binary(repo_root);
    }

    Err(io::Error::other(format!(
        "failed to build pack-shell with status {}\nstdout:\n{}\nstderr:\n{}",
        output.status,
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    )))
}

fn find_pack_shell_binary(repo_root: &Path) -> io::Result<Option<PathBuf>> {
    let target = std::env::var("TARGET").ok();
    if let Some(target) = &target {
        validate_path_component(target, "Rust target")?;
    }
    let profile = std::env::var("PROFILE").unwrap_or_else(|_| "debug".to_string());
    validate_path_component(&profile, "Cargo profile")?;

    let target_dir = resolve_cargo_target_dir(repo_root)?;
    let output_dir = if let Some(target) = target {
        target_dir.join(target).join(&profile)
    } else {
        target_dir.join(&profile)
    };
    let candidate = output_dir.join(pack_shell_binary_name());

    let metadata = match fs::symlink_metadata(&candidate) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error),
    };
    if metadata.file_type().is_symlink() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!(
                "pack-shell binary may not be a symlink: {}",
                candidate.display()
            ),
        ));
    }
    if !metadata.is_file() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!(
                "pack-shell binary must be a regular file: {}",
                candidate.display()
            ),
        ));
    }

    let canonical = candidate.canonicalize()?;
    if canonical != candidate {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!(
                "pack-shell binary path is not canonical or contains a symlink: {}",
                candidate.display()
            ),
        ));
    }
    Ok(Some(canonical))
}

fn resolve_cargo_target_dir(repo_root: &Path) -> io::Result<PathBuf> {
    let repository_root = repo_root.canonicalize()?;
    let target_dir = match std::env::var_os(CARGO_TARGET_DIR_ENV) {
        Some(configured) if !configured.is_empty() => {
            let configured = PathBuf::from(configured);
            if configured.is_absolute() {
                configured
            } else {
                repository_root.join(configured)
            }
        }
        _ => repository_root.join("pack-shell").join("target"),
    };

    if target_dir.exists() {
        target_dir.canonicalize()
    } else {
        Ok(target_dir)
    }
}

fn validate_path_component(value: &str, label: &str) -> io::Result<()> {
    if value.is_empty()
        || value == "."
        || value == ".."
        || value.contains('/')
        || value.contains('\\')
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("{label} must be a single path component: {value:?}"),
        ));
    }
    Ok(())
}

fn pack_shell_binary_name() -> &'static str {
    if cfg!(target_os = "windows") {
        "pack-shell.exe"
    } else {
        "pack-shell"
    }
}

fn reset_dir(path: &Path) -> io::Result<()> {
    if path.exists() {
        clear_dir(path)?;
    } else {
        fs::create_dir_all(path)?;
    }
    Ok(())
}

fn clear_dir(path: &Path) -> io::Result<()> {
    for entry in fs::read_dir(path)? {
        let entry = entry?;
        let entry_path = entry.path();
        let file_type = entry.file_type()?;
        if file_type.is_dir() {
            clear_dir(&entry_path)?;
            fs::remove_dir(&entry_path)?;
        } else {
            fs::remove_file(&entry_path)?;
        }
    }
    Ok(())
}

fn copy_file(src: &Path, dst: &Path) -> io::Result<u64> {
    if let Some(parent) = dst.parent() {
        fs::create_dir_all(parent)?;
    }
    let bytes = fs::copy(src, dst)?;
    if let Ok(permissions) = fs::metadata(src).map(|metadata| metadata.permissions()) {
        let _ = fs::set_permissions(dst, permissions);
    }
    Ok(bytes)
}

fn copy_tracked_runtime_tree(repo_root: &Path, staged_root: &Path) -> io::Result<bool> {
    let output = match Command::new("git")
        .args(["ls-files", "-z", "--", APP_SOURCE_DIR])
        .current_dir(repo_root)
        .output()
    {
        Ok(output) => output,
        Err(_) => return Ok(false),
    };

    if !output.status.success() {
        return Ok(false);
    }

    let source_prefix = format!("{APP_SOURCE_DIR}/");
    for rel in output.stdout.split(|byte| *byte == 0) {
        if rel.is_empty() {
            continue;
        }
        let rel = String::from_utf8_lossy(rel);
        let Some(rel_under_app) = rel.strip_prefix(&source_prefix) else {
            continue;
        };
        let rel_path = Path::new(rel_under_app);
        if should_skip(rel_path, false) {
            continue;
        }
        let source_path = repo_root.join(rel.as_ref());
        let metadata = match fs::symlink_metadata(&source_path) {
            Ok(metadata) => metadata,
            Err(error) if error.kind() == io::ErrorKind::NotFound => continue,
            Err(error) => return Err(error),
        };
        if metadata.file_type().is_symlink() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("tracked runtime source may not be a symlink: {}", rel),
            ));
        }
        if !metadata.is_file() {
            continue;
        }
        copy_file(&source_path, &staged_root.join(rel_path))?;
    }

    Ok(true)
}

fn copy_generated_resource_dirs(runtime_root: &Path, staged_root: &Path) -> io::Result<()> {
    for rel_dir in GENERATED_RESOURCE_DIRS {
        let source_dir = runtime_root.join(rel_dir);
        if !source_dir.exists() {
            continue;
        }
        copy_dir_recursive_filtered(&source_dir, &staged_root.join(rel_dir), runtime_root)?;
    }
    Ok(())
}

fn copy_dir_recursive(src: &Path, dst: &Path) -> io::Result<()> {
    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let source_path = entry.path();
        let target_path = dst.join(entry.file_name());
        let file_type = entry.file_type()?;
        if file_type.is_symlink() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!(
                    "symlinked presentation release entry is not accepted: {}",
                    source_path.display()
                ),
            ));
        }
        if file_type.is_dir() {
            copy_dir_recursive(&source_path, &target_path)?;
        } else if file_type.is_file() {
            copy_file(&source_path, &target_path)?;
        } else {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!(
                    "unsupported presentation release entry: {}",
                    source_path.display()
                ),
            ));
        }
    }
    Ok(())
}

fn copy_dir_recursive_filtered(src: &Path, dst: &Path, runtime_root: &Path) -> io::Result<()> {
    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let source_path = entry.path();
        let target_path = dst.join(entry.file_name());
        let file_type = entry.file_type()?;
        let relative = source_path
            .strip_prefix(runtime_root)
            .unwrap_or(&source_path);

        if should_skip(relative, file_type.is_dir()) {
            continue;
        }

        if file_type.is_symlink() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!(
                    "generated runtime resource may not be a symlink: {}",
                    source_path.display()
                ),
            ));
        }

        if file_type.is_dir() {
            copy_dir_recursive_filtered(&source_path, &target_path, runtime_root)?;
        } else if file_type.is_file() {
            copy_file(&source_path, &target_path)?;
        }
    }
    Ok(())
}

fn should_skip(relative: &Path, is_dir: bool) -> bool {
    let Some(first) = relative.components().next().map(|c| c.as_os_str()) else {
        return false;
    };

    let first = first.to_str();
    if matches!(
        first,
        Some(".env")
            | Some(".env.local")
            | Some(".backups")
            | Some(".backup_dead_code_removal")
            | Some("chats")
            | Some("tenpu")
            | Some("tests")
            | Some("user_data")
            | Some("userdata")
            | Some("venv")
    ) {
        return true;
    }

    if matches!(
        first,
        Some(".git")
            | Some(".mypy_cache")
            | Some(".pytest_cache")
            | Some(".ruff_cache")
            | Some(".rumi_snapshots")
            | Some(".venv")
            | Some("docs")
    ) {
        return true;
    }

    if relative.components().any(|component| {
        matches!(
            component.as_os_str().to_str(),
            Some("__pycache__")
                | Some(".pytest_cache")
                | Some(".ruff_cache")
                | Some(".rumi_snapshots")
                | Some(".venv")
                | Some("node_modules")
                | Some("target")
                | Some("user_data")
                | Some("userdata")
        )
    }) {
        return true;
    }

    if !is_dir {
        if relative.file_name().and_then(|name| name.to_str()) == Some(".DS_Store") {
            return true;
        }
        if matches!(
            relative.extension().and_then(|ext| ext.to_str()),
            Some("bak") | Some("pyc") | Some("pyo") | Some("zip")
        ) {
            return true;
        }
    }

    if first == Some("frontend") {
        let second = relative.components().nth(1).map(|c| c.as_os_str());
        if matches!(
            second.and_then(|part| part.to_str()),
            Some("node_modules") | Some(".vite-temp")
        ) {
            return true;
        }

        if !is_dir
            && matches!(
                relative.extension().and_then(|ext| ext.to_str()),
                Some("tsbuildinfo")
            )
        {
            return true;
        }
    }

    false
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::OsString;
    use std::sync::Mutex;
    use std::time::{SystemTime, UNIX_EPOCH};

    static ENVIRONMENT_LOCK: Mutex<()> = Mutex::new(());

    struct TestTree {
        root: PathBuf,
    }

    impl TestTree {
        fn new(label: &str) -> Self {
            let nonce = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("system clock must be after the Unix epoch")
                .as_nanos();
            let root = std::env::temp_dir().join(format!(
                "tobkiri-build-script-{label}-{}-{nonce}",
                std::process::id()
            ));
            fs::create_dir_all(&root).expect("test tree should be creatable");
            Self { root }
        }

        fn path(&self) -> &Path {
            &self.root
        }
    }

    impl Drop for TestTree {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.root);
        }
    }

    struct EnvironmentGuard {
        key: &'static str,
        previous: Option<OsString>,
    }

    impl EnvironmentGuard {
        fn set_value(key: &'static str, value: &str) -> Self {
            let previous = std::env::var_os(key);
            std::env::set_var(key, value);
            Self { key, previous }
        }

        fn set_path(key: &'static str, value: &Path) -> Self {
            let previous = std::env::var_os(key);
            std::env::set_var(key, value);
            Self { key, previous }
        }
    }

    impl Drop for EnvironmentGuard {
        fn drop(&mut self) {
            if let Some(value) = &self.previous {
                std::env::set_var(self.key, value);
            } else {
                std::env::remove_var(self.key);
            }
        }
    }

    fn write_pack_shell_fixture(root: &Path, target: &str, profile: &str) -> PathBuf {
        let binary = root
            .join(target)
            .join(profile)
            .join(pack_shell_binary_name());
        fs::create_dir_all(binary.parent().expect("fixture binary has a parent"))
            .expect("fixture binary directory should be creatable");
        fs::write(&binary, b"pack-shell fixture").expect("fixture binary should be writable");
        binary
    }

    #[test]
    fn pack_shell_lookup_resolves_default_absolute_and_relative_target_dirs() {
        let _environment_lock = ENVIRONMENT_LOCK
            .lock()
            .expect("environment test lock should not be poisoned");
        let tree = TestTree::new("pack-shell-target-dir");
        let target = "aarch64-apple-darwin";
        let profile = "release";
        let _target = EnvironmentGuard::set_value("TARGET", target);
        let _profile = EnvironmentGuard::set_value("PROFILE", profile);

        {
            let _target_dir = EnvironmentGuard::set_value(CARGO_TARGET_DIR_ENV, "");
            let binary = write_pack_shell_fixture(
                &tree.path().join("pack-shell").join("target"),
                target,
                profile,
            );
            assert_eq!(
                find_pack_shell_binary(tree.path()).expect("default lookup should succeed"),
                Some(binary.canonicalize().expect("fixture should canonicalize"))
            );
        }

        {
            let target_dir = tree.path().join("absolute-target");
            let _target_dir = EnvironmentGuard::set_path(CARGO_TARGET_DIR_ENV, &target_dir);
            let binary = write_pack_shell_fixture(&target_dir, target, profile);
            assert_eq!(
                find_pack_shell_binary(tree.path()).expect("absolute lookup should succeed"),
                Some(binary.canonicalize().expect("fixture should canonicalize"))
            );
        }

        {
            let _target_dir = EnvironmentGuard::set_value(CARGO_TARGET_DIR_ENV, "relative-target");
            let binary =
                write_pack_shell_fixture(&tree.path().join("relative-target"), target, profile);
            assert_eq!(
                find_pack_shell_binary(tree.path()).expect("relative lookup should succeed"),
                Some(binary.canonicalize().expect("fixture should canonicalize"))
            );
        }
    }

    #[test]
    fn pack_shell_lookup_rejects_missing_wrong_and_traversing_binary_paths() {
        let _environment_lock = ENVIRONMENT_LOCK
            .lock()
            .expect("environment test lock should not be poisoned");
        let tree = TestTree::new("pack-shell-invalid-paths");
        let target = "aarch64-apple-darwin";
        let _target = EnvironmentGuard::set_value("TARGET", target);
        let _profile = EnvironmentGuard::set_value("PROFILE", "release");
        let target_dir = tree.path().join("target");
        let _target_dir = EnvironmentGuard::set_path(CARGO_TARGET_DIR_ENV, &target_dir);

        write_pack_shell_fixture(&target_dir, target, "debug");
        assert!(find_pack_shell_binary(tree.path())
            .expect("wrong profile lookup should not error")
            .is_none());

        let invalid_target = EnvironmentGuard::set_value("TARGET", "../escape");
        let error = find_pack_shell_binary(tree.path())
            .expect_err("target path traversal must be rejected");
        assert_eq!(error.kind(), io::ErrorKind::InvalidInput);
        drop(invalid_target);
    }

    #[cfg(unix)]
    #[test]
    fn pack_shell_lookup_rejects_symlinked_binary() {
        let _environment_lock = ENVIRONMENT_LOCK
            .lock()
            .expect("environment test lock should not be poisoned");
        let tree = TestTree::new("pack-shell-symlink");
        let target = "aarch64-apple-darwin";
        let _target = EnvironmentGuard::set_value("TARGET", target);
        let _profile = EnvironmentGuard::set_value("PROFILE", "release");
        let target_dir = tree.path().join("target");
        let _target_dir = EnvironmentGuard::set_path(CARGO_TARGET_DIR_ENV, &target_dir);
        let binary = target_dir
            .join(target)
            .join("release")
            .join(pack_shell_binary_name());
        fs::create_dir_all(binary.parent().expect("fixture binary has a parent"))
            .expect("fixture binary directory should be creatable");
        let outside = tree.path().join("outside-pack-shell");
        fs::write(&outside, b"outside fixture").expect("outside fixture should be writable");
        std::os::unix::fs::symlink(&outside, &binary).expect("binary symlink should be creatable");

        let error =
            find_pack_shell_binary(tree.path()).expect_err("symlinked binary must be rejected");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
    }

    fn release_fixture(tree: &TestTree) -> (PathBuf, PathBuf, PathBuf) {
        let release_root = tree.path().join("release");
        let artifacts = release_root.join("bundled").join("presentation-artifacts");
        let staged_root = tree.path().join("staged");
        let catalog = release_root.join(PRESENTATION_CATALOG_FILENAME);
        fs::create_dir_all(&artifacts).expect("release artifacts should be creatable");
        fs::create_dir_all(staged_root.join("bundled")).expect("staged bundle should be creatable");
        fs::write(&catalog, b"verified presentation catalog")
            .expect("release catalog should be writable");
        fs::write(
            release_root.join("bundled").join(PRESENTATION_RELEASE_FILENAME),
            br#"{"key_id":"fixture-key","public_key":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}"#,
        )
        .expect("release manifest should be writable");
        fs::write(
            release_root
                .join("bundled")
                .join(PRESENTATION_INDEX_FILENAME),
            b"fixture index",
        )
        .expect("release index should be writable");
        fs::write(
            release_root
                .join("bundled")
                .join(PRESENTATION_LOCK_FILENAME),
            b"fixture lock",
        )
        .expect("release lock should be writable");
        fs::write(artifacts.join("verified-shell"), b"verified shell artifact")
            .expect("release artifact should be writable");
        (release_root, staged_root, catalog)
    }

    fn host_fixture(tree: &TestTree) -> PathBuf {
        let staged_root = tree.path().join("staged-host");
        let host_root = staged_root.join("tobkiri_host");
        fs::create_dir_all(&host_root).expect("Host package should be creatable");
        for filename in CANONICAL_HOST_FILES {
            fs::write(host_root.join(filename), b"canonical Host resource")
                .expect("Host resource should be writable");
        }
        staged_root
    }

    #[test]
    fn canonical_host_inventory_is_exact() {
        let tree = TestTree::new("host-inventory");
        let staged_root = host_fixture(&tree);
        verify_canonical_host_package(&staged_root).expect("exact Host package should be accepted");

        fs::write(staged_root.join("tobkiri_host/unlisted.py"), b"pass\n")
            .expect("unlisted resource should be writable");
        assert!(verify_canonical_host_package(&staged_root).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn canonical_host_inventory_rejects_symlink() {
        let tree = TestTree::new("host-symlink");
        let staged_root = host_fixture(&tree);
        let runtime = staged_root.join("tobkiri_host/runtime.py");
        fs::remove_file(&runtime).expect("runtime fixture should be removable");
        std::os::unix::fs::symlink(tree.path(), &runtime)
            .expect("Host symlink should be creatable");
        assert!(verify_canonical_host_package(&staged_root).is_err());
    }

    #[test]
    fn release_stage_then_verify_uses_exact_catalog_file_paths() {
        let tree = TestTree::new("stage-verify");
        let (release_root, staged_root, catalog) = release_fixture(&tree);

        let _release_root =
            EnvironmentGuard::set_path(PRESENTATION_RELEASE_ROOT_ENV, &release_root);
        let source_catalog = stage_presentation_release(&staged_root)
            .expect("release should stage")
            .expect("release staging should return a catalog");
        let staged_catalog = staged_root
            .join("bundled")
            .join(PRESENTATION_CATALOG_FILENAME);

        assert_eq!(source_catalog, catalog);
        assert!(source_catalog.is_file());
        assert!(staged_catalog.is_file());
        verify_staged_catalog(&source_catalog, &staged_catalog)
            .expect("staged catalog should match the release catalog");
        assert!(staged_root
            .join("bundled")
            .join("presentation-artifacts")
            .join("verified-shell")
            .is_file());
    }

    #[test]
    fn verify_rejects_missing_or_wrongly_named_catalog() {
        let tree = TestTree::new("missing-catalog");
        let source_root = tree.path().join("source");
        let staged_root = tree.path().join("staged").join("bundled");
        fs::create_dir_all(&source_root).expect("source should be creatable");
        fs::create_dir_all(&staged_root).expect("staged should be creatable");
        fs::write(source_root.join("wrong_filename.json"), b"catalog")
            .expect("wrongly named catalog should be writable");
        let staged_catalog = staged_root.join(PRESENTATION_CATALOG_FILENAME);
        fs::write(&staged_catalog, b"catalog").expect("staged catalog should be writable");

        let source_catalog = source_root.join(PRESENTATION_CATALOG_FILENAME);
        let error = verify_staged_catalog(&source_catalog, &staged_catalog)
            .expect_err("missing exact catalog filename must fail");
        assert_eq!(error.kind(), io::ErrorKind::NotFound);
        assert!(error.to_string().contains(PRESENTATION_CATALOG_FILENAME));
    }

    #[test]
    fn verify_rejects_catalog_directory_substitution() {
        let tree = TestTree::new("directory-substitution");
        let source_catalog = tree
            .path()
            .join("source")
            .join(PRESENTATION_CATALOG_FILENAME);
        let staged_catalog = tree
            .path()
            .join("staged")
            .join(PRESENTATION_CATALOG_FILENAME);
        fs::create_dir_all(source_catalog.parent().expect("source has a parent"))
            .expect("source should be creatable");
        fs::create_dir_all(staged_catalog.parent().expect("staged has a parent"))
            .expect("staged should be creatable");
        fs::create_dir_all(&source_catalog).expect("source directory substitution should work");
        fs::write(&staged_catalog, b"catalog").expect("staged catalog should be writable");

        let error = verify_staged_catalog(&source_catalog, &staged_catalog)
            .expect_err("source directory substitution must fail");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);

        fs::remove_dir(&source_catalog).expect("source directory should be removable");
        fs::write(&source_catalog, b"catalog").expect("source catalog should be writable");
        fs::remove_file(&staged_catalog).expect("staged catalog should be removable");
        fs::create_dir(&staged_catalog).expect("staged directory substitution should work");

        let error = verify_staged_catalog(&source_catalog, &staged_catalog)
            .expect_err("staged directory substitution must fail");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
    }

    #[test]
    fn verify_rejects_catalog_digest_mismatch() {
        let tree = TestTree::new("tampered-catalog");
        let source_catalog = tree
            .path()
            .join("source")
            .join(PRESENTATION_CATALOG_FILENAME);
        let staged_catalog = tree
            .path()
            .join("staged")
            .join(PRESENTATION_CATALOG_FILENAME);
        fs::create_dir_all(source_catalog.parent().expect("source has a parent"))
            .expect("source should be creatable");
        fs::create_dir_all(staged_catalog.parent().expect("staged has a parent"))
            .expect("staged should be creatable");
        fs::write(&source_catalog, br#"{"artifact":{"sha256":"sha256:good"}}"#)
            .expect("source catalog should be writable");
        fs::write(&staged_catalog, br#"{"artifact":{"sha256":"sha256:bad"}}"#)
            .expect("staged catalog should be writable");

        let error = verify_staged_catalog(&source_catalog, &staged_catalog)
            .expect_err("catalog digest mismatch must fail closed");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        assert!(error.to_string().contains("differs"));
    }

    #[cfg(unix)]
    #[test]
    fn stage_rejects_symlinked_catalog_and_artifact_paths() {
        let tree = TestTree::new("symlink-paths");
        let (release_root, staged_root, catalog) = release_fixture(&tree);
        let outside_catalog = tree.path().join("outside-catalog.json");
        fs::write(&outside_catalog, b"outside catalog").expect("outside catalog should exist");
        fs::remove_file(&catalog).expect("fixture catalog should be removable");
        std::os::unix::fs::symlink(&outside_catalog, &catalog)
            .expect("catalog symlink should be creatable");

        let error = stage_presentation_release_at(&staged_root, &release_root)
            .expect_err("symlinked release catalog must fail closed");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);

        fs::remove_file(&catalog).expect("catalog symlink should be removable");
        fs::write(&catalog, b"verified presentation catalog")
            .expect("catalog should be restorable");
        let outside_artifact = tree.path().join("outside-shell");
        fs::write(&outside_artifact, b"outside shell").expect("outside artifact should exist");
        let artifact_link = release_root
            .join("bundled")
            .join("presentation-artifacts")
            .join("escaped-shell");
        std::os::unix::fs::symlink(&outside_artifact, &artifact_link)
            .expect("artifact symlink should be creatable");

        let error = stage_presentation_release_at(&staged_root, &release_root)
            .expect_err("symlinked artifact must fail closed");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        assert!(error.to_string().contains("symlink"));
    }

    #[cfg(unix)]
    #[test]
    fn stage_rejects_release_root_symlink_path_escape() {
        let tree = TestTree::new("release-root-escape");
        let (release_root, staged_root, _) = release_fixture(&tree);
        let release_link = tree.path().join("release-link");
        std::os::unix::fs::symlink(&release_root, &release_link)
            .expect("release root symlink should be creatable");

        let error = stage_presentation_release_at(&staged_root, &release_link)
            .expect_err("release root symlink must fail closed");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        assert!(error.to_string().contains("release presentation root"));
    }
}
