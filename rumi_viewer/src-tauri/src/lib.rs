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
use std::{fs, io};
use std::thread;
use std::time::Duration;

use anyhow::{anyhow, bail, Context, Result as AnyResult};
use log::{error, info, warn};
use rand::{distributions::Alphanumeric, Rng};
use serde::Deserialize;
use tauri::{AppHandle, Emitter, Manager};

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

fn load_or_create_panel_bootstrap_secret(config: &AppConfig) -> AnyResult<String> {
    let path = config.panel_bootstrap_secret_path();
    match fs::read_to_string(&path) {
        Ok(existing) => {
            let trimmed = existing.trim();
            if !trimmed.is_empty() {
                return Ok(trimmed.to_string());
            }
        }
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(error) => {
            warn!(
                "Failed to read persisted panel bootstrap secret from {}: {error}",
                path.display()
            );
        }
    }

    let secret = generate_panel_bootstrap_secret();
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).with_context(|| {
            format!(
                "failed to create parent directory for bootstrap secret at {}",
                path.display()
            )
        })?;
    }
    fs::write(&path, &secret).with_context(|| {
        format!(
            "failed to persist panel bootstrap secret at {}",
            path.display()
        )
    })?;
    Ok(secret)
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

fn update_setup_progress(app_handle: Option<&AppHandle>, progress: &Arc<Mutex<String>>, msg: &str) {
    match progress.lock() {
        Ok(mut state) => {
            *state = msg.to_string();
        }
        Err(error) => {
            error!("Failed to update setup progress: {error}");
        }
    }
    if let Some(handle) = app_handle {
        let _ = handle.emit("setup-progress", msg);
    }
    info!("{msg}");
}

fn run_delayed_update_check() {
    thread::sleep(Duration::from_secs(5));
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
}

