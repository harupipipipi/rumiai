//! Application update mechanism — **stub**.
//!
//! This module will be fully implemented in Phase U.

use anyhow::Result;

/// Check whether a newer version is available.
///
/// Returns `Ok(Some(version_string))` if an update exists, `Ok(None)`
/// otherwise.
///
/// # Current implementation
/// Always returns `Ok(None)` (stub).
pub fn check_for_update() -> Result<Option<String>> {
    Ok(None)
}

/// Download and apply the given update.
///
/// # Current implementation
/// Returns `Ok(())` without doing anything (stub).
pub fn apply_update(_version: &str) -> Result<()> {
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn check_for_update_returns_none() {
        let result = check_for_update().unwrap();
        assert!(result.is_none());
    }

    #[test]
    fn apply_update_is_noop() {
        assert!(apply_update("0.0.0").is_ok());
    }
}
