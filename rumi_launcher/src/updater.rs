//! Application update mechanism — **stub**.
//!
//! This module will be fully implemented in Phase U.  For now it provides
//! no-op functions so that `main.rs` can compile and call the update API
//! without conditional compilation.

use anyhow::Result;

/// Check whether a newer version is available.
///
/// Returns `Ok(Some(version_string))` if an update exists, `Ok(None)`
/// otherwise.
///
/// # Current implementation
/// Always returns `Ok(None)` (stub).
pub fn check_for_update() -> Result<Option<String>> {
    // Phase U: implement real update check against GitHub releases.
    Ok(None)
}

/// Download and apply the given update.
///
/// # Current implementation
/// Returns `Ok(())` without doing anything (stub — never called because
/// `check_for_update` always returns `None`).
pub fn apply_update(_version: &str) -> Result<()> {
    // Phase U: implement real update logic (self_update crate, etc.).
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn check_for_update_returns_none() {
        let result = check_for_update().unwrap();
        assert!(result.is_none(), "stub should return None");
    }

    #[test]
    fn apply_update_is_noop() {
        assert!(apply_update("0.0.0").is_ok());
    }
}
