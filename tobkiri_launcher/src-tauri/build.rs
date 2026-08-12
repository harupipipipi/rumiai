use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};
use std::process::Command;

#[path = "src/artifact_integrity.rs"]
mod artifact_integrity;
#[path = "src/packaged_source.rs"]
mod packaged_source;
#[path = "src/packaging_toolchain.rs"]
mod packaging_toolchain;
#[allow(dead_code)]
#[path = "src/sealed_python_protocol.rs"]
mod sealed_python_protocol;

use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
#[cfg(test)]
use ed25519_dalek::Signer;
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use sha2::{Digest, Sha256};

const APP_SOURCE_DIR: &str = "tobkiri_runtime";
const PRESENTATION_RELEASE_ROOT_ENV: &str = "TOBKIRI_PRESENTATION_RELEASE_ROOT";
const PRESENTATION_CATALOG_FILENAME: &str = "presentation_catalog.json";
const PRESENTATION_RELEASE_FILENAME: &str = "presentation_release.v4.json";
const PRESENTATION_INDEX_FILENAME: &str = "shell_artifact_index.v4.json";
const PRESENTATION_LOCK_FILENAME: &str = "shell_profile_lock.v4.json";
const RUNTIME_RESOURCE_MANIFEST: &str = "runtime-resource-manifest.v1.json";
const RUNTIME_RESOURCE_SCHEMA: &str = "io.tobkiri.runtime-resource-manifest.v1";
const SEALED_PYTHON_ROOT: &str = "python-runtime";
const SEALED_PYTHON_MANIFEST: &str = "sealed-environment.v1.json";
const SEALED_PYTHON_SCHEMA: &str = "io.tobkiri.sealed-python-environment.v1";
const CARGO_TARGET_DIR_ENV: &str = "CARGO_TARGET_DIR";
const PANEL_BUILD_DIR_ENV: &str = "TOBKIRI_PANEL_BUILD_DIR";
const PANEL_RESOURCE_DIR: &str = "core_runtime/core_pack/core_control_panel/web";
const GENERATED_RESOURCE_DIRS: &[&str] = &[
    PANEL_RESOURCE_DIR,
    "ecosystem/defaultspack/ui",
    "bundled",
    "python-runtime",
];
const CANONICAL_HOST_INVENTORY: &str = "canonical-files.v1.json";
const CANONICAL_HOST_INVENTORY_SCHEMA: &str = "io.tobkiri.host-file-inventory.v1";
const PRESENTATION_CATALOG_SCHEMA: &str = "io.tobkiri.launcher.presentation-catalog.v1";
const PRESENTATION_RELEASE_SCHEMA: &str = "io.tobkiri.shell.release.v4";
const PRESENTATION_INDEX_SCHEMA: &str = "io.tobkiri.shell.artifact-index.v4";
const PRESENTATION_LOCK_SCHEMA: &str = "io.tobkiri.shell.profile-lock.v4";
const ISOLATED_MODULE_CODE: &str = "import runpy,sys;source_root=sys.argv[1];module_name=sys.argv[2];sys.path.insert(0,source_root);sys.argv=[module_name,*sys.argv[3:]];runpy.run_module(module_name,run_name='__main__',alter_sys=True)";
const ISOLATED_ENVIRONMENT_KEYS: &[&str] = &[
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "SystemRoot",
    "TEMP",
    "TMP",
    "TMPDIR",
    "USERPROFILE",
    "WINDIR",
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
    println!("cargo:rerun-if-changed=../../tobkiri_runtime/requirements.txt");
    println!("cargo:rerun-if-changed=../../tobkiri_runtime/python-runtime");
    println!("cargo:rerun-if-changed=bundled");
    println!("cargo:rerun-if-changed=bundled/presentation_catalog.json");
    println!("cargo:rerun-if-env-changed={PRESENTATION_RELEASE_ROOT_ENV}");
    println!("cargo:rerun-if-env-changed={PANEL_BUILD_DIR_ENV}");
    println!("cargo:rerun-if-changed=capabilities");

    if let Some(panel_dir) = configured_panel_build_dir(&PathBuf::from(env!("CARGO_MANIFEST_DIR")))
    {
        println!("cargo:rerun-if-changed={}", panel_dir.display());
    }

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

fn isolated_python_module_command<'a>(
    python: &'a packaging_toolchain::VerifiedTool,
    source: &packaged_source::VerifiedSourceSnapshot,
    module: &str,
) -> io::Result<packaging_toolchain::VerifiedCommand<'a>> {
    source.verify_unchanged()?;
    let mut command = python.command()?;
    command
        .env_clear()
        .args(["-I", "-B", "-c", ISOLATED_MODULE_CODE])
        .arg(".")
        .arg(module)
        .env(
            "GIT_CONFIG_GLOBAL",
            if cfg!(windows) { "NUL" } else { "/dev/null" },
        )
        .env("GIT_CONFIG_NOSYSTEM", "1");
    for key in ISOLATED_ENVIRONMENT_KEYS {
        if let Some(value) = std::env::var_os(key) {
            command.env(key, value);
        }
    }
    source.bind_command_cwd(&mut command)?;
    Ok(command)
}

fn bind_source_provenance_command(
    command: &mut packaging_toolchain::VerifiedCommand<'_>,
    _path: &Path,
) {
    command
        .arg("--source-provenance-file")
        .arg("packaging-source-provenance.v1.json");
}

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
    verify_canonical_host_package(&staged_root, &runtime_root)
        .map_err(|error| stage_error("verify canonical Host package", error))?;
    copy_generated_resource_dirs(&project_dir, &runtime_root, &staged_root)
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
    bind_sealed_python_environment(&staged_root)
        .map_err(|error| stage_error("bind sealed Python environment", error))?;
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
    files.sort_by_key(|path| portable_relative_path(path));
    Ok(files)
}

fn bind_sealed_python_environment(staged_root: &Path) -> io::Result<()> {
    reject_unsupported_sealed_python_release_target()?;
    let root = staged_root.join(SEALED_PYTHON_ROOT);
    let manifest_path = root.join(SEALED_PYTHON_MANIFEST);
    if !manifest_path.exists() {
        println!("cargo:rustc-env=TOBKIRI_SEALED_PYTHON_MANIFEST_SHA256=");
        if required_cargo_profile()? == "release" {
            return Err(io::Error::new(
                io::ErrorKind::NotFound,
                format!("release packaging requires {SEALED_PYTHON_ROOT}/{SEALED_PYTHON_MANIFEST}"),
            ));
        }
        return Ok(());
    }
    require_directory(&root, "sealed Python environment root")?;
    require_regular_file(&manifest_path, "sealed Python environment manifest")?;
    let bytes = fs::read(&manifest_path)?;
    let value: serde_json::Value = serde_json::from_slice(&bytes).map_err(|error| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            format!("sealed Python manifest is malformed: {error}"),
        )
    })?;
    let object = value.as_object().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "sealed Python manifest must be an object",
        )
    })?;
    let expected_fields = [
        "schema",
        "environment_digest",
        "platform",
        "architecture",
        "python_version",
        "package_provenance",
        "sentinels",
        "files",
    ]
    .into_iter()
    .collect::<std::collections::BTreeSet<_>>();
    let actual_fields = object
        .keys()
        .map(String::as_str)
        .collect::<std::collections::BTreeSet<_>>();
    if actual_fields != expected_fields
        || object.get("schema").and_then(serde_json::Value::as_str) != Some(SEALED_PYTHON_SCHEMA)
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "sealed Python manifest schema or exact fields are invalid",
        ));
    }
    let target = required_cargo_target()?;
    let platform = if target.contains("windows") {
        "windows"
    } else if target.contains("apple-darwin") {
        "macos"
    } else if target.contains("linux") {
        "linux"
    } else {
        return Err(io::Error::new(
            io::ErrorKind::Unsupported,
            format!("sealed Python target platform is unsupported: {target}"),
        ));
    };
    if object.get("platform").and_then(serde_json::Value::as_str) != Some(platform)
        || object
            .get("architecture")
            .and_then(serde_json::Value::as_str)
            != Some(expected_pack_shell_architecture(&target))
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "sealed Python manifest platform/architecture differs from Cargo target",
        ));
    }
    let provenance = exact_object(
        object.get("package_provenance"),
        &["kind", "package_id", "release_digest"],
        "package_provenance",
    )?;
    let required_provenance = match platform {
        "macos" => "apple-code-signature-v1",
        "windows" => "windows-authenticode-v1",
        _ => "linux-immutable-package-v1",
    };
    if provenance.get("kind").and_then(serde_json::Value::as_str) != Some(required_provenance)
        || provenance
            .get("package_id")
            .and_then(serde_json::Value::as_str)
            != Some("dev.tobkiri.launcher")
        || !valid_sha256(provenance.get("release_digest"))
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "sealed Python package provenance is invalid",
        ));
    }
    let sentinels = exact_object(
        object.get("sentinels"),
        &["stdlib_sha256", "site_packages_sha256", "native_sha256"],
        "sentinels",
    )?;
    if sentinels.values().any(|value| !valid_sha256(Some(value))) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "sealed Python sentinel identity is invalid",
        ));
    }
    let files = object
        .get("files")
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "sealed Python files must be an array",
            )
        })?;
    let environment_digest = object
        .get("environment_digest")
        .and_then(serde_json::Value::as_str)
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "environment_digest missing"))?;
    if raw_byte_digest(&serde_json::to_vec(files).map_err(io::Error::other)?) != environment_digest
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "sealed Python environment digest differs from sorted file inventory",
        ));
    }
    let mut expected_paths = Vec::new();
    for entry in files {
        let entry = entry.as_object().ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "sealed Python file entry must be an object",
            )
        })?;
        let fields = entry
            .keys()
            .map(String::as_str)
            .collect::<std::collections::BTreeSet<_>>();
        if fields
            != ["path", "size", "sha256", "executable"]
                .into_iter()
                .collect()
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "sealed Python file entry exact fields are invalid",
            ));
        }
        let relative = entry
            .get("path")
            .and_then(serde_json::Value::as_str)
            .ok_or_else(|| {
                io::Error::new(
                    io::ErrorKind::InvalidData,
                    "sealed Python file path missing",
                )
            })?;
        let relative_path = safe_release_relative_path(relative, "sealed Python file")?;
        let path = root.join(&relative_path);
        require_regular_file(&path, "sealed Python inventory file")?;
        reject_release_hardlink(&fs::metadata(&path)?, &path)?;
        let payload = fs::read(&path)?;
        if entry.get("size").and_then(serde_json::Value::as_u64) != Some(payload.len() as u64)
            || entry.get("sha256").and_then(serde_json::Value::as_str)
                != Some(raw_byte_digest(&payload).as_str())
            || entry
                .get("executable")
                .and_then(serde_json::Value::as_bool)
                .is_none()
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("sealed Python file identity drift: {relative}"),
            ));
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let metadata = fs::metadata(&path)?;
            let executable = metadata.permissions().mode() & 0o111 != 0;
            if entry.get("executable").and_then(serde_json::Value::as_bool) != Some(executable)
                || metadata.permissions().mode() & 0o022 != 0
            {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    format!("sealed Python file permissions drift: {relative}"),
                ));
            }
        }
        expected_paths.push(relative.to_string());
    }
    if !expected_paths.windows(2).all(|pair| pair[0] < pair[1]) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "sealed Python file inventory must be strictly sorted and unique",
        ));
    }
    let required_interpreter = if platform == "windows" {
        "venv/Scripts/python.exe"
    } else {
        "venv/bin/python3"
    };
    let python_version = object
        .get("python_version")
        .and_then(serde_json::Value::as_str)
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "python_version missing"))?;
    let version = python_version.split('.').collect::<Vec<_>>();
    if version.len() != 3
        || version
            .iter()
            .any(|part| part.is_empty() || !part.bytes().all(|byte| byte.is_ascii_digit()))
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "python_version must be an exact numeric patch version",
        ));
    }
    let bootstrap = if platform == "windows" {
        "venv/Lib/site-packages/tobkiri_sealed/bootstrap.py".to_string()
    } else {
        format!(
            "venv/lib/python{}.{}/site-packages/tobkiri_sealed/bootstrap.py",
            version[0], version[1]
        )
    };
    let mut required_paths = vec![
        required_interpreter,
        "app/kernel_entry.py",
        "app/defaultspack_entry.py",
        "app/host_helper_entry.py",
        "sentinels/stdlib.sha256",
        "sentinels/site-packages.sha256",
        "sentinels/native.sha256",
        "lease.v1",
    ];
    required_paths.push(&bootstrap);
    for required in required_paths {
        if expected_paths
            .binary_search_by(|path| path.as_str().cmp(required))
            .is_err()
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("sealed Python fixed layout is missing {required}"),
            ));
        }
    }
    let bootstrap_bytes = fs::read(root.join(&bootstrap))?;
    let bootstrap_text = std::str::from_utf8(&bootstrap_bytes).map_err(|error| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            format!("sealed Python bootstrap is not UTF-8: {error}"),
        )
    })?;
    sealed_python_protocol::validate_bootstrap_template(bootstrap_text).map_err(|error| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            format!("sealed Python bootstrap wire contract rejected: {error}"),
        )
    })?;
    if files
        .iter()
        .find(|entry| {
            entry.get("path").and_then(serde_json::Value::as_str) == Some(required_interpreter)
        })
        .and_then(|entry| entry.get("executable"))
        .and_then(serde_json::Value::as_bool)
        != Some(true)
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "sealed Python fixed interpreter must be executable",
        ));
    }
    let mut actual_paths = collect_runtime_resource_files(&root, &root)?
        .into_iter()
        .filter(|path| path != Path::new(SEALED_PYTHON_MANIFEST))
        .map(|path| portable_relative_path(&path))
        .collect::<Vec<_>>();
    actual_paths.sort();
    if actual_paths != expected_paths {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "sealed Python environment contains missing or extra files",
        ));
    }
    println!(
        "cargo:rustc-env=TOBKIRI_SEALED_PYTHON_MANIFEST_SHA256={}",
        raw_byte_digest(&bytes)
    );
    Ok(())
}

