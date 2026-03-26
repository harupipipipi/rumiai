//! System tray icon and menu for Rumi Viewer.

use std::sync::{Arc, Mutex};

use log::error;
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager,
};

use crate::kernel_manager::KernelManager;

/// Helper: clone the Arc<Mutex<KernelManager>> out of Tauri State.
/// This avoids lifetime issues with the temporary State borrow.
fn get_km(app: &tauri::AppHandle) -> Arc<Mutex<KernelManager>> {
    Arc::clone(app.state::<Arc<Mutex<KernelManager>>>().inner())
}

/// Build and register the system-tray icon with Open / Restart Kernel / Quit.
pub fn setup_tray(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let open_i = MenuItem::with_id(app, "open", "Open", true, None::<&str>)?;
    let restart_i =
        MenuItem::with_id(app, "restart_kernel", "Restart Kernel", true, None::<&str>)?;
    let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;

    let menu = Menu::with_items(app, &[&open_i, &restart_i, &quit_i])?;

    let _ = TrayIconBuilder::with_id("main-tray")
        .tooltip("Rumi AI")
        .icon(app.default_window_icon().unwrap().clone())
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "open" => {
                if let Some(win) = app.get_webview_window("main") {
                    let _ = win.unminimize();
                    let _ = win.show();
                    let _ = win.set_focus();
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
                    Err(e) => error!("KernelManager lock poisoned: {e}"),
                }
            }
            "quit" => {
                let km = get_km(app);
                match km.lock() {
                    Ok(mut guard) => {
                        let _ = guard.stop();
                    }
                    Err(e) => error!("KernelManager lock poisoned: {e}"),
                }
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
                if let Some(win) = app.get_webview_window("main") {
                    let _ = win.unminimize();
                    let _ = win.show();
                    let _ = win.set_focus();
                }
            }
        })
        .build(app)?;

    Ok(())
}
