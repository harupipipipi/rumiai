//! Rumi Viewer — Tauri application library.
//!
//! V2: Full implementation with setup hook, commands, tray menu, and navigation guard.

mod config;
mod health_check;
mod kernel_manager;
mod python_env;
mod tray;
mod updater;

use anyhow::{bail, Context, Result};
use env_logger::Env;
use std::process::Command;
use std::sync::{Arc, Mutex};

use log::{error, info};
use tauri::Manager;

use config::AppConfig;
use kernel_manager::KernelManager;

/// Wrapper around a shared progress string, managed as Tauri State.
pub struct SetupProgress(pub Arc<Mutex<String>>);

/// Returns the current setup progress message.
#[tauri::command]
fn get_setup_progress(state: tauri::State<'_, SetupProgress>) -> String {
    state.0.lock().unwrap().clone()
}

/// Restart the Kernel process.
#[tauri::command]
fn restart_kernel(state: tauri::State<'_, Arc<Mutex<KernelManager>>>) -> Result<String, String> {
    let mut km = state.lock().map_err(|e| format!("lock error: {e}"))?;
    km.restart().map_err(|e| format!("restart error: {e}"))?;
    Ok("Kernel restarted".into())
}

fn read_kernel_token(config: &AppConfig) -> Result<String> {
    let script = r#"
import os
import sys

sys.path.insert(0, os.environ["RUMI_HOME"])

from core_runtime.hmac_key_manager import HMACKeyManager

print(HMACKeyManager().get_active_key())
"#;

    let output = Command::new(config.venv_python())
        .args(["-c", script])
        .current_dir(&config.rumi_home)
        .env("RUMI_HOME", &config.rumi_home)
        .env("RUMI_USER_DATA", &config.user_data_dir)
        .output()
        .context("failed to execute token helper")?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        bail!(
            "token helper exited with {}: {}",
            output.status,
            stderr.trim()
        );
    }

    let token = String::from_utf8_lossy(&output.stdout).trim().to_string();
    if token.is_empty() {
        bail!("token helper returned an empty token");
    }

    Ok(token)
}

fn redact_token(url: &str) -> String {
    match url.split_once("token=") {
        Some((prefix, rest)) => {
            let suffix_start = rest.find('&').unwrap_or(rest.len());
            let suffix = &rest[suffix_start..];
            format!("{prefix}token=<redacted>{suffix}")
        }
        None => url.to_string(),
    }
}

fn build_panel_url(port: u16, token: &str, cache_bust: u64) -> String {
    format!("http://127.0.0.1:{port}/panel/?token={token}&v={cache_bust}")
}

fn is_allowed_navigation_target(
    scheme: &str,
    host: Option<&str>,
    port: Option<u16>,
    allow_any_local_port: bool,
) -> bool {
    let is_tauri = scheme == "tauri";
    let is_local_http = scheme == "http"
        && matches!(host, Some("localhost" | "127.0.0.1"))
        && (port == Some(8765) || allow_any_local_port);

    is_tauri || is_local_http
}

fn open_panel_window(handle: &tauri::AppHandle, panel_url: &str) -> Result<()> {
    info!("Opening panel at {}", redact_token(panel_url));

    let parsed_url = panel_url.parse().context("panel URL could not be parsed")?;

    if let Some(existing) = handle.get_webview_window("panel") {
        info!("Panel window already exists; focusing it");
        let _ = existing.unminimize();
        let _ = existing.show();
        let _ = existing.set_focus();
        if let Some(splash) = handle.get_webview_window("main") {
            let _ = splash.hide();
        }
        return Ok(());
    }

    let panel =
        tauri::WebviewWindowBuilder::new(handle, "panel", tauri::WebviewUrl::External(parsed_url))
            .title("Rumi AI")
            .inner_size(1280.0, 800.0)
            .min_inner_size(960.0, 640.0)
            .center()
            .focused(true)
            .visible(true)
            .on_page_load(|_window, payload| {
                let phase = match payload.event() {
                    tauri::webview::PageLoadEvent::Started => "started",
                    tauri::webview::PageLoadEvent::Finished => "finished",
                };
                info!(
                    "Panel page load {phase}: {}",
                    redact_token(payload.url().as_str())
                );
            })
            .build()
            .context("failed to build panel window")?;

    let _ = panel.show();
    let _ = panel.set_focus();

    if let Some(splash) = handle.get_webview_window("main") {
        let _ = splash.hide();
    }

    info!("Panel window opened successfully");
    Ok(())
}