fn reject_unsupported_sealed_python_release_target() -> io::Result<()> {
    if required_cargo_profile()? != "release" {
        return Ok(());
    }
    let target = required_cargo_target()?;
    if !target.contains("apple-darwin") {
        return Err(io::Error::new(
            io::ErrorKind::Unsupported,
            format!(
                "release packaging is disabled for {target}: sealed Python package provenance is not implemented"
            ),
        ));
    }
    Ok(())
}

fn exact_object<'a>(
    value: Option<&'a serde_json::Value>,
    fields: &[&str],
    label: &str,
) -> io::Result<&'a serde_json::Map<String, serde_json::Value>> {
    let object = value
        .and_then(serde_json::Value::as_object)
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                format!("{label} must be an object"),
            )
        })?;
    let actual = object
        .keys()
        .map(String::as_str)
        .collect::<std::collections::BTreeSet<_>>();
    let expected = fields
        .iter()
        .copied()
        .collect::<std::collections::BTreeSet<_>>();
    if actual != expected {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("{label} exact fields are invalid"),
        ));
    }
    Ok(object)
}

fn valid_sha256(value: Option<&serde_json::Value>) -> bool {
    value
        .and_then(serde_json::Value::as_str)
        .is_some_and(|value| {
            value.len() == 64
                && value
                    .bytes()
                    .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        })
}

fn raw_byte_digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn portable_relative_path(path: &Path) -> String {
    path.to_string_lossy().replace('\\', "/")
}

fn canonical_host_files(source_root: &Path) -> io::Result<Vec<String>> {
    let inventory = source_root
        .join("tobkiri_host")
        .join(CANONICAL_HOST_INVENTORY);
    let metadata = fs::symlink_metadata(&inventory)?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "canonical Host inventory is missing or unsafe",
        ));
    }
    let document: serde_json::Value = serde_json::from_slice(&fs::read(&inventory)?)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
    let object = document.as_object().ok_or_else(|| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "canonical Host inventory must be an object",
        )
    })?;
    let mut keys = object.keys().map(String::as_str).collect::<Vec<_>>();
    keys.sort_unstable();
    if keys != ["files", "schema"]
        || object.get("schema").and_then(serde_json::Value::as_str)
            != Some(CANONICAL_HOST_INVENTORY_SCHEMA)
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "canonical Host inventory shape or schema is invalid",
        ));
    }
    let files = object
        .get("files")
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| {
            io::Error::new(
                io::ErrorKind::InvalidData,
                "canonical Host inventory files must be an array",
            )
        })?
        .iter()
        .map(|value| {
            value.as_str().map(str::to_owned).ok_or_else(|| {
                io::Error::new(
                    io::ErrorKind::InvalidData,
                    "canonical Host inventory filenames must be strings",
                )
            })
        })
        .collect::<io::Result<Vec<_>>>()?;
    let mut sorted = files.clone();
    sorted.sort();
    sorted.dedup();
    if files.is_empty()
        || files != sorted
        || !files.iter().any(|name| name == CANONICAL_HOST_INVENTORY)
        || files.iter().any(|name| {
            Path::new(name).components().count() != 1
                || matches!(
                    Path::new(name).components().next(),
                    Some(Component::CurDir | Component::ParentDir | Component::RootDir)
                )
        })
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "canonical Host inventory must be safe, sorted, unique, and self-listed",
        ));
    }
    let host_root = source_root.join("tobkiri_host");
    let mut actual_source_files = Vec::new();
    for entry in fs::read_dir(&host_root)? {
        let entry = entry?;
        let metadata = fs::symlink_metadata(entry.path())?;
        if metadata.file_type().is_symlink() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!(
                    "canonical Host source is a symlink: {}",
                    entry.path().display()
                ),
            ));
        }
        if metadata.is_file() {
            actual_source_files.push(entry.file_name().to_string_lossy().into_owned());
        }
    }
    actual_source_files.sort();
    if actual_source_files != files {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "canonical Host source inventory mismatch",
        ));
    }
    Ok(files)
}

fn verify_canonical_host_package(staged_root: &Path, source_root: &Path) -> io::Result<()> {
    let host_root = staged_root.join("tobkiri_host");
    let source_host_root = source_root.join("tobkiri_host");
    let expected = canonical_host_files(source_root)?;
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
    if actual != expected {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "canonical Host resource inventory mismatch",
        ));
    }
    for filename in expected {
        let source = source_host_root.join(&filename);
        let staged = host_root.join(&filename);
        let source_metadata = fs::symlink_metadata(&source)?;
        if source_metadata.file_type().is_symlink() || !source_metadata.is_file() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("unsafe canonical Host source: {}", source.display()),
            ));
        }
        if fs::read(&source)? != fs::read(&staged)? {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!("canonical Host resource byte mismatch: {filename}"),
            ));
        }
    }
    Ok(())
}

