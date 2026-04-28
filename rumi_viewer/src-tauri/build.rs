use std::fs;
use std::io;
use std::path::{Path, PathBuf};

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
    let runtime_root = repo_root.join("rumi_ai_1_10");
    let staged_root = project_dir.join("gen").join("app");

    reset_dir(&staged_root)?;
    copy_runtime_tree(&runtime_root, &staged_root, &runtime_root)?;

    let bundled_src = project_dir.join("bundled");
    if bundled_src.exists() {
        copy_dir_recursive(&bundled_src, &staged_root.join("bundled"))?;
    }

    stage_pack_shell(&repo_root, &staged_root)?;

    Ok(())
}

fn stage_pack_shell(repo_root: &Path, staged_root: &Path) -> io::Result<()> {
    let Some(pack_shell) = find_pack_shell_binary(repo_root) else {
        return Ok(());
    };
    let bundled_dir = staged_root.join("bundled");
    fs::create_dir_all(&bundled_dir)?;
    fs::copy(pack_shell, bundled_dir.join(pack_shell_binary_name()))?;
    Ok(())
}

fn find_pack_shell_binary(repo_root: &Path) -> Option<PathBuf> {
    let binary_name = pack_shell_binary_name();
    [
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
    ]
    .into_iter()
    .find(|candidate| candidate.is_file())
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

fn copy_runtime_tree(src: &Path, dst: &Path, runtime_root: &Path) -> io::Result<()> {
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let source_path = entry.path();
        let file_type = entry.file_type()?;
        let target_path = dst.join(entry.file_name());
        let relative = source_path.strip_prefix(runtime_root).unwrap_or(&source_path);

        if should_skip(relative, file_type.is_dir()) {
            continue;
        }

        if file_type.is_dir() {
            copy_dir_recursive_filtered(&source_path, &target_path, runtime_root)?;
        } else if file_type.is_file() {
            if let Some(parent) = target_path.parent() {
                fs::create_dir_all(parent)?;
            }
            fs::copy(&source_path, &target_path)?;
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
            fs::copy(&source_path, &target_path)?;
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
        let relative = source_path.strip_prefix(runtime_root).unwrap_or(&source_path);

        if should_skip(relative, file_type.is_dir()) {
            continue;
        }

        if file_type.is_dir() {
            copy_dir_recursive_filtered(&source_path, &target_path, runtime_root)?;
        } else if file_type.is_file() {
            fs::copy(&source_path, &target_path)?;
        }
    }
    Ok(())
}

fn should_skip(relative: &Path, is_dir: bool) -> bool {
    let Some(first) = relative.components().next().map(|c| c.as_os_str()) else {
        return false;
    };

    if matches!(
        first.to_str(),
        Some(".env")
            | Some(".env.local")
            | Some(".backups")
            | Some(".backup_dead_code_removal")
            | Some("user_data")
            | Some("userdata")
            | Some("chats")
            | Some("tenpu")
    ) {
        return true;
    }

    if matches!(
        first.to_str(),
        Some(".git") | Some(".mypy_cache") | Some("docs") | Some("tests")
    ) {
        return true;
    }

    if relative.components().any(|component| {
        matches!(
            component.as_os_str().to_str(),
            Some("__pycache__") | Some(".pytest_cache") | Some(".ruff_cache")
        )
    }) {
        return true;
    }

    if first == "frontend" {
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
