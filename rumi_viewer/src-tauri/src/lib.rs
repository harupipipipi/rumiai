//! Rumi Viewer — Tauri application library.
//!
//! V2: Full implementation with setup hook, commands, tray menu, and navigation guard.

mod config;
mod desktop_system_info;
mod health_check;
mod kernel_manager;
mod process_utils;
mod python_env;
mod tray;
mod updater;

use std::net::TcpListener;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use std::{fs, io};

use anyhow::{anyhow, bail, Context, Result as AnyResult};
use log::{error, info, warn};
use rand::{distributions::Alphanumeric, Rng};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager};

use config::AppConfig;
use kernel_manager::KernelManager;

mod dock_registration;

/// Wrapper around a shared progress string, managed as Tauri State.
pub struct SetupProgress(pub Arc<Mutex<String>>);
pub struct ShutdownState(pub Arc<AtomicBool>);
pub struct AllowedNavigationPorts(pub Arc<Mutex<Vec<u16>>>);

const PRIMARY_WINDOW_LABELS: [&str; 2] = ["panel", "main"];
const DEFAULTSPACK_RESERVED_PORT: u16 = 8766;

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

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
struct WindowRuntimeSnapshot {
    label: String,
    visible: bool,
    minimized: bool,
    focused: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
struct BackgroundControlStatus {
    enabled: bool,
    app_visible: bool,
    foreground_window: Option<String>,
    kernel_running: bool,
    shutdown_requested: bool,
    windows: Vec<WindowRuntimeSnapshot>,
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

#[tauri::command]
fn reauthorize_panel_session(
    config: tauri::State<'_, AppConfig>,
    km: tauri::State<'_, Arc<Mutex<KernelManager>>>,
) -> Result<String, String> {
    request_fresh_panel_session_code(&config, km.inner())
        .map_err(|error| format!("panel reauthorization failed: {error}"))
}

#[tauri::command]
fn open_external_url(url: String) -> Result<(), String> {
    if !(url.starts_with("https://") || url.starts_with("http://")) {
        return Err("only http(s) URLs can be opened externally".into());
    }

    open::that_detached(url).map_err(|error| format!("failed to open external url: {error}"))
}

#[tauri::command]
fn send_to_background(app: AppHandle) -> Result<(), String> {
    send_app_to_background(&app)
}

#[tauri::command]
fn show_app_window(app: AppHandle) -> Result<(), String> {
    show_primary_window(&app)
}

#[tauri::command]
fn get_background_control_status(
    app: AppHandle,
    km: tauri::State<'_, Arc<Mutex<KernelManager>>>,
    shutdown: tauri::State<'_, ShutdownState>,
) -> Result<BackgroundControlStatus, String> {
    let kernel_running = {
        let mut kernel = km.lock().map_err(|error| format!("lock error: {error}"))?;
        kernel.is_running()
    };
    let shutdown_requested = shutdown.0.load(Ordering::SeqCst);
    Ok(summarize_background_control_status(
        collect_primary_window_states(&app),
        kernel_running,
        shutdown_requested,
    ))
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

fn is_loopback_port_available(port: u16) -> bool {
    match TcpListener::bind(("127.0.0.1", port)) {
        Ok(listener) => {
            drop(listener);
            true
        }
        Err(error) if error.kind() == io::ErrorKind::AddrInUse => false,
        Err(error) => {
            warn!("Could not probe loopback port {port}: {error}");
            false
        }
    }
}

fn existing_kernel_accepts_bootstrap(port: u16, bootstrap_secret: &str) -> bool {
    health_check::check_health(port).unwrap_or(false)
        && request_panel_bootstrap_code(port, bootstrap_secret).is_ok()
}

fn resolve_available_kernel_port_with_checks<PortAvailable, ExistingKernelReusable>(
    preferred_port: u16,
    mut port_available: PortAvailable,
    mut existing_kernel_reusable: ExistingKernelReusable,
) -> u16
where
    PortAvailable: FnMut(u16) -> bool,
    ExistingKernelReusable: FnMut(u16) -> bool,
{
    if port_available(preferred_port) || existing_kernel_reusable(preferred_port) {
        return preferred_port;
    }

    let last_candidate = preferred_port.saturating_add(128);
    for port in preferred_port.saturating_add(1)..=last_candidate {
        if port == DEFAULTSPACK_RESERVED_PORT {
            continue;
        }
        if port_available(port) {
            return port;
        }
    }

    preferred_port
}

fn resolve_available_kernel_port(config: &AppConfig, bootstrap_secret: &str) -> u16 {
    let preferred_port = config.kernel_port;
    let port = resolve_available_kernel_port_with_checks(
        preferred_port,
        is_loopback_port_available,
        |candidate| existing_kernel_accepts_bootstrap(candidate, bootstrap_secret),
    );

    if port != preferred_port {
        warn!(
            "Kernel port {preferred_port} is already occupied by another local process; using {port} for this Viewer session"
        );
    }

    port
}

fn set_allowed_navigation_ports(state: &Arc<Mutex<Vec<u16>>>, ports: Vec<u16>) {
    let mut deduped = ports;
    deduped.sort_unstable();
    deduped.dedup();
    match state.lock() {
        Ok(mut allowed_ports) => {
            *allowed_ports = deduped;
        }
        Err(error) => {
            error!("Allowed navigation port lock poisoned: {error}");
        }
    }
}

fn navigation_is_allowed(
    scheme: &str,
    host: &str,
    port: Option<u16>,
    allowed_ports: &[u16],
) -> bool {
    if scheme == "tauri" {
        return true;
    }
    scheme == "http"
        && (host == "localhost" || host == "127.0.0.1")
        && port.is_some_and(|candidate| allowed_ports.contains(&candidate))
}

fn ensure_kernel_ready_for_panel_auth(
    config: &AppConfig,
    km: &Arc<Mutex<KernelManager>>,
) -> AnyResult<()> {
    let port = config.kernel_port;
    if health_check::check_health(port)? {
        return Ok(());
    }

    if health_check::wait_for_healthy(port, 5).is_ok() {
        return Ok(());
    }

    let mut kernel = km
        .lock()
        .map_err(|error| anyhow!("kernel manager lock poisoned: {error}"))?;
    if kernel.is_running() {
        kernel.restart()?;
    } else {
        kernel.start()?;
    }
    drop(kernel);

    health_check::wait_for_healthy(port, 60)?;
    Ok(())
}

fn request_fresh_panel_session_code(
    config: &AppConfig,
    km: &Arc<Mutex<KernelManager>>,
) -> AnyResult<String> {
    ensure_kernel_ready_for_panel_auth(config, km)?;
    let bootstrap_secret = load_or_create_panel_bootstrap_secret(config)
        .context("failed to load persisted panel bootstrap secret")?;
    request_panel_bootstrap_code_with_retry(config.kernel_port, &bootstrap_secret)
}

fn navigate_window_to_panel_session(
    window: &tauri::WebviewWindow,
    port: u16,
    panel_code: &str,
) -> Result<(), tauri::Error> {
    let panel_code = serde_json::to_string(panel_code).unwrap_or_else(|_| "\"\"".into());
    let loopback_origin = serde_json::to_string(&format!("http://127.0.0.1:{port}"))
        .unwrap_or_else(|_| "\"\"".into());
    let localhost_origin = serde_json::to_string(&format!("http://localhost:{port}"))
        .unwrap_or_else(|_| "\"\"".into());

    let js = format!(
        r#"
(() => {{
  const code = {panel_code};
  const loopbackOrigin = {loopback_origin};
  const localhostOrigin = {localhost_origin};
  let nextUrl = `${{loopbackOrigin}}/panel/?code=${{encodeURIComponent(code)}}`;

  try {{
    const current = new URL(window.location.href);
    const isPanelRoute =
      (current.origin === loopbackOrigin || current.origin === localhostOrigin) &&
      current.pathname.startsWith('/panel');

    if (isPanelRoute) {{
      current.searchParams.set('code', code);
      nextUrl = current.pathname + current.search + current.hash;
    }}
  }} catch (_error) {{
    // Fall back to the default panel entrypoint.
  }}

  window.location.replace(nextUrl);
}})();
"#
    );

    window.eval(&js)
}

pub(crate) fn refresh_panel_session_for_window(app: &AppHandle, window_label: &str) {
    let config = app.state::<AppConfig>().inner().clone();
    let km = Arc::clone(app.state::<Arc<Mutex<KernelManager>>>().inner());
    let handle = app.clone();
    let label = window_label.to_string();

    std::thread::spawn(
        move || match request_fresh_panel_session_code(&config, &km) {
            Ok(panel_code) => {
                if let Some(win) = handle.get_webview_window(&label) {
                    if let Err(error) =
                        navigate_window_to_panel_session(&win, config.kernel_port, &panel_code)
                    {
                        error!("Failed to refresh panel session for {label}: {error}");
                    }
                }
            }
            Err(error) => {
                warn!("Failed to refresh panel session for {label}: {error}");
            }
        },
    );
}

pub(crate) fn primary_window_label(has_panel: bool, has_main: bool) -> Option<&'static str> {
    if has_panel {
        Some("panel")
    } else if has_main {
        Some("main")
    } else {
        None
    }
}

pub(crate) fn show_primary_window(app: &AppHandle) -> Result<(), String> {
    let target = primary_window_label(
        app.get_webview_window("panel").is_some(),
        app.get_webview_window("main").is_some(),
    );

    let Some(label) = target else {
        return Err("no Rumi window is available".into());
    };

    refresh_panel_session_for_window(app, label);
    if let Some(window) = app.get_webview_window(label) {
        window
            .unminimize()
            .map_err(|error| format!("failed to unminimize window: {error}"))?;
        window
            .show()
            .map_err(|error| format!("failed to show window: {error}"))?;
        window
            .set_focus()
            .map_err(|error| format!("failed to focus window: {error}"))?;
    }

    Ok(())
}

pub(crate) fn send_app_to_background(app: &AppHandle) -> Result<(), String> {
    let mut found_window = false;
    for label in PRIMARY_WINDOW_LABELS {
        if let Some(window) = app.get_webview_window(label) {
            found_window = true;
            window
                .hide()
                .map_err(|error| format!("failed to hide {label} window: {error}"))?;
        }
    }

    if !found_window {
        warn!("Background request ignored because no Rumi window is available");
    }

    Ok(())
}

fn collect_primary_window_states(app: &AppHandle) -> Vec<WindowRuntimeSnapshot> {
    PRIMARY_WINDOW_LABELS
        .iter()
        .filter_map(|label| {
            app.get_webview_window(label)
                .map(|window| WindowRuntimeSnapshot {
                    label: (*label).to_string(),
                    visible: window.is_visible().unwrap_or(false),
                    minimized: window.is_minimized().unwrap_or(false),
                    focused: window.is_focused().unwrap_or(false),
                })
        })
        .collect()
}

fn summarize_background_control_status(
    windows: Vec<WindowRuntimeSnapshot>,
    kernel_running: bool,
    shutdown_requested: bool,
) -> BackgroundControlStatus {
    let app_visible = windows
        .iter()
        .any(|window| window.visible && !window.minimized);
    let foreground_window = windows
        .iter()
        .find(|window| window.visible && window.focused)
        .or_else(|| {
            windows
                .iter()
                .find(|window| window.visible && !window.minimized)
        })
        .map(|window| window.label.clone());

    BackgroundControlStatus {
        enabled: !shutdown_requested,
        app_visible,
        foreground_window,
        kernel_running,
        shutdown_requested,
        windows,
    }
}

pub(crate) fn request_app_exit(app: &AppHandle) {
    let shutdown_flag = Arc::clone(&app.state::<ShutdownState>().inner().0);
    if shutdown_flag.swap(true, Ordering::SeqCst) {
        return;
    }

    for label in ["panel", "main"] {
        if let Some(window) = app.get_webview_window(label) {
            let _ = window.hide();
        }
    }

    let km = Arc::clone(app.state::<Arc<Mutex<KernelManager>>>().inner());
    let handle = app.clone();

    std::thread::spawn(move || {
        match km.lock() {
            Ok(mut kernel) => {
                if let Err(error) = kernel.stop() {
                    error!("Failed to stop kernel during shutdown: {error}");
                }
            }
            Err(error) => {
                error!("Failed to lock kernel manager during shutdown: {error}");
            }
        }

        handle.exit(0);
    });
}

fn spawn_kernel_exit_monitor(
    app: AppHandle,
    config: AppConfig,
    km: Arc<Mutex<KernelManager>>,
    shutdown_flag: Arc<AtomicBool>,
    panel_bootstrap_secret: String,
) {
    thread::spawn(move || loop {
        if shutdown_flag.load(Ordering::SeqCst) {
            break;
        }

        let mut restarted = false;
        match km.lock() {
            Ok(mut kernel) => {
                if !kernel.is_running() {
                    match kernel.wait_and_handle_restart() {
                        Ok(true) => match kernel.start() {
                            Ok(()) => {
                                restarted = true;
                                info!("Kernel restart handoff completed");
                            }
                            Err(error) => {
                                error!("Failed to restart Kernel after handoff: {error}");
                            }
                        },
                        Ok(false) => {}
                        Err(error) => {
                            warn!("Failed to inspect Kernel exit status: {error}");
                        }
                    }
                }
            }
            Err(error) => {
                error!("Failed to lock kernel manager for exit monitor: {error}");
            }
        }

        if restarted {
            match health_check::wait_for_healthy(config.kernel_port, 60).and_then(|_| {
                request_panel_bootstrap_code_with_retry(config.kernel_port, &panel_bootstrap_secret)
            }) {
                Ok(panel_code) => {
                    if let Some(win) = app.get_webview_window("main") {
                        if let Err(error) =
                            navigate_window_to_panel_session(&win, config.kernel_port, &panel_code)
                        {
                            error!("Failed to refresh panel after Kernel restart: {error}");
                        }
                    }
                }
                Err(error) => {
                    warn!("Kernel restarted, but panel session refresh failed: {error}");
                }
            }
        }

        thread::sleep(Duration::from_millis(500));
    });
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

    let allowed_navigation_ports = Arc::new(Mutex::new(vec![8765]));
    let allowed_navigation_ports_for_plugin = Arc::clone(&allowed_navigation_ports);
    let allowed_navigation_ports_for_setup = Arc::clone(&allowed_navigation_ports);

    tauri::Builder::default()
        .plugin(
            tauri::plugin::Builder::<tauri::Wry, ()>::new("nav-guard")
                .on_navigation(move |_webview, url| {
                    let scheme = url.scheme();
                    let host = url.host_str().unwrap_or("");
                    let port = url.port_or_known_default();
                    let allowed_ports = allowed_navigation_ports_for_plugin
                        .lock()
                        .map(|ports| ports.clone())
                        .unwrap_or_default();
                    let allowed = navigation_is_allowed(scheme, host, port, &allowed_ports);

                    if !allowed {
                        log::warn!("Blocked navigation to: {url}");
                    }
                    allowed
                })
                .build(),
        )
        .setup(move |app| {
            let resource_dir = app
                .path()
                .resource_dir()
                .context("failed to resolve resource_dir")?;
            let app_data_dir = app
                .path()
                .app_data_dir()
                .context("failed to resolve app_data_dir")?;

            let mut config = AppConfig::detect_for_tauri(resource_dir, app_data_dir)
                .context("failed to build AppConfig")?;

            std::fs::create_dir_all(&config.log_dir).ok();
            std::fs::create_dir_all(&config.user_data_dir).ok();

            let progress = SetupProgress(Arc::new(Mutex::new(
                "Initializing...".to_string(),
            )));
            let progress_arc = progress.0.clone();
            app.manage(progress);
            app.manage(ShutdownState(Arc::new(AtomicBool::new(false))));

            let panel_bootstrap_secret = load_or_create_panel_bootstrap_secret(&config)
                .context("failed to load persisted panel bootstrap secret")?;
            config.kernel_port = resolve_available_kernel_port(&config, &panel_bootstrap_secret);
            set_allowed_navigation_ports(
                &allowed_navigation_ports_for_setup,
                vec![config.kernel_port, DEFAULTSPACK_RESERVED_PORT],
            );
            app.manage(AllowedNavigationPorts(Arc::clone(
                &allowed_navigation_ports_for_setup,
            )));
            let km = Arc::new(Mutex::new(KernelManager::new(
                &config,
                panel_bootstrap_secret.clone(),
            )));
            let km_for_thread = km.clone();
            let km_for_monitor = km.clone();
            app.manage(km);

            app.manage(config.clone());

            if let Some(win) = app.get_webview_window("main") {
                let _ = win.show();
            }

            let handle = app.handle().clone();
            let monitor_handle = app.handle().clone();
            let port = config.kernel_port;

            spawn_kernel_exit_monitor(
                monitor_handle,
                config.clone(),
                km_for_monitor,
                Arc::clone(&app.state::<ShutdownState>().inner().0),
                panel_bootstrap_secret.clone(),
            );

            std::thread::spawn(move || {
                // --- Fast path: existing healthy kernel ---
                update_setup_progress(Some(&handle), &progress_arc, "Checking for existing session...");
                if let Ok(true) = health_check::check_health(port) {
                    info!("Existing healthy kernel detected on port {port}, attempting fast-path bootstrap...");
                    match request_panel_bootstrap_code_with_retry(port, &panel_bootstrap_secret) {
                        Ok(panel_code) => {
                            update_setup_progress(Some(&handle), &progress_arc, "Ready");
                            if let Some(win) = handle.get_webview_window("main") {
                                if let Err(e) =
                                    navigate_window_to_panel_session(&win, port, &panel_code)
                                {
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
                    if let Err(e) = navigate_window_to_panel_session(&win, port, &panel_code) {
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
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                if let Err(error) = send_app_to_background(&window.app_handle()) {
                    error!("Failed to send app to background: {error}");
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            get_setup_progress,
            restart_kernel,
            reauthorize_panel_session,
            open_external_url,
            send_to_background,
            show_app_window,
            get_background_control_status,
            desktop_system_info::get_desktop_system_info,
            dock_registration::register_defaultspack_dock,
            dock_registration::launch_defaultspack_desktop
        ])
        .build(tauri::generate_context!())
        .map(|app| {
            app.run(|app_handle, event| {
                #[cfg(target_os = "macos")]
                if let tauri::RunEvent::Reopen {
                    has_visible_windows: false,
                    ..
                } = event
                {
                    if let Err(error) = show_primary_window(app_handle) {
                        warn!("Failed to reopen primary window: {error}");
                    }
                }

                #[cfg(not(target_os = "macos"))]
                {
                    let _ = (app_handle, event);
                }
            });
        })
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
    fn prefers_panel_window_when_available() {
        assert_eq!(primary_window_label(true, true), Some("panel"));
    }

    #[test]
    fn falls_back_to_main_window_before_panel_exists() {
        assert_eq!(primary_window_label(false, true), Some("main"));
    }

    #[test]
    fn returns_none_when_no_window_exists() {
        assert_eq!(primary_window_label(false, false), None);
    }

    #[test]
    fn background_status_reports_visible_foreground_window() {
        let status = summarize_background_control_status(
            vec![
                WindowRuntimeSnapshot {
                    label: "panel".into(),
                    visible: false,
                    minimized: false,
                    focused: false,
                },
                WindowRuntimeSnapshot {
                    label: "main".into(),
                    visible: true,
                    minimized: false,
                    focused: true,
                },
            ],
            true,
            false,
        );

        assert!(status.enabled);
        assert!(status.app_visible);
        assert!(status.kernel_running);
        assert_eq!(status.foreground_window.as_deref(), Some("main"));
    }

    #[test]
    fn background_status_stays_enabled_when_all_windows_are_hidden() {
        let status = summarize_background_control_status(
            vec![WindowRuntimeSnapshot {
                label: "main".into(),
                visible: false,
                minimized: false,
                focused: false,
            }],
            true,
            false,
        );

        assert!(status.enabled);
        assert!(!status.app_visible);
        assert_eq!(status.foreground_window, None);
        assert!(status.kernel_running);
    }

    #[test]
    fn background_status_disables_during_shutdown() {
        let status = summarize_background_control_status(Vec::new(), false, true);

        assert!(!status.enabled);
        assert!(status.shutdown_requested);
        assert!(!status.kernel_running);
    }

    #[test]
    fn resolve_kernel_port_keeps_available_preferred_port() {
        let port = resolve_available_kernel_port_with_checks(
            8765,
            |candidate| candidate == 8765,
            |_| false,
        );

        assert_eq!(port, 8765);
    }

    #[test]
    fn resolve_kernel_port_reuses_existing_kernel_when_bootstrap_matches() {
        let port = resolve_available_kernel_port_with_checks(
            8765,
            |_| false,
            |candidate| candidate == 8765,
        );

        assert_eq!(port, 8765);
    }

    #[test]
    fn resolve_kernel_port_skips_defaultspack_port_when_falling_back() {
        let port = resolve_available_kernel_port_with_checks(
            8765,
            |candidate| candidate == 8767,
            |_| false,
        );

        assert_eq!(port, 8767);
    }

    #[test]
    fn navigation_guard_allows_only_resolved_loopback_ports() {
        let allowed_ports = vec![8767, DEFAULTSPACK_RESERVED_PORT];

        assert!(navigation_is_allowed(
            "http",
            "localhost",
            Some(8767),
            &allowed_ports
        ));
        assert!(navigation_is_allowed(
            "http",
            "127.0.0.1",
            Some(8766),
            &allowed_ports
        ));
        assert!(navigation_is_allowed("tauri", "", None, &allowed_ports));
        assert!(!navigation_is_allowed(
            "http",
            "localhost",
            Some(8765),
            &allowed_ports
        ));
        assert!(!navigation_is_allowed(
            "http",
            "127.0.0.1",
            Some(9999),
            &allowed_ports
        ));
        assert!(!navigation_is_allowed(
            "https",
            "localhost",
            Some(8767),
            &allowed_ports
        ));
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