fn write_runtime_resource_manifest(staged_root: &Path) -> io::Result<()> {
    let entries = collect_runtime_resource_files(staged_root, staged_root)?
        .into_iter()
        .map(|relative| {
            let payload = fs::read(staged_root.join(&relative))?;
            Ok(serde_json::json!({
                "path": portable_relative_path(&relative),
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

#[derive(Debug)]
struct VerifiedPresentationRelease {
    public_key: String,
    key_id: String,
    artifact_path: PathBuf,
    artifact_ref: String,
    entrypoint: String,
    bundle_identity: String,
    platform: String,
    architecture: String,
    default_profile_sha256: String,
    defaultspack_lock_sha256: String,
}

fn invalid_release(message: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message.into())
}

fn object_field<'a>(
    object: &'a serde_json::Map<String, serde_json::Value>,
    field: &str,
    label: &str,
) -> io::Result<&'a serde_json::Value> {
    object
        .get(field)
        .ok_or_else(|| invalid_release(format!("{label} is missing field {field}")))
}

fn text_field(
    object: &serde_json::Map<String, serde_json::Value>,
    field: &str,
    label: &str,
) -> io::Result<String> {
    object_field(object, field, label)?
        .as_str()
        .filter(|value| !value.trim().is_empty())
        .map(str::to_owned)
        .ok_or_else(|| invalid_release(format!("{label} field {field} is not non-empty text")))
}

fn digest_field(
    object: &serde_json::Map<String, serde_json::Value>,
    field: &str,
    label: &str,
) -> io::Result<String> {
    let value = text_field(object, field, label)?;
    if value.len() != 71
        || !value.starts_with("sha256:")
        || !value[7..]
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err(invalid_release(format!(
            "{label} field {field} is not a canonical sha256 digest"
        )));
    }
    Ok(value)
}

fn byte_digest(bytes: &[u8]) -> String {
    format!("sha256:{:x}", Sha256::digest(bytes))
}

fn canonical_value_digest(value: &serde_json::Value, label: &str) -> io::Result<String> {
    let bytes = serde_json::to_vec(value)
        .map_err(|error| invalid_release(format!("{label} cannot be canonicalized: {error}")))?;
    Ok(byte_digest(&bytes))
}

fn safe_release_relative_path(value: &str, label: &str) -> io::Result<PathBuf> {
    let path = Path::new(value);
    if value.is_empty()
        || value.starts_with('~')
        || value.contains('\\')
        || path.is_absolute()
        || path
            .components()
            .any(|component| matches!(component, Component::ParentDir | Component::RootDir))
    {
        return Err(invalid_release(format!("{label} is unsafe: {value}")));
    }
    Ok(path.to_path_buf())
}

fn require_release_path(root: &Path, relative: &str, label: &str) -> io::Result<PathBuf> {
    let relative_path = safe_release_relative_path(relative, label)?;
    let candidate = root.join(&relative_path);
    let mut current = root.to_path_buf();
    for component in relative_path.components() {
        let Component::Normal(part) = component else {
            return Err(invalid_release(format!("{label} is unsafe: {relative}")));
        };
        current.push(part);
        if fs::symlink_metadata(&current)
            .map(|metadata| metadata.file_type().is_symlink())
            .unwrap_or(false)
        {
            return Err(invalid_release(format!(
                "{label} contains a symlink: {}",
                current.display()
            )));
        }
    }
    let root_resolved = root.canonicalize().map_err(|error| {
        invalid_release(format!("{label} release root cannot be resolved: {error}"))
    })?;
    let candidate_resolved = candidate.canonicalize().map_err(|error| {
        invalid_release(format!(
            "{label} is missing at {}: {error}",
            candidate.display()
        ))
    })?;
    if !candidate_resolved.starts_with(&root_resolved) {
        return Err(invalid_release(format!(
            "{label} escapes the release root: {relative}"
        )));
    }
    Ok(candidate)
}

fn release_artifact_digest(path: &Path) -> io::Result<(String, u64)> {
    artifact_integrity::digest_and_size(path)
}

fn release_entrypoint(artifact: &Path, entrypoint: &str) -> io::Result<PathBuf> {
    let relative = safe_release_relative_path(entrypoint, "artifact entrypoint")?;
    let candidate = if artifact.is_dir()
        && relative.components().next().and_then(|part| match part {
            Component::Normal(value) => Some(value),
            _ => None,
        }) == artifact.file_name()
    {
        artifact.join(relative.components().skip(1).collect::<PathBuf>())
    } else if artifact.is_dir() {
        artifact.join(relative)
    } else {
        artifact.to_path_buf()
    };
    require_regular_file(&candidate, "release artifact entrypoint")?;
    let artifact_parent = if artifact.is_dir() {
        artifact.canonicalize()?
    } else {
        artifact.parent().unwrap_or(artifact).canonicalize()?
    };
    if !candidate.canonicalize()?.starts_with(artifact_parent) {
        return Err(invalid_release(
            "release artifact entrypoint escapes its artifact",
        ));
    }
    Ok(candidate)
}

fn git_value(repo_root: &Path, args: &[&str], label: &str) -> io::Result<String> {
    let git = packaging_toolchain::verified_tool("git")?;
    let output = git
        .command()?
        .args(args)
        .current_dir(repo_root)?
        .output()
        .map_err(|error| invalid_release(format!("failed to read {label}: {error}")))?;
    if !output.status.success() {
        return Err(invalid_release(format!(
            "failed to read {label}: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }
    let value = String::from_utf8_lossy(&output.stdout).trim().to_owned();
    if value.is_empty() {
        return Err(invalid_release(format!("Git returned an empty {label}")));
    }
    Ok(value)
}

fn source_identity_from_remote(remote: &str) -> String {
    let without_suffix = remote.trim_end_matches('/').trim_end_matches(".git");
    for prefix in [
        "https://github.com/",
        "http://github.com/",
        "git@github.com:",
    ] {
        if let Some(repository) = without_suffix.strip_prefix(prefix) {
            return format!("github:{repository}");
        }
    }
    format!("git:{remote}")
}

fn current_source_provenance() -> io::Result<(String, String)> {
    let project_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = project_dir
        .parent()
        .and_then(Path::parent)
        .ok_or_else(|| invalid_release("src-tauri has no repository root"))?;
    let revision = git_value(
        repo_root,
        &["rev-parse", "--verify", "HEAD"],
        "source revision",
    )?;
    if revision.len() != 40
        || !revision
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err(invalid_release(format!(
            "source revision is not a full lowercase commit SHA: {revision}"
        )));
    }
    let remote = git_value(
        repo_root,
        &["config", "--get", "remote.origin.url"],
        "source identity",
    )?;
    Ok((source_identity_from_remote(&remote), revision))
}

fn expected_target() -> io::Result<(String, String)> {
    let target = std::env::var("TARGET")
        .map_err(|_| invalid_release("Cargo TARGET is missing for a release package"))?;
    let value = match target.as_str() {
        "aarch64-apple-darwin" => ("macos", "arm64"),
        "x86_64-apple-darwin" => ("macos", "x86_64"),
        "x86_64-pc-windows-msvc" => ("windows", "x86_64"),
        "x86_64-unknown-linux-gnu" => ("linux", "x86_64"),
        _ => {
            return Err(invalid_release(format!(
                "unsupported release target: {target}"
            )))
        }
    };
    Ok((value.0.to_string(), value.1.to_string()))
}

fn verify_presentation_release(release_root: &Path) -> io::Result<VerifiedPresentationRelease> {
    verify_presentation_release_at(
        release_root,
        &release_root.join(PRESENTATION_CATALOG_FILENAME),
    )
}

fn verify_presentation_release_at(
    release_root: &Path,
    catalog_path: &Path,
) -> io::Result<VerifiedPresentationRelease> {
    require_directory(release_root, "release presentation root")?;
    let index_path = release_root
        .join("bundled")
        .join(PRESENTATION_INDEX_FILENAME);
    let lock_path = release_root
        .join("bundled")
        .join(PRESENTATION_LOCK_FILENAME);
    let release_path = release_root
        .join("bundled")
        .join(PRESENTATION_RELEASE_FILENAME);
    let catalog_raw = read_regular_file(catalog_path, "release presentation catalog")?;
    let index_raw = read_regular_file(&index_path, "release presentation artifact index")?;
    let lock_raw = read_regular_file(&lock_path, "release presentation profile lock")?;
    let release_raw = read_regular_file(&release_path, "release presentation manifest")?;
    let catalog = serde_json::from_slice::<serde_json::Value>(&catalog_raw)
        .map_err(|error| invalid_release(format!("presentation catalog is malformed: {error}")))?;
    let index = serde_json::from_slice::<serde_json::Value>(&index_raw)
        .map_err(|error| invalid_release(format!("artifact index is malformed: {error}")))?;
    let lock = serde_json::from_slice::<serde_json::Value>(&lock_raw)
        .map_err(|error| invalid_release(format!("profile lock is malformed: {error}")))?;
    let release = serde_json::from_slice::<serde_json::Value>(&release_raw)
        .map_err(|error| invalid_release(format!("release manifest is malformed: {error}")))?;
    let catalog_object = catalog
        .as_object()
        .ok_or_else(|| invalid_release("presentation catalog must be an object"))?;
    let index_object = index
        .as_object()
        .ok_or_else(|| invalid_release("artifact index must be an object"))?;
    let lock_object = lock
        .as_object()
        .ok_or_else(|| invalid_release("profile lock must be an object"))?;
    let release_object = release
        .as_object()
        .ok_or_else(|| invalid_release("release manifest must be an object"))?;
    let release_fields = [
        "schema",
        "catalog_path",
        "catalog_sha256",
        "artifact_index_path",
        "artifact_index_sha256",
        "profile_lock_path",
        "profile_lock_sha256",
        "default_profile_path",
        "default_profile_sha256",
        "defaultspack_lock_path",
        "defaultspack_lock_sha256",
        "artifact_id",
        "platform",
        "architecture",
        "source_identity",
        "source_revision",
        "key_id",
        "public_key",
        "signature",
    ];
    if release_object.len() != release_fields.len()
        || release_fields
            .iter()
            .any(|field| !release_object.contains_key(*field))
    {
        return Err(invalid_release(
            "release manifest has unknown or missing fields",
        ));
    }

    if text_field(catalog_object, "schema", "presentation catalog")? != PRESENTATION_CATALOG_SCHEMA
    {
        return Err(invalid_release("presentation catalog schema is invalid"));
    }
    if text_field(release_object, "schema", "release manifest")? != PRESENTATION_RELEASE_SCHEMA
        || text_field(index_object, "schema", "artifact index")? != PRESENTATION_INDEX_SCHEMA
        || text_field(lock_object, "schema", "profile lock")? != PRESENTATION_LOCK_SCHEMA
    {
        return Err(invalid_release("v4 release binding schema is invalid"));
    }

    let release_catalog_path = text_field(release_object, "catalog_path", "release manifest")?;
    let release_index_path = text_field(release_object, "artifact_index_path", "release manifest")?;
    let release_lock_path = text_field(release_object, "profile_lock_path", "release manifest")?;
    if release_catalog_path != "bundled/presentation_catalog.json"
        || release_index_path != "bundled/shell_artifact_index.v4.json"
        || release_lock_path != "bundled/shell_profile_lock.v4.json"
    {
        return Err(invalid_release(
            "release manifest uses non-canonical v4 paths",
        ));
    }
    if text_field(release_object, "default_profile_path", "release manifest")?
        != "ecosystem/defaultspack/v4/defaults.profile.v4.json"
        || text_field(release_object, "defaultspack_lock_path", "release manifest")?
            != "ecosystem/defaultspack/v4/bundle.lock.json"
    {
        return Err(invalid_release(
            "release manifest uses non-canonical packaged Defaults paths",
        ));
    }
    let catalog_digest = digest_field(release_object, "catalog_sha256", "release manifest")?;
    let index_file_digest =
        digest_field(release_object, "artifact_index_sha256", "release manifest")?;
    let lock_file_digest = digest_field(release_object, "profile_lock_sha256", "release manifest")?;
    let default_profile_sha256 =
        digest_field(release_object, "default_profile_sha256", "release manifest")?;
    let defaultspack_lock_sha256 = digest_field(
        release_object,
        "defaultspack_lock_sha256",
        "release manifest",
    )?;
    let release_profile = require_release_path(
        release_root,
        "ecosystem/defaultspack/v4/defaults.profile.v4.json",
        "release default Profile",
    )?;
    let release_defaultspack_lock = require_release_path(
        release_root,
        "ecosystem/defaultspack/v4/bundle.lock.json",
        "release Defaults lock",
    )?;
    if catalog_digest != byte_digest(&catalog_raw)
        || index_file_digest != byte_digest(&index_raw)
        || lock_file_digest != byte_digest(&lock_raw)
    {
        return Err(invalid_release("release manifest byte digest mismatch"));
    }
    if digest_field(
        catalog_object,
        "default_profile_digest",
        "presentation catalog",
    )? != default_profile_sha256
    {
        return Err(invalid_release(
            "presentation catalog Profile identity differs from release manifest",
        ));
    }
    if byte_digest(&fs::read(release_profile)?) != default_profile_sha256
        || byte_digest(&fs::read(release_defaultspack_lock)?) != defaultspack_lock_sha256
    {
        return Err(invalid_release(
            "release packaged Defaults bytes differ from signed identities",
        ));
    }

    let binding = object_field(catalog_object, "release_binding", "presentation catalog")?
        .as_object()
        .ok_or_else(|| invalid_release("production catalog has no v4 release binding"))?;
    if text_field(binding, "schema", "catalog release binding")? != PRESENTATION_RELEASE_SCHEMA
        || text_field(binding, "artifact_index_path", "catalog release binding")?
            != "bundled/shell_artifact_index.v4.json"
        || text_field(binding, "profile_lock_path", "catalog release binding")?
            != "bundled/shell_profile_lock.v4.json"
    {
        return Err(invalid_release("catalog release binding is not canonical"));
    }
    let index_digest = digest_field(binding, "artifact_index_sha256", "catalog release binding")?;
    let lock_digest = digest_field(binding, "profile_lock_sha256", "catalog release binding")?;
    if index_digest != canonical_value_digest(&index, "artifact index")?
        || lock_digest != canonical_value_digest(&lock, "profile lock")?
    {
        return Err(invalid_release(
            "catalog v4 binding does not match index or lock",
        ));
    }
    let mut catalog_without_binding = catalog.clone();
    catalog_without_binding
        .as_object_mut()
        .expect("catalog object was checked above")
        .remove("release_binding");
    if text_field(binding, "catalog_revision", "catalog release binding")?
        != canonical_value_digest(&catalog_without_binding, "catalog")?
    {
        return Err(invalid_release("catalog revision mismatch"));
    }

    let mut lock_without_revision = lock.clone();
    lock_without_revision
        .as_object_mut()
        .expect("lock object was checked above")
        .remove("lock_revision");
    if text_field(lock_object, "lock_revision", "profile lock")?
        != canonical_value_digest(&lock_without_revision, "profile lock")?
    {
        return Err(invalid_release("profile lock revision mismatch"));
    }

    let artifact_id = text_field(release_object, "artifact_id", "release manifest")?;
    let platform = text_field(release_object, "platform", "release manifest")?;
    let architecture = text_field(release_object, "architecture", "release manifest")?;
    let source_identity = text_field(release_object, "source_identity", "release manifest")?;
    let source_revision = text_field(release_object, "source_revision", "release manifest")?;
    for field in [
        "artifact_id",
        "platform",
        "architecture",
        "source_identity",
        "source_revision",
    ] {
        let release_value = text_field(release_object, field, "release manifest")?;
        if text_field(binding, field, "catalog release binding")? != release_value
            || text_field(index_object, field, "artifact index")? != release_value
            || text_field(lock_object, field, "profile lock")? != release_value
        {
            return Err(invalid_release(format!(
                "v4 release field mismatch: {field}"
            )));
        }
    }
    #[cfg(not(test))]
    {
        let (expected_platform, expected_architecture) = expected_target()?;
        if (platform.as_str(), architecture.as_str())
            != (expected_platform.as_str(), expected_architecture.as_str())
        {
            return Err(invalid_release(
                "v4 release targets the wrong platform or architecture",
            ));
        }
    }

    let index_path_value = text_field(index_object, "path", "artifact index")?;
    let artifact_relative = safe_release_relative_path(&index_path_value, "artifact index path")?;
    if !index_path_value.starts_with("bundled/presentation-artifacts/") {
        return Err(invalid_release(
            "artifact index path is outside presentation-artifacts",
        ));
    }
    if text_field(binding, "artifact_id", "catalog release binding")? != artifact_id
        || text_field(index_object, "path", "artifact index")? != index_path_value
    {
        return Err(invalid_release("artifact identity/path binding mismatch"));
    }
    let artifact_path = require_release_path(
        release_root,
        artifact_relative.to_str().unwrap_or_default(),
        "release artifact",
    )?;
    let (artifact_digest, artifact_size) = release_artifact_digest(&artifact_path)?;
    if digest_field(index_object, "sha256", "artifact index")? != artifact_digest
        || digest_field(lock_object, "artifact_sha256", "profile lock")? != artifact_digest
        || object_field(index_object, "size", "artifact index")?.as_u64() != Some(artifact_size)
    {
        return Err(invalid_release("artifact digest or size mismatch"));
    }

    let default_selection =
        object_field(catalog_object, "default_selection", "presentation catalog")?
            .as_object()
            .ok_or_else(|| invalid_release("presentation catalog default selection is missing"))?;
    let shell_provider_id =
        text_field(default_selection, "shell_provider_id", "default selection")?;
    let shells = object_field(catalog_object, "shell_providers", "presentation catalog")?
        .as_array()
        .ok_or_else(|| invalid_release("presentation catalog Shell Providers are invalid"))?;
    let selected_shell = shells
        .iter()
        .filter_map(serde_json::Value::as_object)
        .find(|shell| {
            shell.get("provider_id").and_then(serde_json::Value::as_str)
                == Some(shell_provider_id.as_str())
        })
        .ok_or_else(|| invalid_release("default Profile Shell is missing"))?;
    let variants = object_field(selected_shell, "artifact_variants", "default Profile Shell")?
        .as_array()
        .ok_or_else(|| invalid_release("default Profile Shell artifact variants are invalid"))?;
    let selected_variant = variants
        .iter()
        .filter_map(serde_json::Value::as_object)
        .find(|variant| {
            variant
                .get("artifact_id")
                .and_then(serde_json::Value::as_str)
                == Some(artifact_id.as_str())
        })
        .ok_or_else(|| {
            invalid_release("signed artifact does not match the default Profile Shell")
        })?;
    for field in [
        "path",
        "sha256",
        "entrypoint_sha256",
        "source_identity",
        "source_revision",
    ] {
        if text_field(selected_variant, field, "selected artifact variant")?
            != text_field(index_object, field, "artifact index")?
        {
            return Err(invalid_release(format!(
                "catalog variant differs from artifact index: {field}"
            )));
        }
    }
    let entrypoint = text_field(selected_variant, "entrypoint", "selected artifact variant")?;
    let entrypoint_path = release_entrypoint(&artifact_path, &entrypoint)?;
    let entrypoint_digest = byte_digest(&fs::read(&entrypoint_path)?);
    if digest_field(index_object, "entrypoint_sha256", "artifact index")? != entrypoint_digest
        || digest_field(lock_object, "entrypoint_sha256", "profile lock")? != entrypoint_digest
    {
        return Err(invalid_release("artifact entrypoint digest mismatch"));
    }
    let artifact_ref = text_field(
        selected_variant,
        "artifact_ref",
        "selected artifact variant",
    )?;
    let bundle_identity = text_field(
        selected_variant,
        "bundle_identifier",
        "selected artifact variant",
    )?;
    if object_field(selected_variant, "size", "selected artifact variant")?.as_u64()
        != Some(artifact_size)
    {
        return Err(invalid_release(
            "catalog artifact size differs from artifact index",
        ));
    }
    if selected_variant
        .get("production")
        .and_then(serde_json::Value::as_bool)
        != Some(true)
        || selected_variant
            .get("prebuilt")
            .and_then(serde_json::Value::as_bool)
            != Some(true)
        || selected_variant
            .get("development_command")
            .and_then(serde_json::Value::as_str)
            .is_some_and(|value| !value.trim().is_empty())
    {
        return Err(invalid_release(
            "selected Shell artifact is not production-prebuilt",
        ));
    }
    if platform == "macos" {
        let bundle_identifier = text_field(
            selected_variant,
            "bundle_identifier",
            "selected artifact variant",
        )?;
        if artifact_path
            .extension()
            .and_then(|extension| extension.to_str())
            .is_none_or(|extension| extension != "app")
        {
            return Err(invalid_release(
                "macOS Shell artifact is not an .app bundle",
            ));
        }
        let plist_path = artifact_path.join("Contents").join("Info.plist");
        require_regular_file(&plist_path, "macOS Shell Info.plist")?;
        let output = Command::new("/usr/bin/plutil")
            .args([
                "-extract",
                "CFBundleIdentifier",
                "raw",
                "-o",
                "-",
                &plist_path.to_string_lossy(),
            ])
            .output()
            .map_err(|error| {
                invalid_release(format!("failed to read macOS bundle identity: {error}"))
            })?;
        if !output.status.success()
            || String::from_utf8_lossy(&output.stdout).trim() != bundle_identifier
        {
            return Err(invalid_release(
                "macOS Shell bundle identifier differs from the v4 catalog",
            ));
        }
    }

    let public_key = text_field(release_object, "public_key", "release manifest")?;
    let signature = text_field(release_object, "signature", "release manifest")?;
    let key_id = text_field(release_object, "key_id", "release manifest")?;
    let public_key_bytes: [u8; 32] = BASE64
        .decode(&public_key)
        .map_err(|error| invalid_release(format!("release public key is invalid: {error}")))?
        .try_into()
        .map_err(|_| invalid_release("release public key must be 32 bytes"))?;
    let signature_bytes: [u8; 64] = BASE64
        .decode(&signature)
        .map_err(|error| invalid_release(format!("release signature is invalid: {error}")))?
        .try_into()
        .map_err(|_| invalid_release("release signature must be 64 bytes"))?;
    let message = [
        PRESENTATION_RELEASE_SCHEMA,
        catalog_digest.as_str(),
        index_file_digest.as_str(),
        lock_file_digest.as_str(),
        default_profile_sha256.as_str(),
        defaultspack_lock_sha256.as_str(),
        source_identity.as_str(),
        source_revision.as_str(),
        platform.as_str(),
        architecture.as_str(),
        artifact_id.as_str(),
        key_id.as_str(),
    ]
    .join("\0");
    VerifyingKey::from_bytes(&public_key_bytes)
        .map_err(|error| invalid_release(format!("release public key is invalid: {error}")))?
        .verify(
            &message.into_bytes(),
            &Signature::from_bytes(&signature_bytes),
        )
        .map_err(|error| {
            invalid_release(format!("release signature verification failed: {error}"))
        })?;

    #[cfg(not(test))]
    {
        let (expected_identity, expected_revision) = current_source_provenance()?;
        if source_identity != expected_identity || source_revision != expected_revision {
            return Err(invalid_release(
                "v4 release source identity/revision is stale for this checkout",
            ));
        }
    }
    verify_release_artifact_scope(release_root, &artifact_path)?;
    Ok(VerifiedPresentationRelease {
        public_key,
        key_id,
        artifact_path,
        artifact_ref,
        entrypoint,
        bundle_identity,
        platform,
        architecture,
        default_profile_sha256,
        defaultspack_lock_sha256,
    })
}

fn is_intermediate_shell_build() -> bool {
    let Ok(raw_config) = std::env::var("TAURI_CONFIG") else {
        return false;
    };
    let Ok(config) = serde_json::from_str::<serde_json::Value>(&raw_config) else {
        return false;
    };
    config.get("identifier").and_then(serde_json::Value::as_str) == Some("io.tobkiri.shell.tauri")
        && config
            .get("mainBinaryName")
            .and_then(serde_json::Value::as_str)
            == Some("tobkiri-shell")
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ReleaseTreeEntry {
    path: String,
    directory: bool,
    size: u64,
    digest: String,
}

#[cfg(unix)]
fn reject_release_hardlink(metadata: &fs::Metadata, path: &Path) -> io::Result<()> {
    use std::os::unix::fs::MetadataExt;
    if metadata.is_file() && metadata.nlink() != 1 {
        return Err(invalid_release(format!(
            "presentation release file must have one link: {}",
            path.display()
        )));
    }
    Ok(())
}

#[cfg(windows)]
fn reject_release_hardlink(metadata: &fs::Metadata, path: &Path) -> io::Result<()> {
    use std::mem::MaybeUninit;
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::Storage::FileSystem::{
        GetFileInformationByHandle, BY_HANDLE_FILE_INFORMATION,
    };

    if !metadata.is_file() {
        return Ok(());
    }
    let file = File::open(path).map_err(|error| {
        invalid_release(format!(
            "failed to inspect presentation release file links at {}: {error}",
            path.display()
        ))
    })?;
    let mut information = MaybeUninit::<BY_HANDLE_FILE_INFORMATION>::zeroed();
    if unsafe { GetFileInformationByHandle(file.as_raw_handle(), information.as_mut_ptr()) } == 0 {
        return Err(invalid_release(format!(
            "failed to inspect presentation release file links at {}: {}",
            path.display(),
            io::Error::last_os_error()
        )));
    }
    let information = unsafe { information.assume_init() };
    if information.nNumberOfLinks != 1 {
        return Err(invalid_release(format!(
            "presentation release file must have one link: {}",
            path.display()
        )));
    }
    Ok(())
}

#[cfg(not(any(unix, windows)))]
fn reject_release_hardlink(_metadata: &fs::Metadata, _path: &Path) -> io::Result<()> {
    Ok(())
}

fn release_tree_inventory(root: &Path) -> io::Result<Vec<ReleaseTreeEntry>> {
    require_directory(root, "presentation release tree")?;
    fn visit(root: &Path, current: &Path, output: &mut Vec<ReleaseTreeEntry>) -> io::Result<()> {
        let mut entries = fs::read_dir(current)?.collect::<Result<Vec<_>, _>>()?;
        entries.sort_by_key(fs::DirEntry::file_name);
        for entry in entries {
            let path = entry.path();
            let relative = path
                .strip_prefix(root)
                .map_err(|_| invalid_release("release inventory escaped its root"))?;
            let relative_text = portable_relative_path(relative);
            let metadata = fs::symlink_metadata(&path)?;
            if metadata.file_type().is_symlink() {
                return Err(invalid_release(format!(
                    "presentation release contains a symlink: {}",
                    path.display()
                )));
            }
            reject_release_hardlink(&metadata, &path)?;
            if metadata.is_dir() {
                output.push(ReleaseTreeEntry {
                    path: relative_text,
                    directory: true,
                    size: 0,
                    digest: String::new(),
                });
                visit(root, &path, output)?;
            } else if metadata.is_file() {
                output.push(ReleaseTreeEntry {
                    path: relative_text,
                    directory: false,
                    size: metadata.len(),
                    digest: byte_digest(&read_regular_file(&path, "release snapshot file")?),
                });
            } else {
                return Err(invalid_release(format!(
                    "presentation release contains an unsupported entry: {}",
                    path.display()
                )));
            }
        }
        Ok(())
    }
    let mut output = Vec::new();
    visit(root, root, &mut output)?;
    Ok(output)
}

fn verify_release_source_shape(entries: &[ReleaseTreeEntry]) -> io::Result<()> {
    let required_files = [
        "presentation_catalog.json",
        "bundled/presentation_release.v4.json",
        "bundled/shell_artifact_index.v4.json",
        "bundled/shell_profile_lock.v4.json",
        "ecosystem/defaultspack/v4/defaults.profile.v4.json",
        "ecosystem/defaultspack/v4/bundle.lock.json",
    ];
    let required_directories = [
        "bundled",
        "bundled/presentation-artifacts",
        "ecosystem",
        "ecosystem/defaultspack",
        "ecosystem/defaultspack/v4",
    ];
    for required in required_files {
        if !entries
            .iter()
            .any(|entry| !entry.directory && entry.path == required)
        {
            return Err(invalid_release(format!(
                "presentation release is missing required file: {required}"
            )));
        }
    }
    for required in required_directories {
        if !entries
            .iter()
            .any(|entry| entry.directory && entry.path == required)
        {
            return Err(invalid_release(format!(
                "presentation release is missing required directory: {required}"
            )));
        }
    }
    let mut artifact_files = 0usize;
    for entry in entries {
        let allowed = required_files.contains(&entry.path.as_str())
            || required_directories.contains(&entry.path.as_str())
            || entry.path.starts_with("bundled/presentation-artifacts/");
        if !allowed {
            return Err(invalid_release(format!(
                "presentation release contains an extra entry: {}",
                entry.path
            )));
        }
        if !entry.directory && entry.path.starts_with("bundled/presentation-artifacts/") {
            artifact_files += 1;
        }
    }
    if artifact_files == 0 {
        return Err(invalid_release(
            "presentation release artifact tree is empty",
        ));
    }
    Ok(())
}

fn copy_release_tree(source: &Path, destination: &Path) -> io::Result<()> {
    fs::create_dir(destination)?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(destination, fs::Permissions::from_mode(0o700))?;
    }
    let mut entries = fs::read_dir(source)?.collect::<Result<Vec<_>, _>>()?;
    entries.sort_by_key(fs::DirEntry::file_name);
    for entry in entries {
        let source_path = entry.path();
        let destination_path = destination.join(entry.file_name());
        let metadata = fs::symlink_metadata(&source_path)?;
        if metadata.file_type().is_symlink() {
            return Err(invalid_release(format!(
                "presentation release snapshot source became a symlink: {}",
                source_path.display()
            )));
        }
        reject_release_hardlink(&metadata, &source_path)?;
        if metadata.is_dir() {
            copy_release_tree(&source_path, &destination_path)?;
        } else if metadata.is_file() {
            let mut input = File::open(&source_path)?;
            let opened_metadata = input.metadata()?;
            reject_release_hardlink(&opened_metadata, &source_path)?;
            let mut output = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&destination_path)?;
            io::copy(&mut input, &mut output)?;
            output.sync_all()?;
            let final_metadata = fs::symlink_metadata(&source_path)?;
            if final_metadata.file_type().is_symlink()
                || final_metadata.len() != opened_metadata.len()
                || input.metadata()?.len() != opened_metadata.len()
            {
                return Err(invalid_release(format!(
                    "presentation release source mutated during snapshot: {}",
                    source_path.display()
                )));
            }
            fs::set_permissions(&destination_path, opened_metadata.permissions())?;
        } else {
            return Err(invalid_release(format!(
                "presentation release snapshot source is unsupported: {}",
                source_path.display()
            )));
        }
    }
    Ok(())
}

fn seal_release_snapshot(root: &Path) -> io::Result<()> {
    for entry in release_tree_inventory(root)? {
        if entry.directory {
            continue;
        }
        let path = root.join(Path::new(&entry.path));
        let mut permissions = fs::metadata(&path)?.permissions();
        permissions.set_readonly(true);
        fs::set_permissions(path, permissions)?;
    }
    Ok(())
}

fn snapshot_presentation_release_with_hook<F>(
    source: &Path,
    destination: &Path,
    after_copy: F,
) -> io::Result<()>
where
    F: FnOnce(),
{
    let before = release_tree_inventory(source)?;
    verify_release_source_shape(&before)?;
    copy_release_tree(source, destination)?;
    after_copy();
    let after = release_tree_inventory(source)?;
    let snapshot = release_tree_inventory(destination)?;
    if before != after || before != snapshot {
        return Err(invalid_release(
            "presentation release source mutated or copied partially during snapshot",
        ));
    }
    seal_release_snapshot(destination)
}

fn snapshot_presentation_release(source: &Path, destination: &Path) -> io::Result<()> {
    snapshot_presentation_release_with_hook(source, destination, || {})
}

fn verify_release_artifact_scope(root: &Path, artifact: &Path) -> io::Result<()> {
    let artifact_root_path = root.join("bundled/presentation-artifacts");
    let selected = portable_relative_path(
        artifact
            .strip_prefix(&artifact_root_path)
            .map_err(|_| invalid_release("selected artifact escaped release artifact root"))?,
    );
    for entry in release_tree_inventory(&artifact_root_path)? {
        let ancestor = selected.starts_with(&format!("{}/", entry.path));
        let selected_or_descendant =
            entry.path == selected || entry.path.starts_with(&format!("{selected}/"));
        if !(ancestor || selected_or_descendant) {
            return Err(invalid_release(format!(
                "presentation release contains an extra artifact entry: {}",
                entry.path
            )));
        }
    }
    Ok(())
}

fn stage_presentation_release(staged_root: &Path) -> io::Result<Option<PathBuf>> {
    let Some(raw_root) = std::env::var_os(PRESENTATION_RELEASE_ROOT_ENV) else {
        if is_intermediate_shell_build() {
            println!(
                "cargo:warning=intermediate Tauri Shell build has no Launcher Presentation release; this binary is only an input to the sealed outer package"
            );
            println!("cargo:rustc-env=TOBKIRI_PRESENTATION_TRUST_KEY_B64=");
            println!("cargo:rustc-env=TOBKIRI_PRESENTATION_TRUST_KEY_ID=");
            return Ok(None);
        }
        if std::env::var("DEP_TAURI_DEV").ok().as_deref() != Some("true") {
            return Err(io::Error::new(
                io::ErrorKind::NotFound,
                format!("production package requires {PRESENTATION_RELEASE_ROOT_ENV}; a null-metadata presentation catalog is never a package input"),
            ));
        }
        println!("cargo:warning=development build has no sealed Presentation release; the uninstalled catalog is debug-only and cannot be packaged");
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
    let snapshot_parent = staged_root
        .parent()
        .ok_or_else(|| invalid_release("staged root has no private snapshot parent"))?;
    let snapshot_root = snapshot_parent.join(format!(
        ".tobkiri-presentation-release-snapshot-{}",
        std::process::id()
    ));
    if fs::symlink_metadata(&snapshot_root).is_ok() {
        return Err(invalid_release(format!(
            "private presentation snapshot already exists: {}",
            snapshot_root.display()
        )));
    }
    let result = (|| {
        snapshot_presentation_release(release_root, &snapshot_root)?;
        stage_presentation_release_from_snapshot(staged_root, &snapshot_root)
    })();
    if snapshot_root.exists() {
        fs::remove_dir_all(&snapshot_root)?;
    }
    result
}

fn stage_presentation_release_from_snapshot(
    staged_root: &Path,
    release_root: &Path,
) -> io::Result<Option<PathBuf>> {
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

    let verified = verify_presentation_release(release_root)?;
    println!(
        "cargo:rustc-env=TOBKIRI_PRESENTATION_TRUST_KEY_B64={}",
        verified.public_key
    );
    println!(
        "cargo:rustc-env=TOBKIRI_PRESENTATION_TRUST_KEY_ID={}",
        verified.key_id
    );

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
    let bundle_root = staged_root.join("ecosystem/defaultspack/v4");
    #[cfg(not(test))]
    if !bundle_root.is_dir() {
        return Err(invalid_release(
            "complete staged verification requires the packaged Defaults v4 bundle",
        ));
    }
    if bundle_root.is_dir() {
        let repository_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(Path::parent)
            .ok_or_else(|| invalid_release("Launcher manifest has no repository root"))?
            .canonicalize()
            .map_err(|error| {
                invalid_release(format!("failed to resolve repository root: {error}"))
            })?;
        let source_revision = current_source_revision(&repository_root)?;
        let source_tree = current_source_tree(&repository_root, &source_revision)?;
        let trusted_source_manifest =
            committed_source_manifest(&repository_root, &source_revision)?;
        let snapshot_parent = std::env::var_os("OUT_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|| staged_root.join(".verified-source-snapshots"));
        let mut verified_source = packaged_source::verify_and_snapshot_against_manifest(
            &repository_root.join("tobkiri_runtime"),
            &snapshot_parent,
            &trusted_source_manifest,
        )
        .map_err(|error| {
            invalid_release(format!(
                "trusted Rust packaged Profile source-closure verification failed: {error}"
            ))
        })?;
        let execution = (|| -> io::Result<_> {
            let source_provenance = serde_json::to_vec(&serde_json::json!({
                "schema": "io.tobkiri.packaging-source-provenance.v1",
                "source_commit": &source_revision,
                "source_tree": &source_tree,
                "source_clean": true,
                "source_manifest_sha256": raw_byte_digest(&trusted_source_manifest),
            }))
            .map_err(io::Error::other)?;
            let provenance_path = verified_source.bind_provenance(&source_provenance)?;
            let python = packaging_toolchain::verified_tool("python")?;
            verified_source.verify_unchanged()?;
            let mut command = isolated_python_module_command(
                &python,
                &verified_source,
                "scripts.generate_packaged_defaultspack_v4_bundle",
            )?;
            command
                .arg("--source-artifact")
                .arg(&verified.artifact_path)
                .arg("--bundle-root")
                .arg(&bundle_root)
                .arg("--artifact-root")
                .arg(staged_root.join("ecosystem/defaultspack/platform-artifacts"))
                .arg("--relative-path")
                .arg(&verified.artifact_ref)
                .arg("--entrypoint")
                .arg(&verified.entrypoint)
                .arg("--platform")
                .arg(&verified.platform)
                .arg("--architecture")
                .arg(&verified.architecture)
                .arg("--bundle-identity")
                .arg(&verified.bundle_identity);
            bind_source_provenance_command(&mut command, &provenance_path);
            let mut child = command.spawn().map_err(|error| {
                invalid_release(format!("failed to run packaged Profile generator: {error}"))
            })?;
            match child.wait() {
                Ok(status) => Ok(status),
                Err(error) => {
                    let kill = child.kill();
                    let reap = child.wait();
                    Err(invalid_release(format!(
                        "failed waiting for packaged Profile generator: {error}; kill={kill:?}; reap={reap:?}"
                    )))
                }
            }
        })()
        .and_then(|status| {
            verified_source.verify_unchanged()?;
            Ok(status)
        });
        let cleanup = verified_source.cleanup();
        let status = match (execution, cleanup) {
            (Ok(status), Ok(())) => status,
            (Err(error), Ok(())) => return Err(error),
            (Ok(_), Err(cleanup)) => {
                return Err(invalid_release(format!(
                    "verified source snapshot cleanup failed: {cleanup}"
                )))
            }
            (Err(error), Err(cleanup)) => {
                return Err(invalid_release(format!(
                    "{error}; verified source snapshot cleanup also failed: {cleanup}"
                )))
            }
        };
        if !status.success() {
            return Err(invalid_release(format!(
                "packaged Profile generator exited with {status}"
            )));
        }
        let profile = bundle_root.join("defaults.profile.v4.json");
        let lock = bundle_root.join("bundle.lock.json");
        let profile_digest = byte_digest(&fs::read(&profile)?);
        let lock_digest = byte_digest(&fs::read(&lock)?);
        if profile_digest != verified.default_profile_sha256
            || lock_digest != verified.defaultspack_lock_sha256
        {
            return Err(invalid_release(format!(
                "packaged Defaults identity drift: profile={profile_digest}, lock={lock_digest}"
            )));
        }
        let staged_catalog = staged_bundled.join(PRESENTATION_CATALOG_FILENAME);
        let staged_verified = verify_presentation_release_at(staged_root, &staged_catalog)?;
        if staged_verified.default_profile_sha256 != verified.default_profile_sha256
            || staged_verified.defaultspack_lock_sha256 != verified.defaultspack_lock_sha256
            || staged_verified.artifact_ref != verified.artifact_ref
            || staged_verified.entrypoint != verified.entrypoint
        {
            return Err(invalid_release(
                "complete staged presentation release differs from its verified snapshot",
            ));
        }
    }
    let staged_catalog = staged_bundled.join(PRESENTATION_CATALOG_FILENAME);
    Ok(Some(staged_catalog))
}

fn current_source_revision(repository_root: &Path) -> io::Result<String> {
    let git = packaging_toolchain::verified_tool("git")?;
    let revision = git
        .command()?
        .args(["rev-parse", "--verify", "HEAD^{commit}"])
        .current_dir(repository_root)?
        .output()
        .map_err(|error| invalid_release(format!("failed to read source revision: {error}")))?;
    if !revision.status.success() {
        return Err(invalid_release("source checkout has no verifiable commit"));
    }
    let value = String::from_utf8(revision.stdout)
        .map_err(|error| invalid_release(format!("source revision is not UTF-8: {error}")))?
        .trim()
        .to_owned();
    if value.len() != 40
        || !value
            .chars()
            .all(|character| character.is_ascii_digit() || ('a'..='f').contains(&character))
    {
        return Err(invalid_release(
            "production source revision must be a full lowercase commit SHA",
        ));
    }
    let dirty = git
        .command()?
        .args(["status", "--porcelain=v1", "--untracked-files=all"])
        .current_dir(repository_root)?
        .output()
        .map_err(|error| invalid_release(format!("failed to inspect source status: {error}")))?;
    if !dirty.status.success() {
        return Err(invalid_release(
            "source checkout status could not be verified",
        ));
    }
    if !dirty.stdout.is_empty() {
        return Err(invalid_release(
            "production source revision cannot describe a dirty checkout",
        ));
    }
    Ok(value)
}

fn current_source_tree(repository_root: &Path, revision: &str) -> io::Result<String> {
    let git = packaging_toolchain::verified_tool("git")?;
    let object = format!("{revision}^{{tree}}");
    let output = git
        .command()?
        .args(["rev-parse", "--verify", &object])
        .current_dir(repository_root)?
        .output()
        .map_err(|error| invalid_release(format!("failed to read source tree: {error}")))?;
    if !output.status.success() {
        return Err(invalid_release("source checkout has no verifiable tree"));
    }
    let value = String::from_utf8(output.stdout)
        .map_err(|error| invalid_release(format!("source tree is not UTF-8: {error}")))?
        .trim()
        .to_owned();
    if !matches!(value.len(), 40 | 64)
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(invalid_release(
            "source tree is not a canonical Git object ID",
        ));
    }
    Ok(value)
}

fn committed_source_manifest(repository_root: &Path, revision: &str) -> io::Result<Vec<u8>> {
    let git = packaging_toolchain::verified_tool("git")?;
    let object =
        format!("{revision}:tobkiri_runtime/packaged_defaultspack_source_manifest.v1.json");
    let output = git
        .command()?
        .args(["show", &object])
        .current_dir(repository_root)?
        .output()
        .map_err(|error| {
            invalid_release(format!("failed to read committed source manifest: {error}"))
        })?;
    if !output.status.success() || output.stdout.len() > 4 * 1024 * 1024 {
        return Err(invalid_release(
            "committed packaged source manifest is unavailable or oversized",
        ));
    }
    Ok(output.stdout)
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
    let target = required_cargo_target()?;
    let (payload, permissions) = read_verified_pack_shell(&pack_shell, &target)?;
    verify_prebuilt_pack_shell_digest(&pack_shell, &payload)?;
    let bundled_dir = staged_root.join("bundled");
    if bundled_dir.exists() {
        require_directory(&bundled_dir, "pack-shell staging directory")?;
    }
    fs::create_dir_all(&bundled_dir)?;
    let destination = bundled_dir.join(pack_shell_binary_name(&target));
    if destination.exists() || fs::symlink_metadata(&destination).is_ok() {
        require_regular_file(&destination, "pack-shell staging destination")?;
    }
    let temporary = bundled_dir.join(format!(
        ".{}.{}.tmp",
        pack_shell_binary_name(&target),
        std::process::id()
    ));
    let mut temporary_file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temporary)?;
    let stage_result = (|| {
        temporary_file.write_all(&payload)?;
        temporary_file.sync_all()?;
        fs::set_permissions(&temporary, permissions)?;
        drop(temporary_file);
        if destination.exists() {
            fs::remove_file(&destination)?;
        }
        fs::rename(&temporary, &destination)?;
        let staged = fs::read(&destination)?;
        if Sha256::digest(&staged) != Sha256::digest(&payload) {
            let _ = fs::remove_file(&destination);
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!(
                    "staged pack-shell SHA256 mismatch: {}",
                    destination.display()
                ),
            ));
        }
        Ok(())
    })();
    let _ = fs::remove_file(&temporary);
    stage_result?;
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

    Err(io::Error::new(
        io::ErrorKind::NotFound,
        format!(
            "prebuilt verified pack-shell is required; production staging may not build source from {}",
            manifest.display()
        ),
    ))
}

fn verify_prebuilt_pack_shell_digest(path: &Path, payload: &[u8]) -> io::Result<()> {
    let mut digest_name = path.as_os_str().to_os_string();
    digest_name.push(".sha256");
    let digest_path = PathBuf::from(digest_name);
    let expected = String::from_utf8(read_regular_file(
        &digest_path,
        "prebuilt pack-shell digest",
    )?)
    .map_err(|_| {
        io::Error::new(
            io::ErrorKind::InvalidData,
            "prebuilt pack-shell digest must be UTF-8",
        )
    })?;
    let actual = format!("{:x}\n", Sha256::digest(payload));
    if expected != actual {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            "prebuilt pack-shell digest mismatch or non-canonical encoding",
        ));
    }
    Ok(())
}

