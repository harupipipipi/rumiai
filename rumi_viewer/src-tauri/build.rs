use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::Command;

const APP_SOURCE_DIR: &str = "rumi_ai_1_10";
const GENERATED_RESOURCE_DIRS: &[&str] = &[
    "core_runtime/core_pack/core_control_panel/web",
    "ecosystem/defaultspack/ui",
    "bundled",
];

fn main() {
    println!("cargo:rerun-if-changed=splash/index.html");
    println!("cargo:rerun-if-changed=src/lib.rs");
    println!("cargo:rerun-if-changed=../../rumi_ai_1_10/app.py");
    println!("cargo:rerun-if-changed=../../rumi_ai_1_10/core_runtime");
    println!("cargo:rerun-if-changed=../../rumi_ai_1_10/ecosystem");
    println!("cargo:rerun-if-changed=../../rumi_ai_1_10/flows");
    println!("cargo:rerun-if-changed=../../rumi_ai_1_10/lang");
    println!("cargo:rerun-if-changed=../../rumi_ai_1_10/rumi_setup");
    println!("cargo:rerun-if-changed=../../rumi_ai_1_10/requirements.txt");
    println!("cargo:rerun-if-changed=bundled");

    stage_runtime_bundle().expect("failed to stage runtime bundle");
    tauri_build::build()
}

fn stage_runtime_bundle() -> io::Result<()> {
    let project_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let repo_root = project_dir
        .parent()
        .and_then(Path::parent)
        .expect("src-tauri should live under rumi_viewer/");
    let runtime_root = repo_root.join(APP_SOURCE_DIR);
    let staged_root = project_dir.join("gen").join("app");

    reset_dir(&staged_root)?;
    if !copy_tracked_runtime_tree(repo_root, &staged_root)? {
        copy_runtime_tree(&runtime_root, &staged_root, &runtime_root)?;
    }
    copy_generated_resource_dirs(&runtime_root, &staged_root)?;
    stage_defaultspack_seed(&runtime_root, &staged_root)?;

    let bundled_src = project_dir.join("bundled");
    if bundled_src.exists() {
        copy_dir_recursive(&bundled_src, &staged_root.join("bundled"))?;
    }

    stage_edge_haze_helper(&runtime_root, &staged_root)?;
    stage_pack_shell(&repo_root, &staged_root)?;

    Ok(())
}

fn stage_edge_haze_helper(runtime_root: &Path, staged_root: &Path) -> io::Result<()> {
    if !cargo_target_is_macos() {
        return Ok(());
    }
    let source = runtime_root
        .join("ecosystem")
        .join("rumi_default_tools_pack")
        .join("domain")
        .join("computer")
        .join("mac")
        .join("EdgeHaze.swift");
    if !source.is_file() {
        return Ok(());
    }
    let swiftc = match find_swiftc() {
        Some(path) => path,
        None => {
            println!(
                "cargo:warning=swiftc not found; computer-use edge haze helper will not be bundled"
            );
            return Ok(());
        }
    };
    let dest = staged_root
        .join("bundled")
        .join("helpers")
        .join("edge_haze")
        .join("edge_haze");
    if let Some(parent) = dest.parent() {
        fs::create_dir_all(parent)?;
    }
    let output = Command::new(&swiftc)
        .arg(&source)
        .arg("-O")
        .arg("-o")
        .arg(&dest)
        .output()?;
    if !output.status.success() {
        return Err(io::Error::new(
            io::ErrorKind::Other,
            format!(
                "failed to compile EdgeHaze.swift with {}: {}",
                swiftc.display(),
                String::from_utf8_lossy(&output.stderr)
            ),
        ));
    }
    println!("cargo:rerun-if-changed={}", source.display());
    Ok(())
}

fn cargo_target_is_macos() -> bool {
    std::env::var("TARGET")
        .map(|target| target.contains("apple-darwin"))
        .unwrap_or(cfg!(target_os = "macos"))
}

fn find_swiftc() -> Option<PathBuf> {
    if Command::new("swiftc")
        .arg("--version")
        .output()
        .ok()?
        .status
        .success()
    {
        return Some(PathBuf::from("swiftc"));
    }
    if let Ok(output) = Command::new("xcrun").args(["--find", "swiftc"]).output() {
        if output.status.success() {
            let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
            if !path.is_empty() {
                return Some(PathBuf::from(path));
            }
        }
    }
    None
}

fn stage_pack_shell(repo_root: &Path, staged_root: &Path) -> io::Result<()> {
    let Some(pack_shell) = find_pack_shell_binary(repo_root) else {
        return Ok(());
    };
    let bundled_dir = staged_root.join("bundled");
    fs::create_dir_all(&bundled_dir)?;
    copy_file(&pack_shell, &bundled_dir.join(pack_shell_binary_name()))?;
    Ok(())
}

fn find_pack_shell_binary(repo_root: &Path) -> Option<PathBuf> {
    let binary_name = pack_shell_binary_name();
    let mut candidates = Vec::new();
    if let Ok(target) = std::env::var("TARGET") {
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

fn stage_defaultspack_seed(runtime_root: &Path, staged_root: &Path) -> io::Result<()> {
    let source_dir = runtime_root.join("ecosystem").join("defaultspack");
    if !source_dir.exists() {
        return Ok(());
    }
    let seed_dir = staged_root.join("pack_seeds").join("defaultspack");
    if seed_dir.exists() {
        clear_dir(&seed_dir)?;
    }
    copy_dir_recursive_filtered(&source_dir, &seed_dir, runtime_root)
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
        if file_type.is_dir() {
            copy_dir_recursive(&source_path, &target_path)?;
        } else if file_type.is_file() {
            copy_file(&source_path, &target_path)?;
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
