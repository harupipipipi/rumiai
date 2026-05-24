//! Application update support.
//!
//! The primary path uses Tauri's signed updater plugin. The older GitHub
//! Releases checker is kept as a manual-download fallback.

use std::time::Duration;

use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter};
use tauri_plugin_updater::{Update, UpdaterExt};

const VIEWER_UPDATE_PROGRESS_EVENT: &str = "viewer-update-progress";

/// Build-time placeholder used until release signing is configured.
const PLACEHOLDER_UPDATER_PUBKEY: &str = "RUMI_VIEWER_UPDATER_PUBKEY_NOT_CONFIGURED";

/// Public status shape returned by update commands.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct ViewerUpdateStatus {
    pub current_version: String,
    pub latest_version: Option<String>,
    pub notes: Option<String>,
    pub pub_date: Option<String>,
    pub available: bool,
    pub error: Option<String>,
    pub progress: Option<f64>,
}

impl ViewerUpdateStatus {
    fn current() -> Self {
        Self {
            current_version: env!("CARGO_PKG_VERSION").to_string(),
            latest_version: None,
            notes: None,
            pub_date: None,
            available: false,
            error: None,
            progress: None,
        }
    }
}

#[derive(Debug, Clone)]
struct ViewerUpdateMetadata {
    current_version: String,
    latest_version: String,
    notes: Option<String>,
    pub_date: Option<String>,
}

impl ViewerUpdateMetadata {
    fn into_status(self, progress: Option<f64>) -> ViewerUpdateStatus {
        ViewerUpdateStatus {
            current_version: self.current_version,
            latest_version: Some(self.latest_version),
            notes: self.notes,
            pub_date: self.pub_date,
            available: true,
            error: None,
            progress,
        }
    }
}

/// Check Tauri's signed updater endpoint for a Viewer update.
#[tauri::command]
pub async fn check_viewer_update(app: AppHandle) -> ViewerUpdateStatus {
    match check_signed_update(&app).await {
        Ok(Some(update)) => update_metadata(&update).into_status(None),
        Ok(None) => ViewerUpdateStatus::current(),
        Err(error) => fallback_github_status(error),
    }
}

/// Download and install the latest signed Viewer update.
#[tauri::command]
pub async fn install_viewer_update(app: AppHandle) -> ViewerUpdateStatus {
    if !compiled_updater_pubkey_configured() {
        let mut status = fallback_github_status(
            "automatic updater signing key is not configured for this build".to_string(),
        );
        status.progress = Some(0.0);
        return status;
    }

    let update = match check_signed_update(&app).await {
        Ok(Some(update)) => update,
        Ok(None) => {
            let mut status = ViewerUpdateStatus::current();
            status.progress = Some(1.0);
            return status;
        }
        Err(error) => {
            let mut status = fallback_github_status(error);
            status.progress = Some(0.0);
            return status;
        }
    };

    let metadata = update_metadata(&update);
    let mut downloaded = 0_u64;
    let progress_app = app.clone();
    let finish_app = app.clone();
    let progress_metadata = metadata.clone();
    let finish_metadata = metadata.clone();

    match update
        .download_and_install(
            move |chunk_length, content_length| {
                downloaded = downloaded.saturating_add(chunk_length as u64);
                let progress =
                    content_length.and_then(|total| calculate_progress(downloaded, total));
                let _ = progress_app.emit(
                    VIEWER_UPDATE_PROGRESS_EVENT,
                    progress_metadata.clone().into_status(progress),
                );
            },
            move || {
                let _ = finish_app.emit(
                    VIEWER_UPDATE_PROGRESS_EVENT,
                    finish_metadata.clone().into_status(Some(1.0)),
                );
            },
        )
        .await
    {
        Ok(()) => {
            app.request_restart();
            metadata.into_status(Some(1.0))
        }
        Err(error) => {
            let mut status = metadata.into_status(Some(0.0));
            status.error = Some(format!("failed to install signed update: {error}"));
            status
        }
    }
}

pub fn configured_updater_pubkey() -> &'static str {
    option_env!("RUMI_VIEWER_UPDATER_PUBKEY").unwrap_or(PLACEHOLDER_UPDATER_PUBKEY)
}

fn compiled_updater_pubkey_configured() -> bool {
    configured_updater_pubkey() != PLACEHOLDER_UPDATER_PUBKEY
}

async fn check_signed_update(app: &AppHandle) -> std::result::Result<Option<Update>, String> {
    let updater = app
        .updater()
        .map_err(|error| format!("failed to build signed updater: {error}"))?;
    updater
        .check()
        .await
        .map_err(|error| format!("signed updater check failed: {error}"))
}

fn update_metadata(update: &Update) -> ViewerUpdateMetadata {
    ViewerUpdateMetadata {
        current_version: update.current_version.clone(),
        latest_version: update.version.clone(),
        notes: update.body.clone(),
        pub_date: update_pub_date(update),
    }
}

fn update_pub_date(update: &Update) -> Option<String> {
    update
        .raw_json
        .get("pub_date")
        .and_then(|date| date.as_str())
        .map(ToOwned::to_owned)
        .or_else(|| update.date.map(|date| date.to_string()))
}