fn find_pack_shell_binary(repo_root: &Path) -> io::Result<Option<PathBuf>> {
    let target = required_cargo_target()?;
    let profile = required_cargo_profile()?;

    let target_dir = resolve_cargo_target_dir(repo_root)?;
    let candidate = target_dir
        .join(&target)
        .join(&profile)
        .join(pack_shell_binary_name(&target));

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

    #[cfg(unix)]
    let is_executable = {
        use std::os::unix::fs::PermissionsExt;
        metadata.permissions().mode() & 0o111 != 0
    };
    #[cfg(unix)]
    if !is_executable {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!(
                "pack-shell binary must be executable: {}",
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
            reject_parent_traversal(&configured, CARGO_TARGET_DIR_ENV)?;
            if configured.is_absolute() {
                configured
            } else {
                repository_root.join(configured)
            }
        }
        _ => repository_root.join("pack-shell").join("target"),
    };

    let target_dir = normalize_absolute_path(&target_dir)?;
    let mut ancestors = target_dir.ancestors().collect::<Vec<_>>();
    ancestors.reverse();
    for ancestor in ancestors {
        match fs::symlink_metadata(ancestor) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    format!(
                        "Cargo target directory contains a symlink component: {}",
                        target_dir.display()
                    ),
                ));
            }
            Ok(metadata) if !metadata.is_dir() => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidData,
                    format!(
                        "Cargo target directory has a non-directory component: {}",
                        ancestor.display()
                    ),
                ));
            }
            Ok(_) => {}
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => return Err(error),
        }
    }
    Ok(target_dir)
}

