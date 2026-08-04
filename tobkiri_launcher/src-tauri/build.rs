use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::Command;

const APP_SOURCE_DIR: &str = "tobkiri_runtime";
const PRESENTATION_RELEASE_ROOT_ENV: &str = "TOBKIRI_PRESENTATION_RELEASE_ROOT";
const PRESENTATION_CATALOG_FILENAME: &str = "presentation_catalog.json";
const GENERATED_RESOURCE_DIRS: &[&str] = &[
    "core_runtime/core_pack/core_control_panel/web",
    "ecosystem/defaultspack/ui",
    "bundled",
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
        copy_runtime_tree(&runtime_root, &staged_root, &runtime_root)
            .map_err(|error| stage_error("copy runtime tree", error))?;
    }
    copy_generated_resource_dirs(&runtime_root, &staged_root)
        .map_err(|error| stage_error("copy generated resources", error))?;
    stage_setup_brand_icon(&repo_root, &staged_root)
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

    stage_pack_shell(&repo_root, &staged_root)
        .map_err(|error| stage_error("stage pack-shell", error))?;

    Ok(())
}

fn stage_presentation_release(staged_root: &Path) -> io::Result<Option<PathBuf>> {
    let Some(raw_root) = std::env::var_os(PRESENTATION_RELEASE_ROOT_ENV) else {
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

    let staged_bundled = staged_root.join("bundled");
    copy_file(
        &catalog,
        &staged_bundled.join(PRESENTATION_CATALOG_FILENAME),
    )?;
    copy_dir_recursive(&artifacts, &staged_bundled.join("presentation-artifacts"))?;
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
    if let Some(pack_shell) = find_pack_shell_binary(repo_root) {
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
        .arg(&manifest);

    if std::env::var("PROFILE").as_deref() == Ok("release") {
        command.arg("--release");
    }

    let output = command.output()?;
    if output.status.success() {
        return Ok(find_pack_shell_binary(repo_root));
    }

    Err(io::Error::other(format!(
        "failed to build pack-shell with status {}\nstdout:\n{}\nstderr:\n{}",
        output.status,
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    )))
}

fn find_pack_shell_binary(repo_root: &Path) -> Option<PathBuf> {
    let binary_name = pack_shell_binary_name();
    let mut candidates = Vec::new();
    if let Ok(target) = std::env::var("TARGET") {
        candidates.push(
            repo_root
                .join("target")
                .join(&target)
                .join("release")
                .join(binary_name),
        );
        candidates.push(
            repo_root
                .join("pack-shell")
                .join("target")
                .join(target)
                .join("release")
                .join(binary_name),
        );
    }
    candidates.extend([
        repo_root.join("target").join("release").join(binary_name),
        repo_root.join("target").join("debug").join(binary_name),
        repo_root
            .join("pack-shell")
            .join("target")
            .join("release")
            .join(binary_name),
        repo_root
            .join("pack-shell")
            .join("target")
            .join("debug")
            .join(binary_name),
    ]);
    candidates.into_iter().find(|candidate| candidate.is_file())
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
        if !source_path.is_file() {
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

fn copy_runtime_tree(src: &Path, dst: &Path, runtime_root: &Path) -> io::Result<()> {
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let source_path = entry.path();
        let file_type = entry.file_type()?;
        let target_path = dst.join(entry.file_name());
        let relative = source_path
            .strip_prefix(runtime_root)
            .unwrap_or(&source_path);

        if should_skip(relative, file_type.is_dir()) {
            continue;
        }

        if file_type.is_dir() {
            copy_dir_recursive_filtered(&source_path, &target_path, runtime_root)?;
        } else if file_type.is_file() {
            copy_file(&source_path, &target_path)?;
        }
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
    use std::time::{SystemTime, UNIX_EPOCH};

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

    fn release_fixture(tree: &TestTree) -> (PathBuf, PathBuf, PathBuf) {
        let release_root = tree.path().join("release");
        let artifacts = release_root.join("bundled").join("presentation-artifacts");
        let staged_root = tree.path().join("staged");
        let catalog = release_root.join(PRESENTATION_CATALOG_FILENAME);
        fs::create_dir_all(&artifacts).expect("release artifacts should be creatable");
        fs::create_dir_all(staged_root.join("bundled")).expect("staged bundle should be creatable");
        fs::write(&catalog, b"verified presentation catalog")
            .expect("release catalog should be writable");
        fs::write(artifacts.join("verified-shell"), b"verified shell artifact")
            .expect("release artifact should be writable");
        (release_root, staged_root, catalog)
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
