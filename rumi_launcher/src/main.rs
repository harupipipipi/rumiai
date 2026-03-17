//! Rumi AI Launcher — native system-tray application.
//!
//! Startup flow:
//! 1. Detect paths (`AppConfig::detect`)
//! 2. Bootstrap Python environment (PBS + uv + venv)
//! 3. Start Kernel (`app.py`)
//! 4. Wait for health-check
//! 5. Open browser
//! 6. Enter tray-icon event loop (menu actions + Kernel monitoring)

mod config;
mod health_check;
mod kernel_manager;
mod python_env;
mod updater;

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use log::{error, info, warn};
use tray_icon::menu::{Menu, MenuEvent, MenuItem, PredefinedMenuItem};
use tray_icon::{Icon, TrayIconBuilder};

use config::AppConfig;
use kernel_manager::KernelManager;

/// Build a tray icon from `assets/icon.png` if available, otherwise
/// synthesise a small solid-colour fallback.
fn load_tray_icon(config: &AppConfig) -> Icon {
    let candidates = [
        config.app_dir.join("rumi_launcher").join("assets").join("icon.png"),
        config.app_dir.join("assets").join("icon.png"),
    ];

    for path in &candidates {
        if path.exists() {
            match image::open(path) {
                Ok(img) => {
                    let rgba = img.to_rgba8();
                    let (w, h) = rgba.dimensions();
                    if let Ok(icon) = Icon::from_rgba(rgba.into_raw(), w, h) {
                        info!("Loaded tray icon from {}", path.display());
                        return icon;
                    }
                }
                Err(e) => warn!("Failed to load icon {}: {e}", path.display()),
            }
        }
    }

    // Fallback: 16x16 magenta.
    info!("Using fallback tray icon (no icon.png found)");
    let size: u32 = 16;
    let mut rgba = Vec::with_capacity((size * size * 4) as usize);
    for _ in 0..(size * size) {
        rgba.extend_from_slice(&[0xE0, 0x40, 0xE0, 0xFF]);
    }
    Icon::from_rgba(rgba, size, size).expect("fallback icon must succeed")
}

fn run() -> Result<()> {
    env_logger::init();
    info!("Rumi Launcher starting …");

    // ---- 1. Configuration --------------------------------------------------
    let config = AppConfig::detect().context("failed to detect app configuration")?;
    info!("app_dir   = {}", config.app_dir.display());
    info!("rumi_home = {}", config.rumi_home.display());

    std::fs::create_dir_all(&config.log_dir)
        .context("failed to create log directory")?;
    std::fs::create_dir_all(config.user_data_dir.join("settings"))
        .context("failed to create user_data/settings directory")?;

    // ---- 2. Python environment ---------------------------------------------
    python_env::ensure_python_env(&config)
        .context("Python environment setup failed")?;
    info!("Python environment ready");

    // ---- 3. Start Kernel ---------------------------------------------------
    let mut kernel = KernelManager::new(&config);
    kernel.start().context("failed to start Kernel")?;

    // ---- 4. Health check ---------------------------------------------------
    health_check::wait_for_healthy(config.kernel_port, 30)
        .context("Kernel health-check failed")?;
    info!("Kernel is healthy");

    // ---- 5. Open browser ---------------------------------------------------
    let url = format!("http://localhost:{}", config.kernel_port);
    if let Err(e) = open::that(&url) {
        warn!("Could not open browser: {e}");
    }

    // ---- 6. Update check (best-effort) -------------------------------------
    match updater::check_for_update() {
        Ok(Some(ver)) => info!("Update available: {ver}"),
        Ok(None) => {}
        Err(e) => warn!("Update check failed: {e}"),
    }

    // ---- 7. System tray ----------------------------------------------------
    let icon = load_tray_icon(&config);

    let item_open = MenuItem::new("Open Rumi AI", true, None);
    let item_restart = MenuItem::new("Restart Kernel", true, None);
    let item_quit = MenuItem::new("Quit", true, None);

    let tray_menu = Menu::new();
    tray_menu.append(&item_open).context("menu append failed")?;
    tray_menu.append(&item_restart).context("menu append failed")?;
    tray_menu
        .append(&PredefinedMenuItem::separator())
        .context("menu append failed")?;
    tray_menu.append(&item_quit).context("menu append failed")?;

    // Keep `_tray` alive for the lifetime of the event loop.
    let _tray = TrayIconBuilder::new()
        .with_menu(Box::new(tray_menu))
        .with_tooltip("Rumi AI")
        .with_icon(icon)
        .build()
        .context("failed to build tray icon")?;

    let id_open = item_open.id().clone();
    let id_restart = item_restart.id().clone();
    let id_quit = item_quit.id().clone();

    // Ctrl+C flag — Drop impl on KernelManager will stop the child.
    let quit = Arc::new(AtomicBool::new(false));
    {
        let q = Arc::clone(&quit);
        thread::spawn(move || {
            // Park forever; on process signal Drop takes care of cleanup.
            loop {
                thread::sleep(Duration::from_secs(3600));
                if q.load(Ordering::SeqCst) {
                    break;
                }
            }
        });
    }

    let menu_rx = MenuEvent::receiver();
    let mut last_health = Instant::now();

    info!("Entering event loop");
    loop {
        // ---- Menu events ---------------------------------------------------
        if let Ok(event) = menu_rx.try_recv() {
            if event.id() == &id_open {
                let u = format!("http://localhost:{}", config.kernel_port);
                if let Err(e) = open::that(&u) {
                    error!("Open browser failed: {e}");
                }
            } else if event.id() == &id_restart {
                info!("User requested Kernel restart");
                if let Err(e) = kernel.restart() {
                    error!("Kernel restart failed: {e}");
                }
            } else if event.id() == &id_quit {
                info!("Quit requested");
                break;
            }
        }

        // ---- Kernel liveness (every 2 s) -----------------------------------
        if last_health.elapsed() >= Duration::from_secs(2) {
            last_health = Instant::now();

            if !kernel.is_running() {
                match kernel.wait_and_handle_restart() {
                    Ok(true) => {
                        info!("Auto-restarting Kernel (exit code 42) …");
                        if let Err(e) = kernel.start() {
                            error!("Auto-restart failed: {e}");
                        }
                    }
                    Ok(false) => {
                        warn!("Kernel stopped unexpectedly");
                        if let Err(e) =
                            _tray.set_tooltip(Some("Rumi AI — Kernel stopped"))
                        {
                            warn!("Tooltip update failed: {e}");
                        }
                    }
                    Err(e) => {
                        error!("Kernel wait error: {e}");
                    }
                }
            }
        }

        // ---- External quit flag --------------------------------------------
        if quit.load(Ordering::SeqCst) {
            break;
        }

        thread::sleep(Duration::from_millis(50));
    }

    // ---- Cleanup -----------------------------------------------------------
    info!("Shutting down …");
    kernel.stop().ok();
    info!("Goodbye");
    Ok(())
}

fn main() {
    if let Err(e) = run() {
        eprintln!("FATAL: {e:#}");
        std::process::exit(1);
    }
}