fn reject_parent_traversal(path: &Path, label: &str) -> io::Result<()> {
    if path
        .components()
        .any(|component| component == Component::ParentDir)
    {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("{label} may not contain parent traversal: {path:?}"),
        ));
    }
    Ok(())
}

fn normalize_absolute_path(path: &Path) -> io::Result<PathBuf> {
    if !path.is_absolute() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            format!("path must be absolute after resolution: {}", path.display()),
        ));
    }
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    format!(
                        "resolved path contains parent traversal: {}",
                        path.display()
                    ),
                ));
            }
            _ => normalized.push(component.as_os_str()),
        }
    }
    Ok(normalized)
}

fn required_cargo_target() -> io::Result<String> {
    let target = std::env::var("TARGET").map_err(|_| {
        io::Error::new(
            io::ErrorKind::InvalidInput,
            "Cargo TARGET is missing or non-Unicode",
        )
    })?;
    validate_path_component(&target, "Rust target")?;
    Ok(target)
}

fn required_cargo_profile() -> io::Result<String> {
    let profile = std::env::var("PROFILE").unwrap_or_else(|_| "debug".to_string());
    validate_path_component(&profile, "Cargo profile")?;
    Ok(profile)
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

fn expected_pack_shell_architecture(target: &str) -> &str {
    match target.split('-').next().unwrap_or_default() {
        "amd64" => "x86_64",
        "arm64" => "aarch64",
        "i586" | "i686" => "x86",
        architecture => architecture,
    }
}

fn pack_shell_binary_architecture(payload: &[u8], target: &str) -> io::Result<String> {
    let invalid = |message: &str| io::Error::new(io::ErrorKind::InvalidData, message);
    if target.contains("windows") || target.ends_with("-msvc") {
        if payload.len() < 64 || &payload[..2] != b"MZ" {
            return Err(invalid("pack-shell is not a PE executable"));
        }
        let pe_offset = u32::from_le_bytes(payload[60..64].try_into().unwrap()) as usize;
        if payload.len() < pe_offset + 6 || &payload[pe_offset..pe_offset + 4] != b"PE\0\0" {
            return Err(invalid("pack-shell has an invalid PE header"));
        }
        let machine = u16::from_le_bytes(payload[pe_offset + 4..pe_offset + 6].try_into().unwrap());
        return Ok(match machine {
            0x014c => "x86".to_string(),
            0x8664 => "x86_64".to_string(),
            0xaa64 => "aarch64".to_string(),
            _ => format!("pe-machine-{machine:#x}"),
        });
    }

    if target.contains("apple-darwin") {
        if payload.len() < 8 {
            return Err(invalid("pack-shell has a truncated Mach-O header"));
        }
        let cpu_type = match &payload[..4] {
            b"\xcf\xfa\xed\xfe" | b"\xce\xfa\xed\xfe" => {
                u32::from_le_bytes(payload[4..8].try_into().unwrap())
            }
            b"\xfe\xed\xfa\xcf" | b"\xfe\xed\xfa\xce" => {
                u32::from_be_bytes(payload[4..8].try_into().unwrap())
            }
            _ => return Err(invalid("pack-shell is not a thin Mach-O executable")),
        };
        return Ok(match cpu_type {
            7 => "x86".to_string(),
            0x01000007 => "x86_64".to_string(),
            0x0100000c => "aarch64".to_string(),
            _ => format!("macho-cpu-{cpu_type:#x}"),
        });
    }

    if payload.len() < 20 || &payload[..4] != b"\x7fELF" {
        return Err(invalid("pack-shell is not an ELF executable"));
    }
    let machine_bytes: [u8; 2] = payload[18..20].try_into().unwrap();
    let machine = match payload.get(5) {
        Some(1) => u16::from_le_bytes(machine_bytes),
        Some(2) => u16::from_be_bytes(machine_bytes),
        _ => return Err(invalid("pack-shell ELF header has an invalid byte order")),
    };
    Ok(match machine {
        3 => "x86".to_string(),
        62 => "x86_64".to_string(),
        183 => "aarch64".to_string(),
        _ => format!("elf-machine-{machine:#x}"),
    })
}

fn same_file_identity(before: &fs::Metadata, after: &fs::Metadata) -> bool {
    if before.len() != after.len() || before.modified().ok() != after.modified().ok() {
        return false;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;
        before.dev() == after.dev() && before.ino() == after.ino()
    }
    #[cfg(not(unix))]
    {
        true
    }
}

fn read_verified_pack_shell(path: &Path, target: &str) -> io::Result<(Vec<u8>, fs::Permissions)> {
    let before = fs::symlink_metadata(path)?;
    if before.file_type().is_symlink() || !before.is_file() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!(
                "pack-shell binary must be a regular non-symlink: {}",
                path.display()
            ),
        ));
    }
    let mut source = fs::File::open(path)?;
    let opened = source.metadata()?;
    let mut payload = Vec::new();
    source.read_to_end(&mut payload)?;
    let after = fs::symlink_metadata(path)?;
    if !same_file_identity(&before, &opened) || !same_file_identity(&opened, &after) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!(
                "pack-shell binary changed while being staged: {}",
                path.display()
            ),
        ));
    }
    let actual = pack_shell_binary_architecture(&payload, target)?;
    let expected = expected_pack_shell_architecture(target);
    if actual != expected {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!("pack-shell architecture mismatch: expected {expected}, got {actual}"),
        ));
    }
    Ok((payload, opened.permissions()))
}

