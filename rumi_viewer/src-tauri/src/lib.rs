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
use std::thread;
use std::time::Duration;

use anyhow::{anyhow, bail, Context, Result as AnyResult};
use log::{error, info, warn};
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
    match state.0.lock() {
        Ok(progress) => progress.clone(),
        Err(error) => {
            error!("Setup progress lock poisoned: {error}");
            "Setup status unavailable".to_string()
        }
    }
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
        bail!(envelope
            .error
            .unwrap_or_else(|| "panel bootstrap failed".into()));
    }

    let payload = envelope
        .data
        .context("panel bootstrap response missing payload")?;
    if payload.code.is_empty() {
        bail!("panel bootstrap response missing code");
    }
    Ok(payload.code)
}

fn request_panel_bootstrap_code_with_retry(port: u16, bootstrap_secret: &str) -> AnyResult<String> {
    let max_attempts = 10;
    let retry_delay = Duration::from_millis(500);
    let mut last_error = None;

    for attempt in 1..=max_attempts {
        match request_panel_bootstrap_code(port, bootstrap_secret) {
            Ok(code) => return Ok(code),
            Err(error) => {
                last_error = Some(error);
                if attempt < max_attempts {
                    thread::sleep(retry_delay);
                }
            }
        }
    }

    match last_error {
        Some(error) => Err(error),
        None => bail!("panel bootstrap retry finished without making a request"),
    }
}

fn update_setup_progress(progress: &Arc<Mutex<String>>, msg: &str) {
    match progress.lock() {
        Ok(mut state) => {
            *state = msg.to_string();
        }
        Err(error) => {
            error!("Failed to update setup progress: {error}");
        }
    }
    info!("{msg}");
}

fn startup_failure_message(stage: &str, error: &anyhow::Error, config: &AppConfig) -> String {
    let log_path = config.log_dir.join("kernel.log");
    format!(
        "Error: {stage} failed — {error}. See {}",
        log_path.display()
    )
}

fn start_kernel_and_bootstrap(
    km: &Arc<Mutex<KernelManager>>,
    port: u16,
    bootstrap_secret: &str,
    progress: &Arc<Mutex<String>>,
) -> AnyResult<String> {
    let mut recovered_conflict = false;

    loop {
        update_setup_progress(
            progress,
            if recovered_conflict {
                "Retrying Kernel startup after recovering a stale listener..."
            } else {
                "Starting Kernel..."
            },
        );

        {
            let mut kernel = km
                .lock()
                .map_err(|error| anyhow!("kernel manager lock poisoned: {error}"))?;
            kernel.start()?;
        }

        update_setup_progress(progress, "Waiting for Kernel...");
        if let Err(error) = health_check::wait_for_healthy(port, 60) {
            if recovered_conflict {
                return Err(error);
            }

            let recovered = {
                let mut kernel = km
                    .lock()
                    .map_err(|lock_error| anyhow!("kernel manager lock poisoned: {lock_error}"))?;
                kernel.recover_port_conflict()?
            };

            if let Some(message) = recovered {
                warn!("{message}");
                recovered_conflict = true;
                continue;
            }

            return Err(error);
        }

        update_setup_progress(progress, "Authorizing panel session...");
        match request_panel_bootstrap_code_with_retry(port, bootstrap_secret) {
            Ok(code) => return Ok(code),
            Err(error) => {
                if recovered_conflict {
                    return Err(error);
                }

                let recovered = {
                    let mut kernel = km.lock().map_err(|lock_error| {
                        anyhow!("kernel manager lock poisoned: {lock_error}")
                    })?;
                    kernel.recover_port_conflict()?
                };

                if let Some(message) = recovered {
                    warn!("{message}");
                    recovered_conflict = true;
                    continue;
                }

                return Err(error);
            }
        }
    }
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
                .context("failed to resolve resource_dir")?;
            let app_data_dir = app
                .path()
                .app_data_dir()
                .context("failed to resolve app_data_dir")?;

            let config = AppConfig::detect_for_tauri(resource_dir, app_data_dir)
                .context("failed to build AppConfig")?;

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
                update_setup_progress(&progress_arc, "Checking Python environment...");
                if let Err(e) = python_env::ensure_python_env(&config) {
                    let msg = startup_failure_message("Python setup", &e, &config);
                    error!("{msg}");
                    update_setup_progress(&progress_arc, &msg);
                    return;
                }

                let panel_code = match start_kernel_and_bootstrap(
                    &km_for_thread,
                    port,
                    &panel_bootstrap_secret,
                    &progress_arc,
                ) {
                    Ok(code) => code,
                    Err(e) => {
                        let msg = startup_failure_message("Viewer startup", &e, &config);
                        error!("{msg}");
                        update_setup_progress(&progress_arc, &msg);
                        return;
                    }
                };

                update_setup_progress(&progress_arc, "Ready");

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
        .unwrap_or_else(|error| error!("error while running tauri application: {error}"));
}