pub fn run() {
    env_logger::Builder::from_env(Env::default().default_filter_or("info")).init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(
            tauri::plugin::Builder::<tauri::Wry, ()>::new("nav-guard")
                .on_navigation(|_webview, url| {
                    let allowed = is_allowed_navigation_target(
                        url.scheme(),
                        url.host_str(),
                        url.port(),
                        cfg!(debug_assertions),
                    );

                    if allowed {
                        info!("Allowed navigation to: {}", redact_token(url.as_str()));
                    } else {
                        log::warn!("Blocked navigation to: {url}");
                    }
                    allowed
                })
                .build(),
        )
        .setup(|app| {
            let resource_dir = app
                .path()
                .resource_dir()
                .expect("failed to resolve resource_dir");
            let app_data_dir = app
                .path()
                .app_data_dir()
                .expect("failed to resolve app_data_dir");

            let config = AppConfig::detect_for_tauri(resource_dir, app_data_dir)
                .expect("failed to build AppConfig");
            info!("Resolved app_dir={}", config.app_dir.display());
            info!("Resolved user_data_dir={}", config.user_data_dir.display());

            std::fs::create_dir_all(&config.log_dir).ok();
            std::fs::create_dir_all(&config.user_data_dir).ok();

            let progress = SetupProgress(Arc::new(Mutex::new("Initializing...".to_string())));
            let progress_arc = progress.0.clone();
            app.manage(progress);

            let km = Arc::new(Mutex::new(KernelManager::new(&config)));
            let km_for_thread = km.clone();
            app.manage(km);

            app.manage(config.clone());

            if let Some(win) = app.get_webview_window("main") {
                let _ = win.show();
            }

            let handle = app.handle().clone();
            let port = config.kernel_port;

            std::thread::spawn(move || {
                let set_progress = |msg: &str| {
                    if let Ok(mut p) = progress_arc.lock() {
                        *p = msg.to_string();
                    }
                    info!("{msg}");
                };

                set_progress("Checking Python environment...");
                if let Err(e) = python_env::ensure_python_env(&config) {
                    let msg = format!("Error: Python setup failed — {e}");
                    error!("{msg}");
                    set_progress(&msg);
                    return;
                }

                set_progress("Starting Kernel...");
                {
                    let mut km = km_for_thread.lock().unwrap();
                    if let Err(e) = km.start() {
                        let msg = format!("Error: Kernel start failed — {e}");
                        error!("{msg}");
                        set_progress(&msg);
                        return;
                    }
                }

                set_progress("Waiting for Kernel...");
                if let Err(e) = health_check::wait_for_healthy(port, 60) {
                    let msg = format!("Error: Kernel health check failed — {e}");
                    error!("{msg}");
                    set_progress(&msg);
                    return;
                }

                set_progress("Authorizing panel...");
                let token = match read_kernel_token(&config) {
                    Ok(token) => token,
                    Err(e) => {
                        let msg = format!("Error: Panel authorization failed — {e}");
                        error!("{msg}");
                        set_progress(&msg);
                        return;
                    }
                };

                let cache_bust = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|duration| duration.as_secs())
                    .unwrap_or(0);
                let panel_url = build_panel_url(port, &token, cache_bust);
                info!("Prepared panel URL {}", redact_token(&panel_url));

                set_progress("Ready");

                let handle_for_panel = handle.clone();
                let panel_url_for_window = panel_url.clone();
                if let Err(e) = handle.run_on_main_thread(move || {
                    if let Err(e) = open_panel_window(&handle_for_panel, &panel_url_for_window) {
                        error!("Failed to open panel window: {e}");
                    }
                }) {
                    error!("Failed to schedule panel window open: {e}");
                }

                // Background update check — log only, never interrupt startup.
                match updater::check_for_update() {
                    Ok(Some(info)) => {
                        info!(
                            "Update available: {} -> {}",
                            info.current_version, info.latest_version
                        );
                    }
                    Ok(None) => {
                        info!("Rumi AI is up to date.");
                    }
                    Err(e) => {
                        error!("Startup update check failed (non-fatal): {e}");
                    }
                }
            });

            tray::setup_tray(app)?;

            Ok(())
        })
        .on_window_event(|window, event| {
            #[cfg(target_os = "macos")]
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .invoke_handler(tauri::generate_handler![get_setup_progress, restart_kernel])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn redact_token_masks_token_value_and_preserves_other_query_params() {
        let url = "http://127.0.0.1:8765/panel/?token=secret-value&v=123";
        assert_eq!(
            redact_token(url),
            "http://127.0.0.1:8765/panel/?token=<redacted>&v=123"
        );
    }

    #[test]
    fn redact_token_leaves_tokenless_url_unchanged() {
        let url = "http://127.0.0.1:8765/panel/?v=123";
        assert_eq!(redact_token(url), url);
    }

    #[test]
    fn build_panel_url_targets_pre_auth_panel_route() {
        assert_eq!(
            build_panel_url(8765, "abc123", 42),
            "http://127.0.0.1:8765/panel/?token=abc123&v=42"
        );
    }

    #[test]
    fn navigation_guard_allows_panel_routes_on_kernel_port() {
        assert!(is_allowed_navigation_target(
            "http",
            Some("127.0.0.1"),
            Some(8765),
            false
        ));
        assert!(is_allowed_navigation_target(
            "http",
            Some("localhost"),
            Some(8765),
            false
        ));
    }

    #[test]
    fn navigation_guard_blocks_non_loopback_or_wrong_scheme_routes() {
        assert!(!is_allowed_navigation_target(
            "https",
            Some("127.0.0.1"),
            Some(8765),
            false
        ));
        assert!(!is_allowed_navigation_target(
            "http",
            Some("example.com"),
            Some(8765),
            false
        ));
        assert!(!is_allowed_navigation_target(
            "http",
            Some("127.0.0.1"),
            Some(3000),
            false
        ));
    }

    #[test]
    fn navigation_guard_debug_mode_allows_local_dev_port() {
        assert!(is_allowed_navigation_target(
            "http",
            Some("localhost"),
            Some(3000),
            true
        ));
    }

    #[test]
    fn navigation_guard_always_allows_tauri_scheme() {
        assert!(is_allowed_navigation_target("tauri", None, None, false));
    }
}