fn fallback_github_status(primary_error: String) -> ViewerUpdateStatus {
    let mut status = match check_for_update() {
        Ok(Some(info)) => ViewerUpdateStatus {
            current_version: info.current_version,
            latest_version: Some(info.latest_version),
            notes: info.notes,
            pub_date: info.pub_date,
            available: true,
            error: None,
            progress: None,
        },
        Ok(None) => ViewerUpdateStatus::current(),
        Err(fallback_error) => {
            let mut status = ViewerUpdateStatus::current();
            status.error = Some(format!(
                "{primary_error}; GitHub release fallback failed: {fallback_error}"
            ));
            return status;
        }
    };

    status.error = Some(format!(
        "{primary_error}; falling back to GitHub Releases for manual download"
    ));
    status
}

fn calculate_progress(downloaded: u64, total: u64) -> Option<f64> {
    if total == 0 {
        return None;
    }
    Some((downloaded as f64 / total as f64).clamp(0.0, 1.0))
}

/// Information about an available update.
#[derive(Debug, Clone)]
pub struct UpdateInfo {
    /// The latest version string, e.g. "0.2.0".
    pub latest_version: String,
    /// URL to the GitHub release page.
    pub release_url: String,
    /// The currently running version, e.g. "0.1.0".
    pub current_version: String,
    /// Release notes from GitHub, if present.
    pub notes: Option<String>,
    /// GitHub release publish timestamp, if present.
    pub pub_date: Option<String>,
}

/// Partial GitHub Releases API response.
#[derive(Debug, Deserialize)]
struct GitHubRelease {
    tag_name: String,
    html_url: String,
    body: Option<String>,
    published_at: Option<String>,
}

/// The GitHub API endpoint for the latest release.
const RELEASES_API: &str = "https://api.github.com/repos/harupipipipi/rumiai/releases/latest";

/// HTTP request timeout in seconds.
const TIMEOUT_SECS: u64 = 10;

/// Check whether a newer version is available on GitHub Releases.
///
/// Returns `Ok(Some(UpdateInfo))` if an update exists, `Ok(None)` if the
/// current version is up-to-date, or an error on network / parse failure.
///
/// Errors are **not** fatal — callers should log and continue.
pub fn check_for_update() -> Result<Option<UpdateInfo>> {
    let current_str = env!("CARGO_PKG_VERSION");
    let current = parse_version(current_str).context("failed to parse current version")?;

    let release = fetch_latest_release().context("failed to fetch latest release")?;

    let latest = parse_version(&release.tag_name)
        .with_context(|| format!("failed to parse release tag: {}", release.tag_name))?;

    if latest > current {
        Ok(Some(UpdateInfo {
            latest_version: latest.to_string(),
            release_url: release.html_url,
            current_version: current.to_string(),
            notes: release.body,
            pub_date: release.published_at,
        }))
    } else {
        Ok(None)
    }
}

/// Open the release page in the user's default browser.
pub fn open_release_page(info: &UpdateInfo) -> Result<()> {
    open::that_detached(&info.release_url).context("failed to open release page in browser")?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/// Fetch the latest release metadata from the GitHub API.
fn fetch_latest_release() -> Result<GitHubRelease> {
    let version = env!("CARGO_PKG_VERSION");
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(TIMEOUT_SECS))
        .user_agent(format!("rumi-viewer/{version}"))
        .build()
        .context("failed to build HTTP client")?;

    let resp = client
        .get(RELEASES_API)
        .header("Accept", "application/vnd.github+json")
        .send()
        .context("GitHub API request failed")?;

    if !resp.status().is_success() {
        bail!("GitHub API returned HTTP {}", resp.status());
    }

    let release: GitHubRelease = resp.json().context("failed to parse GitHub release JSON")?;

    Ok(release)
}

/// Parse a version string, stripping an optional leading `v`.
fn parse_version(tag: &str) -> Result<semver::Version> {
    let cleaned = tag.strip_prefix('v').unwrap_or(tag);
    semver::Version::parse(cleaned).with_context(|| format!("invalid semver: {tag}"))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_version_with_v_prefix() {
        let v = parse_version("v1.2.3").unwrap();
        assert_eq!(v, semver::Version::new(1, 2, 3));
    }

    #[test]
    fn parse_version_without_prefix() {
        let v = parse_version("1.2.3").unwrap();
        assert_eq!(v, semver::Version::new(1, 2, 3));
    }

    #[test]
    fn parse_version_invalid() {
        assert!(parse_version("invalid").is_err());
    }

    #[test]
    fn update_detected_when_latest_is_newer() {
        let current = parse_version("0.1.0").unwrap();
        let latest = parse_version("0.2.0").unwrap();
        assert!(latest > current);
    }

    #[test]
    fn no_update_when_current_is_latest() {
        let current = parse_version("1.0.0").unwrap();
        let latest = parse_version("1.0.0").unwrap();
        assert!(!(latest > current));
    }

    #[test]
    fn progress_is_none_when_total_is_unknown() {
        assert_eq!(calculate_progress(42, 0), None);
    }

    #[test]
    fn progress_is_clamped_to_complete() {
        assert_eq!(calculate_progress(150, 100), Some(1.0));
    }

    #[test]
    fn metadata_status_exposes_expected_fields() {
        let metadata = ViewerUpdateMetadata {
            current_version: "0.1.0".into(),
            latest_version: "0.2.0".into(),
            notes: Some("notes".into()),
            pub_date: Some("2026-05-24T00:00:00Z".into()),
        };

        assert_eq!(
            metadata.into_status(Some(0.5)),
            ViewerUpdateStatus {
                current_version: "0.1.0".into(),
                latest_version: Some("0.2.0".into()),
                notes: Some("notes".into()),
                pub_date: Some("2026-05-24T00:00:00Z".into()),
                available: true,
                error: None,
                progress: Some(0.5),
            }
        );
    }
}
