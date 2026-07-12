use std::fs;
use std::io;
use std::path::{Path, PathBuf};

const MARKER: &str = ".tobkiri-migration-complete";

pub fn migrate_legacy_app_data(new_dir: &Path) -> io::Result<bool> {
    if new_dir.exists() {
        reject_symlink(new_dir)?;
        if fs::read_dir(new_dir)?.next().is_some() {
            return Ok(false);
        }
        fs::remove_dir(new_dir)?;
    }
    let parent = new_dir
        .parent()
        .ok_or_else(|| io::Error::other("app data path has no parent"))?;
    let old_dir = parent.join("dev.rumiai.app");
    if !old_dir.exists() {
        return Ok(false);
    }
    reject_symlink(&old_dir)?;
    let staging = parent.join(format!(
        ".tobkiri-app-data-migration-{}",
        std::process::id()
    ));
    if staging.exists() {
        fs::remove_dir_all(&staging)?;
    }
    if let Err(error) = copy_tree(&old_dir, &staging).and_then(|_| {
        fs::write(
            staging.join(MARKER),
            b"legacy app data copied; source retained\n",
        )?;
        fs::rename(&staging, new_dir)
    }) {
        let _ = fs::remove_dir_all(&staging);
        return Err(error);
    }
    Ok(true)
}

fn reject_symlink(path: &Path) -> io::Result<()> {
    if fs::symlink_metadata(path)?.file_type().is_symlink() {
        return Err(io::Error::other(format!(
            "refusing symlink during migration: {}",
            path.display()
        )));
    }
    Ok(())
}

fn copy_tree(source: &Path, destination: &Path) -> io::Result<()> {
    reject_symlink(source)?;
    fs::create_dir(destination)?;
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let source_path = entry.path();
        reject_symlink(&source_path)?;
        let destination_path: PathBuf = destination.join(entry.file_name());
        if entry.file_type()?.is_dir() {
            copy_tree(&source_path, &destination_path)?;
        } else if entry.file_type()?.is_file() {
            fs::copy(source_path, destination_path)?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn root(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "tobkiri_migration_{name}_{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }

    #[test]
    fn copies_legacy_data_once_and_retains_source() {
        let root = root("copy");
        let old = root.join("dev.rumiai.app");
        let new = root.join("dev.tobkiri.launcher");
        fs::create_dir_all(old.join("user_data")).unwrap();
        fs::write(old.join("user_data/profile.json"), b"profile").unwrap();
        assert!(migrate_legacy_app_data(&new).unwrap());
        assert_eq!(
            fs::read(new.join("user_data/profile.json")).unwrap(),
            b"profile"
        );
        assert!(old.exists());
        assert!(!migrate_legacy_app_data(&new).unwrap());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn missing_legacy_data_is_a_noop() {
        let root = root("missing");
        fs::create_dir_all(&root).unwrap();
        assert!(!migrate_legacy_app_data(&root.join("dev.tobkiri.launcher")).unwrap());
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn existing_new_data_wins_over_legacy_data() {
        let root = root("new_wins");
        let old = root.join("dev.rumiai.app");
        let new = root.join("dev.tobkiri.launcher");
        fs::create_dir_all(&old).unwrap();
        fs::create_dir_all(&new).unwrap();
        fs::write(old.join("state"), b"old").unwrap();
        fs::write(new.join("state"), b"new").unwrap();
        assert!(!migrate_legacy_app_data(&new).unwrap());
        assert_eq!(fs::read(new.join("state")).unwrap(), b"new");
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn rejects_symlinks_without_creating_destination() {
        use std::os::unix::fs::symlink;
        let root = root("symlink");
        let old = root.join("dev.rumiai.app");
        let new = root.join("dev.tobkiri.launcher");
        fs::create_dir_all(&old).unwrap();
        symlink("/tmp", old.join("unsafe")).unwrap();
        assert!(migrate_legacy_app_data(&new).is_err());
        assert!(!new.exists());
        fs::remove_dir_all(root).unwrap();
    }
}
