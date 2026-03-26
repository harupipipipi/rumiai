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

pub fn run() {
    env_logger::init();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(
            tauri::plugin::Builder::<tauri::Wry, ()>::new("nav-guard")
                .on_navigation(|_webview, url| {
                    let scheme = url.scheme();
                    let host = url.host_str().unwrap_or("");
                    let port = url.port();

                    let allowed = scheme == "tauri"
                        || (scheme == "http"
                            && host == "localhost"
                            && (port == Some(8765)
                                || cfg!(debug_assertions)));

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

                set_progress("Ready");

                if let Some(win) = handle.get_webview_window("main") {
                    let js = format!(
                        "window.location.replace('http://localhost:{port}/panel/')"
                    );
                    if let Err(e) = win.eval(&js) {
                        error!("Failed to navigate to panel: {e}");
                    }
                }
            });

            tray::setup_tray(app)?;

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![get_setup_progress, restart_kernel])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
