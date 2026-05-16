//! System tray icon and menu for Rumi Viewer.

use std::sync::{Arc, Mutex};

use log::{error, info};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager,
};

use crate::kernel_manager::KernelManager;
use crate::updater;
use crate::{request_app_exit, show_primary_window};

/// Helper: clone the Arc<Mutex<KernelManager>> out of Tauri State.
fn get_km(app: &tauri::AppHandle) -> Arc<Mutex<KernelManager>> {
    Arc::clone(app.state::<Arc<Mutex<KernelManager>>>().inner())
}

/// Build and register the system-tray icon with Open / Restart Kernel / Quit.
pub fn setup_tray(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let open_i = MenuItem::with_id(app, "open", "Open", true, None::<&str>)?;
    let restart_i = MenuItem::with_id(app, "restart_kernel", "Restart Kernel", true, None::<&str>)?;
    #[cfg(target_os = "macos")]
    let register_dock_i = MenuItem::with_id(
        app,
        "register_dock",
        "Register Defaultspack to Dock",
        true,
        None::<&str>,
    )?;
    let update_i = MenuItem::with_id(app, "check_update", "Check for Updates", true, None::<&str>)?;
    let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;

    #[cfg(target_os = "macos")]
    let menu = Menu::with_items(
        app,
        &[
            &open_i,
            &restart_i,
            &register_dock_i,
            &update_i,
            &quit_i,
        ],
    )?;
    #[cfg(not(target_os = "macos"))]
    let menu = Menu::with_items(app, &[&open_i, &restart_i, &update_i, &quit_i])?;

    let mut tray_builder = TrayIconBuilder::with_id("main-tray")
        .tooltip("Rumi AI")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "open" => {
                if let Err(error) = show_primary_window(app) {
                    error!("Failed to show Rumi window: {error}");
                }
            }
            "restart_kernel" => {
                let km = get_km(app);
                match km.lock() {
                    Ok(mut guard) => {
                        if let Err(e) = guard.restart() {
                            error!("Failed to restart kernel: {e}");
                        }
                    }
                    Err(e) => {
                        error!("Failed to lock kernel manager: {e}");
                    }
                };
            }
            "register_dock" => {
                #[cfg(target_os = "macos")]
                {
                    let config = app.state::<crate::config::AppConfig>().inner().clone();
                    std::thread::spawn(move || {
                        match crate::dock_registration::register_defaultspack_dock_impl(&config) {
                            Ok(msg) => {
                                info!("Dock registration: {msg}");
                            }
                            Err(e) => {
                                error!("Dock registration failed: {e}");
                            }
                        }
                    });
                }
                #[cfg(not(target_os = "macos"))]
                {
                    error!("Dock registration is only supported on macOS");
                }
            }
            "check_update" => {
                std::thread::spawn(|| match updater::check_for_update() {
                    Ok(Some(info)) => {
                        info!(
                            "Update available: {} -> {}",
                            info.current_version, info.latest_version
                        );
                        if let Err(e) = updater::open_release_page(&info) {
                            error!("Failed to open release page: {e}");
                        }
                    }
                    Ok(None) => {
                        info!("Rumi AI is up to date.");
                    }
                    Err(e) => {
                        error!("Update check failed: {e}");
                    }
                });
            }
            "quit" => {
                request_app_exit(app);
            }
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                let app = tray.app_handle();
                if let Err(error) = show_primary_window(&app) {
                    error!("Failed to show Rumi window: {error}");
                }
            }
        });

    if let Some(icon) = app.default_window_icon() {
        tray_builder = tray_builder.icon(icon.clone());
    } else {
        info!("Default window icon is unavailable; continuing without a tray icon image");
    }

    let _ = tray_builder.build(app)?;

    Ok(())
}