fn startup_failure_message(stage: &str, error: &anyhow::Error, config: &AppConfig) -> String {
    let log_path = config.log_dir.join("kernel.log");
    format!(
        "Error: {stage} failed — {error}. See {}",
        log_path.display()
    )
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum StartupRecoveryStage {
    HealthCheck,
    Bootstrap,
}

fn run_startup_sequence<StartKernel, WaitForHealthy, AuthorizePanel, RecoverConflict>(
    app_handle: Option<&AppHandle>,
    progress: &Arc<Mutex<String>>,
    mut start_kernel: StartKernel,
    mut wait_for_healthy: WaitForHealthy,
    mut authorize_panel: AuthorizePanel,
    mut recover_conflict: RecoverConflict,
) -> AnyResult<String>
where
    StartKernel: FnMut() -> AnyResult<()>,
    WaitForHealthy: FnMut() -> AnyResult<()>,
    AuthorizePanel: FnMut() -> AnyResult<String>,
    RecoverConflict: FnMut(StartupRecoveryStage) -> AnyResult<Option<String>>,
{
    let mut recovered_conflict = false;

    loop {
        update_setup_progress(
            app_handle,
            progress,
            if recovered_conflict {
                "Retrying Kernel startup after recovering a stale listener..."
            } else {
                "Starting Kernel..."
            },
        );

        start_kernel()?;

        update_setup_progress(app_handle, progress, "Waiting for Kernel...");
        if let Err(error) = wait_for_healthy() {
            if recovered_conflict {
                return Err(error);
            }

            if let Some(message) = recover_conflict(StartupRecoveryStage::HealthCheck)? {
                warn!("{message}");
                recovered_conflict = true;
                continue;
            }

            return Err(error);
        }

        update_setup_progress(app_handle, progress, "Authorizing panel session...");
        match authorize_panel() {
            Ok(code) => return Ok(code),
            Err(error) => {
                if recovered_conflict {
                    return Err(error);
                }

                if let Some(message) = recover_conflict(StartupRecoveryStage::Bootstrap)? {
                    warn!("{message}");
                    recovered_conflict = true;
                    continue;
                }

                return Err(error);
            }
        }
    }
}

fn start_kernel_and_bootstrap(
    app_handle: &AppHandle,
    km: &Arc<Mutex<KernelManager>>,
    port: u16,
    bootstrap_secret: &str,
    progress: &Arc<Mutex<String>>,
) -> AnyResult<String> {
    run_startup_sequence(
        Some(app_handle),
        progress,
        || {
            let mut kernel = km
                .lock()
                .map_err(|error| anyhow!("kernel manager lock poisoned: {error}"))?;
            kernel.start()?;
            Ok(())
        },
        || {
            health_check::wait_for_healthy(port, 60)?;
            Ok(())
        },
        || request_panel_bootstrap_code_with_retry(port, bootstrap_secret),
        |_| {
            let mut kernel = km
                .lock()
                .map_err(|lock_error| anyhow!("kernel manager lock poisoned: {lock_error}"))?;
            kernel.recover_port_conflict()
        },
    )
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

            let panel_bootstrap_secret = load_or_create_panel_bootstrap_secret(&config)
                .context("failed to load persisted panel bootstrap secret")?;
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
                // --- Fast path: existing healthy kernel ---
                update_setup_progress(Some(&handle), &progress_arc, "Checking for existing session...");
                if let Ok(true) = health_check::check_health(port) {
                    info!("Existing healthy kernel detected on port {port}, attempting fast-path bootstrap...");
                    match request_panel_bootstrap_code_with_retry(port, &panel_bootstrap_secret) {
                        Ok(panel_code) => {
                            update_setup_progress(Some(&handle), &progress_arc, "Ready");
                            if let Some(win) = handle.get_webview_window("main") {
                                let js = format!(
                                    "window.location.replace('http://127.0.0.1:{port}/panel/?code={panel_code}')"
                                );
                                if let Err(e) = win.eval(&js) {
                                    error!("Failed to navigate to panel: {e}");
                                }
                            }
                            // Delayed background update check.
                            run_delayed_update_check();
                            return;
                        }
                        Err(e) => {
                            info!("Fast-path bootstrap failed: {e}, falling back to normal startup");
                        }
                    }
                }

                // --- Normal startup sequence ---
                update_setup_progress(Some(&handle), &progress_arc, "Checking Python environment...");
                if let Err(e) = python_env::ensure_python_env(&config) {
                    let msg = startup_failure_message("Python setup", &e, &config);
                    error!("{msg}");
                    update_setup_progress(Some(&handle), &progress_arc, &msg);
                    return;
                }

                let panel_code = match start_kernel_and_bootstrap(
                    &handle,
                    &km_for_thread,
                    port,
                    &panel_bootstrap_secret,
                    &progress_arc,
                ) {
                    Ok(code) => code,
                    Err(e) => {
                        let msg = startup_failure_message("Viewer startup", &e, &config);
                        error!("{msg}");
                        update_setup_progress(Some(&handle), &progress_arc, &msg);
                        return;
                    }
                };

                update_setup_progress(Some(&handle), &progress_arc, "Ready");

                if let Some(win) = handle.get_webview_window("main") {
                    let js = format!(
                        "window.location.replace('http://127.0.0.1:{port}/panel/?code={panel_code}')"
                    );
                    if let Err(e) = win.eval(&js) {
                        error!("Failed to navigate to panel: {e}");
                    }
                }

                // Delayed background update check.
                run_delayed_update_check();
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    use std::sync::{Mutex, OnceLock};
    use std::time::{SystemTime, UNIX_EPOCH};

    fn env_lock() -> &'static Mutex<()> {
        static ENV_LOCK: OnceLock<Mutex<()>> = OnceLock::new();
        ENV_LOCK.get_or_init(|| Mutex::new(()))
    }

    fn test_config() -> AppConfig {
        AppConfig::detect_for_tauri(
            PathBuf::from("/tmp/test_resource"),
            PathBuf::from("/tmp/test_appdata"),
        )
        .unwrap()
    }

    #[test]
    fn reuses_persisted_panel_bootstrap_secret() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_viewer_secret_{unique}"));
        let config =
            AppConfig::detect_for_tauri(root.join("resource"), root.join("appdata")).unwrap();

        let first = load_or_create_panel_bootstrap_secret(&config).unwrap();
        let second = load_or_create_panel_bootstrap_secret(&config).unwrap();

        assert_eq!(first, second);
        assert_eq!(
            fs::read_to_string(config.panel_bootstrap_secret_path())
                .unwrap()
                .trim(),
            first
        );

        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn is_running_default_false() {
        let config = test_config();
        let mut km = KernelManager::new(&config, "test-bootstrap".into());
        assert!(!km.is_running());
    }

    #[test]
    fn stop_without_start_is_ok() {
        let config = test_config();
        let mut km = KernelManager::new(&config, "test-bootstrap".into());
        assert!(km.stop().is_ok());
    }

    #[test]
    fn wait_and_handle_restart_no_child() {
        let config = test_config();
        let mut km = KernelManager::new(&config, "test-bootstrap".into());
        let result = km.wait_and_handle_restart().unwrap();
        assert!(!result);
    }

    #[test]
    fn explicit_auto_approve_opt_in_is_required() {
        let _guard = env_lock().lock().unwrap();
        std::env::remove_var("RUMI_AUTO_APPROVE_LOCAL");

        let dev_environment = true;
        let auto_approve_local = dev_environment
            && std::env::var("RUMI_AUTO_APPROVE_LOCAL")
                .map(|value| value.eq_ignore_ascii_case("true"))
                .unwrap_or(false);

        assert!(!auto_approve_local);
    }

    #[test]
    fn explicit_auto_approve_opt_in_only_applies_in_dev() {
        let _guard = env_lock().lock().unwrap();
        std::env::set_var("RUMI_AUTO_APPROVE_LOCAL", "true");

        let production_auto_approve = false
            && std::env::var("RUMI_AUTO_APPROVE_LOCAL")
                .map(|value| value.eq_ignore_ascii_case("true"))
                .unwrap_or(false);
        let development_auto_approve = true
            && std::env::var("RUMI_AUTO_APPROVE_LOCAL")
                .map(|value| value.eq_ignore_ascii_case("true"))
                .unwrap_or(false);

        assert!(!production_auto_approve);
        assert!(development_auto_approve);

        std::env::remove_var("RUMI_AUTO_APPROVE_LOCAL");
    }

    #[test]
    fn retries_startup_after_recovering_stale_listener_during_health_check() {
        let progress = Arc::new(Mutex::new(String::new()));
        let mut start_calls = 0;
        let mut health_calls = 0;
        let mut recover_stages = Vec::new();

        let panel_code = run_startup_sequence(
            None,
            &progress,
            || {
                start_calls += 1;
                Ok(())
            },
            || {
                health_calls += 1;
                if health_calls == 1 {
                    Err(anyhow!("health failed"))
                } else {
                    Ok(())
                }
            },
            || Ok("panel-code".into()),
            |stage| {
                recover_stages.push(stage);
                Ok(Some("Recovered stale listener".into()))
            },
        )
        .unwrap();

        assert_eq!(panel_code, "panel-code");
        assert_eq!(start_calls, 2);
        assert_eq!(health_calls, 2);
        assert_eq!(recover_stages, vec![StartupRecoveryStage::HealthCheck]);
        assert_eq!(
            progress.lock().unwrap().as_str(),
            "Authorizing panel session..."
        );
    }

    #[test]
    fn retries_startup_after_recovering_stale_listener_during_bootstrap() {
        let progress = Arc::new(Mutex::new(String::new()));
        let mut start_calls = 0;
        let mut bootstrap_calls = 0;
        let mut recover_stages = Vec::new();

        let panel_code = run_startup_sequence(
            None,
            &progress,
            || {
                start_calls += 1;
                Ok(())
            },
            || Ok(()),
            || {
                bootstrap_calls += 1;
                if bootstrap_calls == 1 {
                    Err(anyhow!("bootstrap failed"))
                } else {
                    Ok("panel-code".into())
                }
            },
            |stage| {
                recover_stages.push(stage);
                Ok(Some("Recovered stale listener".into()))
            },
        )
        .unwrap();

        assert_eq!(panel_code, "panel-code");
        assert_eq!(start_calls, 2);
        assert_eq!(bootstrap_calls, 2);
        assert_eq!(recover_stages, vec![StartupRecoveryStage::Bootstrap]);
    }

    #[test]
    fn does_not_retry_when_conflict_recovery_rejects_foreign_listener() {
        let progress = Arc::new(Mutex::new(String::new()));
        let mut start_calls = 0;
        let mut recover_calls = 0;

        let error = run_startup_sequence(
            None,
            &progress,
            || {
                start_calls += 1;
                Ok(())
            },
            || Err(anyhow!("health failed")),
            || Ok("panel-code".into()),
            |stage| {
                recover_calls += 1;
                assert_eq!(stage, StartupRecoveryStage::HealthCheck);
                Err(anyhow!(
                    "port 8765 is already in use by pid 999 (foreign process)"
                ))
            },
        )
        .unwrap_err();

        assert_eq!(start_calls, 1);
        assert_eq!(recover_calls, 1);
        assert!(error
            .to_string()
            .contains("port 8765 is already in use by pid 999"));
    }
}
