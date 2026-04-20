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

/// Helper: clone the Arc<Mutex<KernelManager>> out of Tauri State.
fn get_km(app: &tauri::AppHandle) -> Arc<Mutex<KernelManager>> {
    Arc::clone(app.state::<Arc<Mutex<KernelManager>>>().inner())
}

fn show_primary_window(app: &tauri::AppHandle) {
    if let Some(win) = app
        .get_webview_window("panel")
        .or_else(|| app.get_webview_window("main"))
    {
        let _ = win.unminimize();
        let _ = win.show();
        let _ = win.set_focus();
    }
}

/// Build and register the system-tray icon with Open / Restart Kernel / Quit.
pub fn setup_tray(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let open_i = MenuItem::with_id(app, "open", "Open", true, None::<&str>)?;
    let restart_i = MenuItem::with_id(app, "restart_kernel", "Restart Kernel", true, None::<&str>)?;
    let update_i = MenuItem::with_id(app, "check_update", "Check for Updates", true, None::<&str>)?;
    let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;

    let menu = Menu::with_items(app, &[&open_i, &restart_i, &update_i, &quit_i])?;

    let _ = TrayIconBuilder::with_id("main-tray")
        .tooltip("Rumi AI")
        .icon(app.default_window_icon().unwrap().clone())
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "open" => {
                show_primary_window(app);
            }
            "restart_kernel" => {
                let km = get_km(app);
                let mut guard = km.lock().unwrap();
                if let Err(e) = guard.restart() {
                    error!("Failed to restart kernel: {e}");
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
                let km = get_km(app);
                let mut guard = km.lock().unwrap();
                let _ = guard.stop();
                drop(guard);
                drop(km);
                app.exit(0);
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
                show_primary_window(&app);
            }
        })
        .build(app)?;

    Ok(())
}
