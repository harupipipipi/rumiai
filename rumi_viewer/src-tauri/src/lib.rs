//! Rumi Viewer — Tauri application library.
//!
//! V2: Full implementation with setup hook, commands, tray menu, and navigation guard.

mod config;
mod health_check;
mod kernel_manager;
mod python_env;
mod tray;
mod updater;

use std::sync::{Arc, Mutex};
use std::time::Duration;

use anyhow::{bail, Context, Result as AnyResult};
use log::{error, info};
use rand::{distributions::Alphanumeric, Rng};
use serde::Deserialize;
use tauri::Manager;

use config::AppConfig;
use kernel_manager::KernelManager;

/// Wrapper around a shared progress string, managed as Tauri State.
pub struct SetupProgress(pub Arc<Mutex<String>>);

#[derive(Debug, Deserialize)]
struct PanelBootstrapPayload {
    code: String,
}

#[derive(Debug, Deserialize)]
struct ApiEnvelope<T> {
    success: bool,
    data: Option<T>,
    error: Option<String>,
}

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

fn generate_panel_bootstrap_secret() -> String {
    rand::thread_rng()
        .sample_iter(&Alphanumeric)
        .take(64)
        .map(char::from)
        .collect()
}

fn request_panel_bootstrap_code(port: u16, bootstrap_secret: &str) -> AnyResult<String> {
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(10))
        .build()
        .context("failed to build bootstrap HTTP client")?;
    let url = format!("http://127.0.0.1:{port}/api/panel/auth/bootstrap");
    let response = client
        .post(url)
        .header("X-Rumi-Desktop-Bootstrap", bootstrap_secret)
        .send()
        .context("panel bootstrap request failed")?;

    if !response.status().is_success() {
        let status = response.status();
        let body = response.text().unwrap_or_default();
        bail!("panel bootstrap returned {status}: {body}");
    }

    let envelope: ApiEnvelope<PanelBootstrapPayload> = response
        .json()
        .context("failed to decode panel bootstrap response")?;
    if !envelope.success {
        bail!(envelope.error.unwrap_or_else(|| "panel bootstrap failed".into()));
    }

    let payload = envelope
        .data
        .context("panel bootstrap response missing payload")?;
    if payload.code.is_empty() {
        bail!("panel bootstrap response missing code");
    }
    Ok(payload.code)
}

pub fn run() {
    env_logger::init();

    tauri::Builder::default()
        .plugin(
            tauri::plugin::Builder::<tauri::Wry, ()>::new("nav-guard")
                .on_navigation(|_webview, url| {
                    let scheme = url.scheme();
                    let host = url.host_str().unwrap_or("");
                    let port = url.port();

                    let is_tauri = scheme == "tauri";
                    let is_local_http = scheme == "http"
                        && (host == "localhost" || host == "127.0.0.1")
                        && (port == Some(8765) || cfg!(debug_assertions));

                    let allowed = is_tauri || is_local_http;

                    if !allowed {
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

            std::fs::create_dir_all(&config.log_dir).ok();
            std::fs::create_dir_all(&config.user_data_dir).ok();

            let progress = SetupProgress(Arc::new(Mutex::new(
                "Initializing...".to_string(),
            )));
            let progress_arc = progress.0.clone();
            app.manage(progress);

            let panel_bootstrap_secret = generate_panel_bootstrap_secret();
            let km = Arc::new(Mutex::new(KernelManager::new(
                &config,
                panel_bootstrap_secret.clone(),
            )));
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

                set_progress("Ready");

                let panel_code = match request_panel_bootstrap_code(port, &panel_bootstrap_secret)
                {
                    Ok(code) => code,
                    Err(e) => {
                        let msg = format!("Error: Panel bootstrap failed — {e}");
                        error!("{msg}");
                        set_progress(&msg);
                        return;
                    }
                };

                if let Some(win) = handle.get_webview_window("main") {
                    let js = format!(
                        "window.location.replace('http://127.0.0.1:{port}/panel/?code={panel_code}')"
                    );
                    if let Err(e) = win.eval(&js) {
                        error!("Failed to navigate to panel: {e}");
                    }
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