fn pack_shell_binary_name(target: &str) -> &'static str {
    if target.contains("windows") || target.ends_with("-msvc") {
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
    let git = packaging_toolchain::verified_tool("git")?;
    let output = match git
        .command()?
        .args(["ls-files", "-z", "--", APP_SOURCE_DIR])
        .current_dir(repo_root)?
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

fn configured_panel_build_dir(project_dir: &Path) -> Option<PathBuf> {
    let raw = std::env::var_os(PANEL_BUILD_DIR_ENV)?;
    let configured = PathBuf::from(raw);
    if configured.as_os_str().is_empty() {
        return None;
    }
    Some(if configured.is_absolute() {
        configured
    } else {
        project_dir
            .parent()
            .map(|launcher_root| launcher_root.join("frontend").join(&configured))
            .unwrap_or(configured)
    })
}

fn copy_generated_resource_dirs(
    project_dir: &Path,
    runtime_root: &Path,
    staged_root: &Path,
) -> io::Result<()> {
    let configured_panel_dir = configured_panel_build_dir(project_dir);
    for rel_dir in GENERATED_RESOURCE_DIRS {
        let source_dir = if *rel_dir == PANEL_RESOURCE_DIR {
            configured_panel_dir
                .clone()
                .unwrap_or_else(|| runtime_root.join(rel_dir))
        } else {
            runtime_root.join(rel_dir)
        };
        if !source_dir.exists() {
            if *rel_dir == PANEL_RESOURCE_DIR && configured_panel_dir.is_some() {
                return Err(io::Error::new(
                    io::ErrorKind::NotFound,
                    format!(
                        "configured panel build directory is missing: {}",
                        source_dir.display()
                    ),
                ));
            }
            continue;
        }
        if fs::symlink_metadata(&source_dir)?.file_type().is_symlink() {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                format!(
                    "generated runtime resource may not be a symlink: {}",
                    source_dir.display()
                ),
            ));
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
    use std::sync::{Mutex, MutexGuard};
    use std::time::{SystemTime, UNIX_EPOCH};

    static ENVIRONMENT_LOCK: Mutex<()> = Mutex::new(());

    fn environment_lock() -> MutexGuard<'static, ()> {
        ENVIRONMENT_LOCK
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
    }

    struct TestTree {
        root: PathBuf,
    }

    impl TestTree {
        fn new(label: &str) -> Self {
            let nonce = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("system clock must be after the Unix epoch")
                .as_nanos();
            // macOS commonly exposes its temporary directory through the
            // `/var` alias for canonical `/private/var`. Resolve only this
            // trusted OS-provided base before adding fixture-controlled names;
            // production target roots remain subject to strict symlink checks.
            let temp_base = std::env::temp_dir()
                .canonicalize()
                .expect("system temporary directory should canonicalize");
            let root = temp_base.join(format!(
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

    #[test]
    fn test_tree_resolves_only_the_trusted_system_temp_base() {
        let tree = TestTree::new("canonical-temp-base");
        assert_eq!(
            tree.path(),
            tree.path()
                .canonicalize()
                .expect("fixture path should remain canonical")
        );
    }

    #[test]
    fn runtime_manifest_uses_exact_portable_full_tree_order() {
        let tree = TestTree::new("runtime-manifest-order");
        for relative in [
            "bootstrap/00_env_check.py",
            "bootstrap.py",
            "lib/i18n/index.ts",
            "lib/i18n.test.ts",
        ] {
            let path = tree.path().join(relative);
            fs::create_dir_all(path.parent().expect("fixture file should have a parent"))
                .expect("fixture directory should be creatable");
            fs::write(path, relative.as_bytes()).expect("fixture file should be writable");
        }

        write_runtime_resource_manifest(tree.path()).expect("manifest should be writable");
        let manifest: serde_json::Value = serde_json::from_slice(
            &fs::read(tree.path().join(RUNTIME_RESOURCE_MANIFEST))
                .expect("manifest should be readable"),
        )
        .expect("manifest should be valid JSON");
        let paths = manifest["entries"]
            .as_array()
            .expect("manifest entries should be an array")
            .iter()
            .map(|entry| {
                entry["path"]
                    .as_str()
                    .expect("entry path should be a string")
            })
            .collect::<Vec<_>>();
        assert_eq!(
            paths,
            [
                "bootstrap.py",
                "bootstrap/00_env_check.py",
                "lib/i18n.test.ts",
                "lib/i18n/index.ts",
            ]
        );
    }

    #[test]
    fn sealed_python_binding_accepts_exact_tree_and_rejects_domain_swap() {
        let _environment = environment_lock();
        let target = if cfg!(target_arch = "aarch64") {
            "aarch64-apple-darwin"
        } else {
            "x86_64-apple-darwin"
        };
        let _target = EnvironmentGuard::set_value("TARGET", target);
        let _profile = EnvironmentGuard::set_value("PROFILE", "release");
        let tree = TestTree::new("sealed-python");
        let root = tree.path().join(SEALED_PYTHON_ROOT);
        let required = [
            "app/defaultspack_entry.py",
            "app/host_helper_entry.py",
            "app/kernel_entry.py",
            "lease.v1",
            "sentinels/native.sha256",
            "sentinels/site-packages.sha256",
            "sentinels/stdlib.sha256",
            "venv/bin/python3",
            "venv/lib/python3.13/site-packages/tobkiri_sealed/bootstrap.py",
        ];
        let mut files = Vec::new();
        for relative in required {
            let path = root.join(relative);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            let payload = if relative.ends_with("tobkiri_sealed/bootstrap.py") {
                sealed_python_protocol::REQUIRED_TEMPLATE_FRAGMENTS.join("\n")
                    + "\nparse_known_args role_args chmod\n"
            } else {
                relative.to_string()
            };
            fs::write(&path, payload.as_bytes()).unwrap();
            let executable = relative == "venv/bin/python3";
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                fs::set_permissions(
                    &path,
                    fs::Permissions::from_mode(if executable { 0o555 } else { 0o644 }),
                )
                .unwrap();
            }
            files.push(serde_json::json!({
                "path": relative,
                "size": payload.len(),
                "sha256": raw_byte_digest(payload.as_bytes()),
                "executable": executable
            }));
        }
        let inventory_digest = raw_byte_digest(&serde_json::to_vec(&files).unwrap());
        let manifest = serde_json::json!({
            "schema": SEALED_PYTHON_SCHEMA,
            "environment_digest": inventory_digest,
            "platform": "macos",
            "architecture": expected_pack_shell_architecture(target),
            "python_version": "3.13.13",
            "package_provenance": {
                "kind": "apple-code-signature-v1",
                "package_id": "dev.tobkiri.launcher",
                "release_digest": raw_byte_digest(b"release")
            },
            "sentinels": {
                "stdlib_sha256": raw_byte_digest(b"stdlib"),
                "site_packages_sha256": raw_byte_digest(b"site"),
                "native_sha256": raw_byte_digest(b"native")
            },
            "files": files
        });
        fs::write(
            root.join(SEALED_PYTHON_MANIFEST),
            serde_json::to_vec(&manifest).unwrap(),
        )
        .unwrap();
        bind_sealed_python_environment(tree.path()).unwrap();

        let mut swapped = manifest.clone();
        swapped["environment_digest"] = swapped["package_provenance"]["release_digest"].clone();
        fs::write(
            root.join(SEALED_PYTHON_MANIFEST),
            serde_json::to_vec(&swapped).unwrap(),
        )
        .unwrap();
        assert!(bind_sealed_python_environment(tree.path()).is_err());

        let mut prefixed = manifest;
        prefixed["sentinels"]["stdlib_sha256"] =
            serde_json::Value::String(format!("sha256:{}", raw_byte_digest(b"stdlib")));
        fs::write(
            root.join(SEALED_PYTHON_MANIFEST),
            serde_json::to_vec(&prefixed).unwrap(),
        )
        .unwrap();
        assert!(bind_sealed_python_environment(tree.path()).is_err());
    }

    #[test]
    fn non_macos_release_targets_are_rejected_before_packaging() {
        let _environment = environment_lock();
        let _profile = EnvironmentGuard::set_value("PROFILE", "release");
        for target in ["x86_64-pc-windows-msvc", "x86_64-unknown-linux-gnu"] {
            let _target = EnvironmentGuard::set_value("TARGET", target);
            let error = reject_unsupported_sealed_python_release_target().unwrap_err();
            assert_eq!(error.kind(), io::ErrorKind::Unsupported);
            assert!(error.to_string().contains(target));
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

        fn clear(key: &'static str) -> Self {
            let previous = std::env::var_os(key);
            std::env::remove_var(key);
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
            .join(pack_shell_binary_name(target));
        fs::create_dir_all(binary.parent().expect("fixture binary has a parent"))
            .expect("fixture binary directory should be creatable");
        let architecture = expected_pack_shell_architecture(target);
        let mut payload = if target.contains("windows") {
            let mut payload = vec![0_u8; 128];
            payload[..2].copy_from_slice(b"MZ");
            payload[60..64].copy_from_slice(&64_u32.to_le_bytes());
            payload[64..68].copy_from_slice(b"PE\0\0");
            let machine = match architecture {
                "aarch64" => 0xaa64_u16,
                _ => 0x8664_u16,
            };
            payload[68..70].copy_from_slice(&machine.to_le_bytes());
            payload
        } else if target.contains("apple-darwin") {
            let cpu_type = match architecture {
                "aarch64" => 0x0100000c_u32,
                _ => 0x01000007_u32,
            };
            [b"\xcf\xfa\xed\xfe".as_slice(), &cpu_type.to_le_bytes()].concat()
        } else {
            let mut payload = vec![0_u8; 64];
            payload[..6].copy_from_slice(b"\x7fELF\x02\x01");
            let machine = match architecture {
                "aarch64" => 183_u16,
                _ => 62_u16,
            };
            payload[18..20].copy_from_slice(&machine.to_le_bytes());
            payload
        };
        payload.extend_from_slice(b"pack-shell fixture");
        fs::write(&binary, payload).expect("fixture binary should be writable");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&binary, fs::Permissions::from_mode(0o755))
                .expect("fixture binary should be executable");
        }
        binary
    }

    #[test]
    fn pack_shell_lookup_resolves_default_absolute_and_relative_target_dirs() {
        let _environment_lock = environment_lock();
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
            let _target_dir =
                EnvironmentGuard::set_value(CARGO_TARGET_DIR_ENV, "relative target-雪");
            let binary =
                write_pack_shell_fixture(&tree.path().join("relative target-雪"), target, profile);
            assert_eq!(
                find_pack_shell_binary(tree.path()).expect("relative lookup should succeed"),
                Some(binary.canonicalize().expect("fixture should canonicalize"))
            );
        }
    }

    #[test]
    fn pack_shell_lookup_rejects_missing_wrong_and_traversing_binary_paths() {
        let _environment_lock = environment_lock();
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
        let _environment_lock = environment_lock();
        let tree = TestTree::new("pack-shell-symlink");
        let target = "aarch64-apple-darwin";
        let _target = EnvironmentGuard::set_value("TARGET", target);
        let _profile = EnvironmentGuard::set_value("PROFILE", "release");
        let target_dir = tree.path().join("target");
        let _target_dir = EnvironmentGuard::set_path(CARGO_TARGET_DIR_ENV, &target_dir);
        let binary = target_dir
            .join(target)
            .join("release")
            .join(pack_shell_binary_name(target));
        fs::create_dir_all(binary.parent().expect("fixture binary has a parent"))
            .expect("fixture binary directory should be creatable");
        let outside = tree.path().join("outside-pack-shell");
        fs::write(&outside, b"outside fixture").expect("outside fixture should be writable");
        std::os::unix::fs::symlink(&outside, &binary).expect("binary symlink should be creatable");

        let error =
            find_pack_shell_binary(tree.path()).expect_err("symlinked binary must be rejected");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
    }

    #[test]
    fn cargo_target_dir_rejects_parent_traversal_and_file_root() {
        let _environment_lock = environment_lock();
        let tree = TestTree::new("pack-shell-target-root-invalid");
        {
            let _target_dir = EnvironmentGuard::set_value(CARGO_TARGET_DIR_ENV, "../outside");
            let error = resolve_cargo_target_dir(tree.path())
                .expect_err("parent traversal must be rejected");
            assert_eq!(error.kind(), io::ErrorKind::InvalidInput);
        }
        {
            let target_file = tree.path().join("target-file");
            fs::write(&target_file, b"not a directory").expect("target file should be writable");
            let _target_dir = EnvironmentGuard::set_path(CARGO_TARGET_DIR_ENV, &target_file);
            let error = resolve_cargo_target_dir(tree.path())
                .expect_err("file target root must be rejected");
            assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        }
    }

    #[cfg(unix)]
    #[test]
    fn cargo_target_dir_rejects_symlinked_root() {
        let _environment_lock = environment_lock();
        let tree = TestTree::new("pack-shell-target-root-symlink");
        let outside = tree.path().join("outside");
        fs::create_dir_all(&outside).expect("outside directory should be creatable");
        let target_link = tree.path().join("target-link");
        std::os::unix::fs::symlink(&outside, &target_link)
            .expect("target symlink should be creatable");
        let _target_dir = EnvironmentGuard::set_path(CARGO_TARGET_DIR_ENV, &target_link);
        let error = resolve_cargo_target_dir(tree.path())
            .expect_err("symlinked target root must be rejected");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn cargo_target_dir_rejects_user_controlled_macos_var_alias() {
        let _environment_lock = environment_lock();
        let tree = TestTree::new("pack-shell-macos-var-alias");
        let alias = Path::new("/var");
        assert_ne!(
            alias
                .canonicalize()
                .expect("macOS /var alias should resolve"),
            alias
        );
        let target_dir = alias.join(format!("tobkiri-user-target-{}", std::process::id()));
        let _target_dir = EnvironmentGuard::set_path(CARGO_TARGET_DIR_ENV, &target_dir);

        let error = resolve_cargo_target_dir(tree.path())
            .expect_err("a user-controlled system alias must remain rejected");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
    }

    #[test]
    fn pack_shell_header_rejects_wrong_architecture_and_accepts_cross_target_names() {
        let tree = TestTree::new("pack-shell-header");
        let arm_target = "aarch64-apple-darwin";
        let x86_binary = write_pack_shell_fixture(
            &tree.path().join("target"),
            "x86_64-apple-darwin",
            "release",
        );
        let error = read_verified_pack_shell(&x86_binary, arm_target)
            .expect_err("wrong architecture must be rejected");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        assert_eq!(
            pack_shell_binary_name("x86_64-pc-windows-msvc"),
            "pack-shell.exe"
        );
        assert_eq!(pack_shell_binary_name(arm_target), "pack-shell");
    }

    #[test]
    fn production_pack_shell_requires_verified_prebuilt_digest() {
        let tree = TestTree::new("pack-shell-prebuilt-digest");
        let binary = tree.path().join("pack-shell");
        let payload = b"prebuilt pack-shell";
        fs::write(&binary, payload).expect("fixture binary should be writable");

        let missing = verify_prebuilt_pack_shell_digest(&binary, payload)
            .expect_err("missing digest must fail closed");
        assert_eq!(missing.kind(), io::ErrorKind::NotFound);

        let mut digest_name = binary.as_os_str().to_os_string();
        digest_name.push(".sha256");
        let digest_path = PathBuf::from(digest_name);
        fs::write(&digest_path, format!("{}\n", "0".repeat(64)))
            .expect("digest should be writable");
        let mismatch = verify_prebuilt_pack_shell_digest(&binary, payload)
            .expect_err("unverified payload must fail closed");
        assert_eq!(mismatch.kind(), io::ErrorKind::InvalidData);

        fs::write(&digest_path, format!("{:x}\n", Sha256::digest(payload)))
            .expect("verified digest should be writable");
        verify_prebuilt_pack_shell_digest(&binary, payload)
            .expect("matching prebuilt digest should pass");

        fs::write(&digest_path, format!("{:X}\n", Sha256::digest(payload)))
            .expect("non-canonical digest should be writable");
        let noncanonical = verify_prebuilt_pack_shell_digest(&binary, payload)
            .expect_err("uppercase digest encoding must fail closed");
        assert_eq!(noncanonical.kind(), io::ErrorKind::InvalidData);

        fs::write(&digest_path, format!("{:x}\n", Sha256::digest(b"tampered")))
            .expect("stale digest should be writable");
        let tampered = verify_prebuilt_pack_shell_digest(&binary, payload)
            .expect_err("stale digest must fail closed");
        assert_eq!(tampered.kind(), io::ErrorKind::InvalidData);
    }

    #[cfg(unix)]
    #[test]
    fn production_pack_shell_rejects_symlinked_digest() {
        let tree = TestTree::new("pack-shell-digest-symlink");
        let binary = tree.path().join("pack-shell");
        let payload = b"prebuilt pack-shell";
        fs::write(&binary, payload).expect("fixture binary should be writable");
        let outside = tree.path().join("outside.sha256");
        fs::write(&outside, format!("{:x}\n", Sha256::digest(payload)))
            .expect("outside digest should be writable");
        let digest_path = tree.path().join("pack-shell.sha256");
        std::os::unix::fs::symlink(&outside, &digest_path)
            .expect("digest symlink should be creatable");

        let error = verify_prebuilt_pack_shell_digest(&binary, payload)
            .expect_err("symlinked digest must fail closed");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
    }

    #[test]
    fn production_pack_shell_never_builds_missing_source_artifact() {
        let _environment_lock = environment_lock();
        let tree = TestTree::new("pack-shell-no-source-build");
        let _target = EnvironmentGuard::set_value("TARGET", "aarch64-apple-darwin");
        let _profile = EnvironmentGuard::set_value("PROFILE", "release");
        fs::create_dir_all(tree.path().join("pack-shell"))
            .expect("source directory should be creatable");
        fs::write(
            tree.path().join("pack-shell").join("Cargo.toml"),
            "[package]",
        )
        .expect("source manifest should be writable");

        let error = ensure_pack_shell_binary(tree.path())
            .expect_err("production source-build fallback must remain disabled");
        assert_eq!(error.kind(), io::ErrorKind::NotFound);
        assert!(error.to_string().contains("may not build source"));
    }

    #[test]
    fn isolated_panel_build_overlays_tracked_bundle_without_mutating_source() {
        let _environment_lock = environment_lock();
        let tree = TestTree::new("isolated-panel-build");
        let project_dir = tree.path().join("tobkiri_launcher/src-tauri");
        let runtime_root = tree.path().join(APP_SOURCE_DIR);
        let tracked_panel = runtime_root.join(PANEL_RESOURCE_DIR);
        let isolated_panel = tree.path().join("runner-temp/tobkiri-panel-build");
        let staged_root = tree.path().join("staged");
        fs::create_dir_all(&tracked_panel).expect("tracked panel should be creatable");
        fs::create_dir_all(&isolated_panel).expect("isolated panel should be creatable");
        fs::write(tracked_panel.join("index.html"), b"checked-in\n")
            .expect("tracked panel should be writable");
        fs::write(isolated_panel.join("index.html"), b"regenerated\n")
            .expect("isolated panel should be writable");
        let _panel_dir = EnvironmentGuard::set_path(PANEL_BUILD_DIR_ENV, &isolated_panel);

        copy_generated_resource_dirs(&project_dir, &runtime_root, &staged_root)
            .expect("isolated panel should be staged");

        assert_eq!(
            fs::read_to_string(runtime_root.join(PANEL_RESOURCE_DIR).join("index.html"))
                .expect("tracked panel should remain readable"),
            "checked-in\n"
        );
        assert_eq!(
            fs::read_to_string(staged_root.join(PANEL_RESOURCE_DIR).join("index.html"))
                .expect("staged panel should be readable"),
            "regenerated\n"
        );
    }

    #[test]
    fn configured_panel_build_must_exist_instead_of_falling_back_to_tracked_output() {
        let _environment_lock = environment_lock();
        let tree = TestTree::new("missing-isolated-panel-build");
        let project_dir = tree.path().join("tobkiri_launcher/src-tauri");
        let runtime_root = tree.path().join(APP_SOURCE_DIR);
        let staged_root = tree.path().join("staged");
        fs::create_dir_all(runtime_root.join(PANEL_RESOURCE_DIR))
            .expect("tracked panel should be creatable");
        let missing_panel = tree.path().join("runner-temp/missing-panel");
        let _panel_dir = EnvironmentGuard::set_path(PANEL_BUILD_DIR_ENV, &missing_panel);

        let error = copy_generated_resource_dirs(&project_dir, &runtime_root, &staged_root)
            .expect_err("missing configured panel must fail closed");
        assert_eq!(error.kind(), io::ErrorKind::NotFound);
    }

    #[test]
    fn package_never_falls_back_without_an_explicit_dev_build() {
        let _environment_lock = environment_lock();
        let _release_root = EnvironmentGuard::clear(PRESENTATION_RELEASE_ROOT_ENV);
        let _dev = EnvironmentGuard::clear("DEP_TAURI_DEV");
        let _profile = EnvironmentGuard::set_value("PROFILE", "debug");
        let tree = TestTree::new("presentation-no-fallback");
        let error = stage_presentation_release(&tree.path().join("staged"))
            .expect_err("packaging without a sealed root must fail even when Cargo selects debug");
        assert_eq!(error.kind(), io::ErrorKind::NotFound);
        assert!(error.to_string().contains(PRESENTATION_RELEASE_ROOT_ENV));
    }

    fn release_fixture(tree: &TestTree) -> (PathBuf, PathBuf, PathBuf) {
        let release_root = tree.path().join("release");
        let artifact_id = "shell.tauri.default.linux-x86_64";
        let artifact_path = Path::new("bundled")
            .join("presentation-artifacts")
            .join(artifact_id)
            .join("verified-shell");
        let artifacts = release_root.join(&artifact_path);
        let staged_root = tree.path().join("staged");
        let catalog_path = release_root.join(PRESENTATION_CATALOG_FILENAME);
        fs::create_dir_all(artifacts.parent().expect("artifact should have a parent"))
            .expect("release artifacts should be creatable");
        fs::create_dir_all(staged_root.join("bundled")).expect("staged bundle should be creatable");
        let artifact_payload = b"verified shell artifact";
        fs::write(&artifacts, artifact_payload).expect("release artifact should be writable");
        let (artifact_digest, artifact_size) =
            release_artifact_digest(&artifacts).expect("fixture artifact should hash");
        let entrypoint_digest = byte_digest(artifact_payload);
        let source_identity = "test:source";
        let source_revision = "a".repeat(40);
        let default_profile_path =
            release_root.join("ecosystem/defaultspack/v4/defaults.profile.v4.json");
        let defaultspack_lock_path =
            release_root.join("ecosystem/defaultspack/v4/bundle.lock.json");
        fs::create_dir_all(default_profile_path.parent().expect("Profile has a parent"))
            .expect("Defaults fixture should be creatable");
        fs::write(&default_profile_path, b"{\"profile_id\":\"defaults\"}\n")
            .expect("Profile fixture should be writable");
        fs::write(&defaultspack_lock_path, b"{\"entries\":[]}\n")
            .expect("Defaults lock fixture should be writable");
        let default_profile_sha256 =
            byte_digest(&fs::read(&default_profile_path).expect("Profile should exist"));
        let defaultspack_lock_sha256 =
            byte_digest(&fs::read(&defaultspack_lock_path).expect("Defaults lock should exist"));
        let index = serde_json::json!({
            "schema": PRESENTATION_INDEX_SCHEMA,
            "artifact_id": artifact_id,
            "path": artifact_path.to_string_lossy().replace('\\', "/"),
            "sha256": artifact_digest,
            "entrypoint_sha256": entrypoint_digest,
            "size": artifact_size,
            "platform": "linux",
            "architecture": "x86_64",
            "source_identity": source_identity,
            "source_revision": source_revision,
        });
        let index_digest =
            canonical_value_digest(&index, "fixture artifact index").expect("index should hash");
        let mut catalog = serde_json::json!({
            "schema": PRESENTATION_CATALOG_SCHEMA,
            "default_profile_digest": default_profile_sha256,
            "default_selection": {
                "base_pack_id": "fixture-base",
                "shell_provider_id": "shell.tauri.default",
            },
            "shell_providers": [{
                "provider_id": "shell.tauri.default",
                "artifact_variants": [{
                    "artifact_id": artifact_id,
                    "platform": "linux",
                    "architecture": "x86_64",
                    "path": artifact_path.to_string_lossy().replace('\\', "/"),
                    "sha256": artifact_digest,
                    "entrypoint_sha256": entrypoint_digest,
                    "artifact_ref": "verified-shell",
                    "entrypoint": "verified-shell",
                    "bundle_identifier": "io.tobkiri.shell.tauri",
                    "size": artifact_size,
                    "source_identity": source_identity,
                    "source_revision": source_revision,
                    "production": true,
                    "prebuilt": true,
                    "development_command": serde_json::Value::Null,
                }],
            }],
        });
        let catalog_revision =
            canonical_value_digest(&catalog, "fixture catalog").expect("catalog should hash");
        let lock_body = serde_json::json!({
            "schema": PRESENTATION_LOCK_SCHEMA,
            "catalog_revision": catalog_revision,
            "artifact_index_sha256": index_digest,
            "artifact_id": artifact_id,
            "artifact_sha256": artifact_digest,
            "entrypoint_sha256": entrypoint_digest,
            "platform": "linux",
            "architecture": "x86_64",
            "source_identity": source_identity,
            "source_revision": source_revision,
        });
        let lock_revision =
            canonical_value_digest(&lock_body, "fixture lock").expect("lock should hash");
        let mut lock = lock_body;
        lock["lock_revision"] = serde_json::Value::String(lock_revision);
        catalog["release_binding"] = serde_json::json!({
            "schema": PRESENTATION_RELEASE_SCHEMA,
            "artifact_index_path": "bundled/shell_artifact_index.v4.json",
            "artifact_index_sha256": index_digest,
            "profile_lock_path": "bundled/shell_profile_lock.v4.json",
            "profile_lock_sha256": canonical_value_digest(&lock, "fixture lock").expect("lock should hash"),
            "catalog_revision": catalog_revision,
            "artifact_id": artifact_id,
            "source_identity": source_identity,
            "source_revision": source_revision,
            "platform": "linux",
            "architecture": "x86_64",
        });
        fn write_json(path: &Path, value: &serde_json::Value) {
            fs::write(
                path,
                [
                    serde_json::to_vec_pretty(value).expect("fixture JSON should serialize"),
                    b"\n".to_vec(),
                ]
                .concat(),
            )
            .expect("fixture JSON should be writable");
        }
        write_json(&catalog_path, &catalog);
        write_json(
            &release_root
                .join("bundled")
                .join(PRESENTATION_INDEX_FILENAME),
            &index,
        );
        write_json(
            &release_root
                .join("bundled")
                .join(PRESENTATION_LOCK_FILENAME),
            &lock,
        );
        let catalog_file_digest =
            byte_digest(&fs::read(&catalog_path).expect("catalog should exist"));
        let index_file_digest = byte_digest(
            &fs::read(
                release_root
                    .join("bundled")
                    .join(PRESENTATION_INDEX_FILENAME),
            )
            .expect("index should exist"),
        );
        let lock_file_digest = byte_digest(
            &fs::read(
                release_root
                    .join("bundled")
                    .join(PRESENTATION_LOCK_FILENAME),
            )
            .expect("lock should exist"),
        );
        let signing_key = ed25519_dalek::SigningKey::from_bytes(&[7_u8; 32]);
        let public_key = BASE64.encode(signing_key.verifying_key().to_bytes());
        let key_id = "fixture-key";
        let message = [
            PRESENTATION_RELEASE_SCHEMA,
            catalog_file_digest.as_str(),
            index_file_digest.as_str(),
            lock_file_digest.as_str(),
            default_profile_sha256.as_str(),
            defaultspack_lock_sha256.as_str(),
            source_identity,
            source_revision.as_str(),
            "linux",
            "x86_64",
            artifact_id,
            key_id,
        ]
        .join("\0");
        let signature = BASE64.encode(signing_key.sign(message.as_bytes()).to_bytes());
        let release = serde_json::json!({
            "schema": PRESENTATION_RELEASE_SCHEMA,
            "catalog_path": "bundled/presentation_catalog.json",
            "catalog_sha256": catalog_file_digest,
            "artifact_index_path": "bundled/shell_artifact_index.v4.json",
            "artifact_index_sha256": index_file_digest,
            "profile_lock_path": "bundled/shell_profile_lock.v4.json",
            "profile_lock_sha256": lock_file_digest,
            "default_profile_path": "ecosystem/defaultspack/v4/defaults.profile.v4.json",
            "default_profile_sha256": default_profile_sha256,
            "defaultspack_lock_path": "ecosystem/defaultspack/v4/bundle.lock.json",
            "defaultspack_lock_sha256": defaultspack_lock_sha256,
            "artifact_id": artifact_id,
            "platform": "linux",
            "architecture": "x86_64",
            "source_identity": source_identity,
            "source_revision": source_revision,
            "key_id": key_id,
            "public_key": public_key,
            "signature": signature,
        });
        write_json(
            &release_root
                .join("bundled")
                .join(PRESENTATION_RELEASE_FILENAME),
            &release,
        );
        (release_root, staged_root, catalog_path)
    }

    fn host_fixture(tree: &TestTree) -> (PathBuf, PathBuf) {
        let source_root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(Path::parent)
            .expect("Launcher should live under the repository")
            .join(APP_SOURCE_DIR);
        let staged_root = tree.path().join("staged-host");
        let host_root = staged_root.join("tobkiri_host");
        fs::create_dir_all(&host_root).expect("Host package should be creatable");
        for filename in
            canonical_host_files(&source_root).expect("Host inventory should be readable")
        {
            fs::copy(
                source_root.join("tobkiri_host").join(&filename),
                host_root.join(filename),
            )
            .expect("Host resource should be copied exactly");
        }
        (staged_root, source_root)
    }

    #[test]
    fn canonical_host_inventory_is_exact() {
        let tree = TestTree::new("host-inventory");
        let (staged_root, source_root) = host_fixture(&tree);
        verify_canonical_host_package(&staged_root, &source_root)
            .expect("exact Host package should be accepted");

        fs::write(staged_root.join("tobkiri_host/unlisted.py"), b"pass\n")
            .expect("unlisted resource should be writable");
        assert!(verify_canonical_host_package(&staged_root, &source_root).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn canonical_host_inventory_rejects_symlink() {
        let tree = TestTree::new("host-symlink");
        let (staged_root, source_root) = host_fixture(&tree);
        let runtime = staged_root.join("tobkiri_host/runtime.py");
        fs::remove_file(&runtime).expect("runtime fixture should be removable");
        std::os::unix::fs::symlink(tree.path(), &runtime)
            .expect("Host symlink should be creatable");
        assert!(verify_canonical_host_package(&staged_root, &source_root).is_err());
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

        assert_ne!(source_catalog, catalog);
        assert!(source_catalog.starts_with(&staged_root));
        assert!(source_catalog.is_file());
        assert!(staged_catalog.is_file());
        verify_staged_catalog(&source_catalog, &staged_catalog)
            .expect("staged catalog should match the release catalog");
        assert!(staged_root
            .join("bundled")
            .join("presentation-artifacts")
            .join("shell.tauri.default.linux-x86_64")
            .join("verified-shell")
            .is_file());
    }

    #[test]
    fn snapshot_rejects_mutation_of_every_signed_identity_during_copy() {
        for relative in [
            "presentation_catalog.json",
            "bundled/shell_artifact_index.v4.json",
            "bundled/shell_profile_lock.v4.json",
            "bundled/presentation_release.v4.json",
            "ecosystem/defaultspack/v4/defaults.profile.v4.json",
            "ecosystem/defaultspack/v4/bundle.lock.json",
        ] {
            let tree = TestTree::new(&format!("snapshot-race-{}", relative.replace('/', "-")));
            let (release_root, _, _) = release_fixture(&tree);
            let snapshot = tree.path().join("private-snapshot");
            let target = release_root.join(relative);
            let error = snapshot_presentation_release_with_hook(&release_root, &snapshot, || {
                fs::write(&target, b"mutated during snapshot")
                    .expect("race mutation should be writable");
            })
            .expect_err("source mutation during snapshot must fail closed");
            assert!(error.to_string().contains("mutated or copied partially"));
        }
    }

    #[test]
    fn snapshot_rejects_missing_extra_and_partial_release_trees() {
        let tree = TestTree::new("snapshot-tree-shape");
        let (release_root, _, _) = release_fixture(&tree);
        fs::write(release_root.join("unexpected.json"), b"extra")
            .expect("extra fixture should be writable");
        let error =
            snapshot_presentation_release(&release_root, &tree.path().join("extra-snapshot"))
                .expect_err("extra release entry must fail closed");
        assert!(error.to_string().contains("extra entry"));

        fs::remove_file(release_root.join("unexpected.json"))
            .expect("extra fixture should be removable");
        fs::remove_file(
            release_root
                .join("bundled")
                .join(PRESENTATION_INDEX_FILENAME),
        )
        .expect("required fixture should be removable");
        let error =
            snapshot_presentation_release(&release_root, &tree.path().join("missing-snapshot"))
                .expect_err("missing release entry must fail closed");
        assert!(error.to_string().contains("missing required file"));
    }

    #[test]
    fn verification_rejects_an_extra_artifact_sibling() {
        let tree = TestTree::new("extra-artifact-sibling");
        let (release_root, _, _) = release_fixture(&tree);
        let rogue_artifact = release_root
            .join("bundled/presentation-artifacts")
            .join("shell.tauri.default.linux-x86_64-stale")
            .join("verified-shell");
        fs::create_dir_all(
            rogue_artifact
                .parent()
                .expect("rogue artifact should have a parent"),
        )
        .expect("rogue artifact directory should be creatable");
        fs::write(&rogue_artifact, b"stale artifact").expect("rogue artifact should be writable");

        let error = verify_presentation_release(&release_root)
            .expect_err("an unsigned artifact sibling must fail closed");
        assert!(error.to_string().contains("extra artifact entry"));
    }

    #[cfg(any(unix, windows))]
    #[test]
    fn snapshot_rejects_hardlinked_release_files() {
        let tree = TestTree::new("snapshot-hardlink");
        let (release_root, _, catalog) = release_fixture(&tree);
        let outside = tree.path().join("outside-catalog.json");
        fs::rename(&catalog, &outside).expect("catalog should move outside");
        fs::hard_link(&outside, &catalog).expect("hardlink fixture should be creatable");
        let error =
            snapshot_presentation_release(&release_root, &tree.path().join("hardlink-snapshot"))
                .expect_err("hardlinked release file must fail closed");
        assert!(error.to_string().contains("must have one link"));
    }

    #[test]
    fn source_mutation_after_snapshot_cannot_change_staged_bytes() {
        let tree = TestTree::new("snapshot-post-verify-mutation");
        let (release_root, staged_root, catalog) = release_fixture(&tree);
        let snapshot = tree.path().join("private-snapshot");
        snapshot_presentation_release(&release_root, &snapshot)
            .expect("release snapshot should succeed");
        verify_presentation_release(&snapshot).expect("snapshot should verify");
        fs::write(&catalog, b"mutated after snapshot verification")
            .expect("mutable source should be changeable");

        let staged_catalog = stage_presentation_release_from_snapshot(&staged_root, &snapshot)
            .expect("verified snapshot should stage")
            .expect("staged catalog should be returned");
        assert_eq!(
            fs::read(&staged_catalog).expect("staged catalog should be readable"),
            fs::read(snapshot.join(PRESENTATION_CATALOG_FILENAME))
                .expect("snapshot catalog should be readable")
        );
        assert_ne!(
            fs::read(&staged_catalog).expect("staged catalog should remain readable"),
            fs::read(&catalog).expect("mutated source should be readable")
        );
    }

    #[test]
    fn complete_staged_release_verification_rechecks_every_signed_file() {
        for relative in [
            "bundled/presentation_catalog.json",
            "bundled/shell_artifact_index.v4.json",
            "bundled/shell_profile_lock.v4.json",
            "bundled/presentation_release.v4.json",
            "ecosystem/defaultspack/v4/defaults.profile.v4.json",
            "ecosystem/defaultspack/v4/bundle.lock.json",
        ] {
            let tree = TestTree::new(&format!("staged-recheck-{}", relative.replace('/', "-")));
            let (release_root, _, _) = release_fixture(&tree);
            let staged = tree.path().join("complete-staged");
            copy_release_tree(&release_root, &staged).expect("release should copy to stage");
            let source_catalog = staged.join(PRESENTATION_CATALOG_FILENAME);
            let staged_catalog = staged.join("bundled").join(PRESENTATION_CATALOG_FILENAME);
            fs::rename(&source_catalog, &staged_catalog)
                .expect("catalog should move to packaged location");
            verify_presentation_release_at(&staged, &staged_catalog)
                .expect("complete staged release should verify before tampering");
            fs::write(staged.join(relative), b"tampered staged release")
                .expect("staged tamper should be writable");
            verify_presentation_release_at(&staged, &staged_catalog)
                .expect_err("every staged signed identity must be rechecked");
        }
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn packager_output_is_accepted_by_complete_build_staging() {
        let tree = TestTree::new("packager-build-staging");
        let repository_root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(Path::parent)
            .expect("Launcher should live under the repository")
            .canonicalize()
            .expect("repository root should resolve");
        let package_root = tree.path().join("package-input");
        fs::create_dir_all(&package_root).expect("package fixture root should be creatable");
        let package_test = repository_root
            .join("tobkiri_launcher/scripts/tests/test_package_presentation_artifact.py");
        let python = packaging_toolchain::verified_tool("python")
            .expect("formal packaging Python binding should be available");
        let status = python
            .command()
            .expect("verified Python command should be constructible")
            .args([
                "-c",
                "import runpy,sys; from pathlib import Path; runpy.run_path(sys.argv[1])['_package'](Path(sys.argv[2]))",
            ])
            .arg(&package_test)
            .arg(&package_root)
            .current_dir(&repository_root)
            .expect("repository cwd should be anchorable")
            .status()
            .expect("official packager fixture should run");
        assert!(status.success(), "official packager fixture should succeed");

        let staged_root = tree.path().join("staged");
        copy_dir_recursive(
            &repository_root.join("tobkiri_runtime/ecosystem/defaultspack/v4"),
            &staged_root.join("ecosystem/defaultspack/v4"),
        )
        .expect("canonical Defaults bundle should stage");
        fs::create_dir_all(staged_root.join("bundled"))
            .expect("staged bundled directory should be creatable");

        let staged_catalog =
            stage_presentation_release_at(&staged_root, &package_root.join("release"))
                .expect("build staging must accept the packager's exact output")
                .expect("packager output should return its staged catalog");
        verify_presentation_release_at(&staged_root, &staged_catalog)
            .expect("complete staged output should remain verified");
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
        let valid_catalog = fs::read(&catalog).expect("fixture catalog should be readable");
        let outside_catalog = tree.path().join("outside-catalog.json");
        fs::write(&outside_catalog, b"outside catalog").expect("outside catalog should exist");
        fs::remove_file(&catalog).expect("fixture catalog should be removable");
        std::os::unix::fs::symlink(&outside_catalog, &catalog)
            .expect("catalog symlink should be creatable");

        let error = stage_presentation_release_at(&staged_root, &release_root)
            .expect_err("symlinked release catalog must fail closed");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);

        fs::remove_file(&catalog).expect("catalog symlink should be removable");
        fs::write(&catalog, valid_catalog).expect("catalog should be restorable");
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
